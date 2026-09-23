"""Workflow tests use isolated JSON data and never make network requests."""

from concurrent.futures import ThreadPoolExecutor
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from services import storage, workflow


class WorkflowTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.data = Path(self.directory.name)
        self.data_patch = patch.object(storage, "DATA_DIR", self.data)
        self.data_patch.start()
        storage.save_records("tasks", [
            {"id": "task-1", "title": "Feedback analysis", "success_criteria": "Explain urgent complaints", "expected_result": "Alerts"},
            {"id": "task-2", "title": "Cafe planning", "success_criteria": "Compare against baseline"},
            {"id": "task-3", "title": "Booking calendar"},
        ])
        storage.save_records("teams", [{"id": "team-1", "name": "Nova", "xp": 999},
                                       {"id": "team-2", "name": "Orbit"}])
        storage.save_records("proposals", [
            {"id": "proposal-1", "task_id": "task-1", "team_id": "team-1", "status": "Accepted"},
            {"id": "proposal-2", "task_id": "task-1", "team_id": "team-2", "status": "Accepted"},
            {"id": "proposal-3", "task_id": "task-2", "team_id": "team-1", "status": "Accepted"},
            {"id": "proposal-4", "task_id": "task-3", "team_id": "team-1", "status": "Accepted"},
        ])

    def tearDown(self):
        self.data_patch.stop()
        self.directory.cleanup()

    def _complete(self, proposal_id="proposal-1", rating=5):
        workflow.submit_delivery(proposal_id, "Working solution", "https://example.com/demo")
        workflow.accept_delivery(proposal_id)
        return workflow.leave_review(proposal_id, rating, "Detailed business feedback",
                                      "Agreed alert criterion was not met" if rating <= 2 else "")

    def _milestone(self, proposal_id="proposal-1", title="Prototype"):
        record = workflow.submit_milestone(proposal_id, title, "Demo with sample inputs and results")
        return workflow.confirm_milestone(proposal_id, record["milestones"][-1]["id"])

    def test_reading_default_work_does_not_write_data_or_award_seed_xp(self):
        record = workflow.get_engagement("proposal-1")
        self.assertEqual(record["status"], "In progress")
        self.assertEqual(record["milestones"], [])
        self.assertFalse((self.data / "engagements.json").exists())
        stats = workflow.team_stats("team-1")
        self.assertEqual(stats["xp"], 0)
        self.assertIsNone(stats["average_rating"])
        self.assertEqual(stats["active_tasks"], 3)

    def test_multiple_teams_complete_same_task_independently(self):
        self._milestone()
        self._milestone(title="Validation")
        self._complete()
        second = workflow.get_engagement("proposal-2")
        self.assertEqual(second["status"], "In progress")
        self.assertEqual(workflow.team_stats("team-2")["xp"], 0)
        self._complete("proposal-2", 4)
        self.assertEqual(workflow.team_stats("team-1")["xp"], 60)
        self.assertEqual(workflow.team_stats("team-2")["xp"], 20)
        self.assertEqual(workflow.team_stats("team-1")["completed_tasks"], 1)
        self.assertEqual(workflow.team_stats("team-1")["active_tasks"], 2)
        self.assertEqual(workflow.leaderboard()[0]["id"], "team-1")

    def test_each_rating_has_exact_documented_xp_and_floor(self):
        for rating, expected in workflow.REVIEW_XP.items():
            with self.subTest(rating=rating):
                storage.save_records("engagements", [])
                record = self._complete(rating=rating)
                self.assertEqual(record["review"]["xp_delta"], expected)
                self.assertEqual(record["review"]["xp_applied"], max(0, expected))
                self.assertEqual(workflow.team_stats("team-1")["xp"], max(0, expected))

    def test_xp_floor_is_applied_per_event_and_does_not_create_future_debt(self):
        self._complete(rating=1)
        self._complete("proposal-3", 5)
        self._complete("proposal-4", 2)
        stats = workflow.team_stats("team-1")
        self.assertEqual(stats["xp"], 30)
        self.assertEqual([event["xp_after"] for event in stats["ledger"]], [0, 40, 30])
        self.assertEqual([event["xp_applied"] for event in stats["ledger"]], [0, 40, -10])
        self.assertEqual(stats["review_count"], 3)
        self.assertEqual(stats["average_rating"], 2.67)

    def test_negative_review_keeps_confirmed_history_and_applies_actual_deduction(self):
        self._milestone()
        record = self._complete(rating=1)
        self.assertEqual(record["review"]["xp_delta"], -20)
        self.assertEqual(record["review"]["xp_applied"], -10)
        self.assertEqual(record["milestones"][0]["status"], "Confirmed")
        stats = workflow.team_stats("team-1")
        self.assertEqual(stats["confirmed_milestones"], 1)
        self.assertEqual(stats["xp"], 0)
        self.assertIn("criterion", stats["reviews"][0]["criterion_feedback"])
        self.assertEqual(stats["reviews"][0]["success_criteria"], "Explain urgent complaints")

    def test_duplicate_confirmation_and_review_are_idempotent(self):
        record = self._milestone()
        milestone_id = record["milestones"][0]["id"]
        workflow.confirm_milestone("proposal-1", milestone_id)
        self._complete()
        before = (self.data / "engagements.json").read_bytes()
        workflow.leave_review("proposal-1", 5, "Detailed business feedback")
        workflow.confirm_milestone("proposal-1", milestone_id)
        workflow.accept_delivery("proposal-1")
        self.assertEqual((self.data / "engagements.json").read_bytes(), before)
        self.assertEqual(workflow.team_stats("team-1")["xp"], 50)
        with self.assertRaisesRegex(ValueError, "Only one final review"):
            workflow.leave_review("proposal-1", 4, "Changed mind")

    def test_duplicate_proposals_share_work_and_cannot_farm_reviews(self):
        self._complete()
        duplicate = storage.add_record("proposals", {
            "task_id": "task-1", "team_id": "team-1", "status": "Accepted"})
        first = workflow.get_engagement("proposal-1")
        second = workflow.get_engagement(duplicate["id"])
        self.assertEqual(first["id"], second["id"])
        self.assertEqual(second["status"], "Completed")
        workflow.leave_review(duplicate["id"], 5, "Detailed business feedback")
        with self.assertRaises(ValueError):
            workflow.submit_delivery(duplicate["id"], "Another result")
        self.assertEqual(len(storage.load_records("engagements")), 1)
        self.assertEqual(workflow.team_stats("team-1")["xp"], 40)

    def test_two_milestone_limit_and_pending_stages_award_nothing(self):
        first = workflow.submit_milestone("proposal-1", "Prototype", "Demo evidence")
        same = workflow.submit_milestone("proposal-1", "Prototype", "Demo evidence")
        self.assertEqual(len(same["milestones"]), 1)
        self.assertEqual(first["id"], same["id"])
        workflow.submit_milestone("proposal-1", "Validation", "Test results")
        self.assertEqual(workflow.team_stats("team-1")["xp"], 0)
        with self.assertRaisesRegex(ValueError, "at most two"):
            workflow.submit_milestone("proposal-1", "Third", "More evidence")
        with self.assertRaises(ValueError):
            workflow.confirm_milestone("proposal-2", first["milestones"][0]["id"])

    def test_revision_resubmission_keeps_old_evidence_and_feedback(self):
        workflow.submit_delivery("proposal-1", "First version", "https://example.com/v1")
        with self.assertRaises(ValueError):
            workflow.submit_delivery("proposal-1", "Changed without review")
        with self.assertRaises(ValueError):
            workflow.leave_review("proposal-1", 5, "Looks good")
        workflow.request_revision("proposal-1", "Include urgent alerts")
        with self.assertRaises(ValueError):
            workflow.accept_delivery("proposal-1")
        updated = workflow.submit_delivery("proposal-1", "Now includes alerts", "https://example.com/v2")
        self.assertEqual(updated["delivery"]["version"], 2)
        self.assertEqual(updated["delivery_history"][0]["feedback"], "Include urgent alerts")
        self.assertEqual(updated["delivery_history"][0]["url"], "https://example.com/v1")
        workflow.accept_delivery("proposal-1")
        self.assertEqual(workflow.team_stats("team-1")["completed_tasks"], 1)
        self.assertEqual(workflow.team_stats("team-1")["review_count"], 0)
        project = workflow.team_stats("team-1")["completed_projects"][0]
        self.assertEqual(project["url"], "https://example.com/v2")
        self.assertIsNone(project["review"])
        workflow.leave_review("proposal-1", 5, "Agreed alerts now work")
        self.assertEqual(workflow.team_stats("team-1")["xp"], 40)
        with self.assertRaises(ValueError):
            workflow.request_revision("proposal-1", "Another change")

    def test_negative_reviews_require_criterion_reason_and_valid_rating(self):
        workflow.submit_delivery("proposal-1", "Prototype")
        workflow.accept_delivery("proposal-1")
        for rating in (0, 6, True, 1.0, "5"):
            with self.subTest(rating=rating), self.assertRaises(ValueError):
                workflow.leave_review("proposal-1", rating, "Review")
        for rating in (1, 2):
            with self.subTest(rating=rating), self.assertRaisesRegex(ValueError, "criterion"):
                workflow.leave_review("proposal-1", rating, "Not satisfied")
        with self.assertRaises(ValueError):
            workflow.leave_review("proposal-1", 5, " ")
        self.assertIsNone(workflow.get_engagement("proposal-1")["review"])

    def test_pending_rejected_and_missing_proposals_cannot_do_work(self):
        for status in ("Pending", "Rejected"):
            storage.update_record("proposals", "proposal-1", {"status": status})
            with self.subTest(status=status), self.assertRaises(ValueError):
                workflow.submit_delivery("proposal-1", "Prototype")
            with self.assertRaises(ValueError):
                workflow.submit_milestone("proposal-1", "Prototype", "Evidence")
        with self.assertRaises(ValueError):
            workflow.get_engagement("missing")
        self.assertFalse((self.data / "engagements.json").exists())

    def test_cannot_erase_work_by_rejecting_selected_proposal(self):
        storage.review_proposal("proposal-1", "Rejected")
        storage.review_proposal("proposal-1", "Accepted")
        workflow.submit_milestone("proposal-1", "Prototype", "Evidence")
        with self.assertRaisesRegex(ValueError, "already started"):
            storage.review_proposal("proposal-1", "Rejected")
        self.assertEqual(storage.load_records("proposals")[0]["status"], "Accepted")

    def test_pending_duplicate_proposal_can_still_be_rejected_after_work_started(self):
        self._milestone()
        duplicate = storage.add_record("proposals", {
            "task_id": "task-1", "team_id": "team-1", "status": "Pending"})
        result = storage.review_proposal(duplicate["id"], "Rejected")
        self.assertEqual(result["status"], "Rejected")
        self.assertEqual(workflow.team_stats("team-1")["xp"], 10)

    def test_agreed_criteria_are_snapshotted_when_work_begins(self):
        self._milestone()
        storage.update_record("tasks", "task-1", {"success_criteria": "Entirely new requirement"})
        record = self._complete(rating=2)
        self.assertEqual(record["success_criteria"], "Explain urgent complaints")

    def test_validation_prevents_empty_work_and_unsafe_links(self):
        for title, evidence in ((" ", "Evidence"), ("Title", " ")):
            with self.assertRaises(ValueError):
                workflow.submit_milestone("proposal-1", title, evidence)
        for url in ("javascript:alert(1)", "file:///C:/secret", "https://", "invalid-url",
                    "https://user:pass@example.com", "https://example.com:invalid", "https://exa mple.com"):
            with self.subTest(url=url), self.assertRaises(ValueError):
                workflow.submit_delivery("proposal-1", "Summary", url)
        with self.assertRaises(ValueError):
            workflow.submit_delivery("proposal-1", " ")
        with self.assertRaises(ValueError):
            workflow.accept_delivery("proposal-1")
        self.assertFalse((self.data / "engagements.json").exists())

    def test_profile_updates_preserve_identity_and_deduplicate_tags(self):
        original = storage.load_records("teams")[0]
        saved = workflow.update_team_profile("team-1", " We build apps ", "Python, UI, python, ", ["Retail", "retail", "Education"])
        self.assertEqual(saved["id"], original["id"])
        self.assertEqual(saved["name"], "Nova")
        self.assertEqual(saved["about"], "We build apps")
        self.assertEqual(saved["skills"], ["Python", "UI"])
        self.assertEqual(saved["interests"], ["Retail", "Education"])
        self.assertEqual(workflow.leaderboard()[0]["xp"], 0)
        with self.assertRaises(ValueError):
            workflow.update_team_profile("missing", "About", [], [])

    def test_concurrent_confirmations_award_xp_once(self):
        record = workflow.submit_milestone("proposal-1", "Prototype", "Evidence")
        milestone_id = record["milestones"][0]["id"]
        with ThreadPoolExecutor(max_workers=8) as executor:
            list(executor.map(lambda _: workflow.confirm_milestone("proposal-1", milestone_id), range(20)))
        self.assertEqual(workflow.team_stats("team-1")["xp"], 10)
        self.assertEqual(len(workflow.team_stats("team-1")["ledger"]), 1)

    def test_concurrent_adds_do_not_lose_records(self):
        with ThreadPoolExecutor(max_workers=8) as executor:
            list(executor.map(lambda index: storage.add_record("notes", {"number": index}), range(30)))
        self.assertEqual({row["number"] for row in storage.load_records("notes")}, set(range(30)))
        self.assertFalse(list(self.data.glob("*.tmp")))

    def test_failed_atomic_replace_keeps_old_json_and_cleans_tempfile(self):
        original = (self.data / "teams.json").read_bytes()
        with patch.object(storage.os, "replace", side_effect=OSError("Simulated failure")):
            with self.assertRaises(OSError):
                storage.add_record("teams", {"name": "Never saved"})
        self.assertEqual((self.data / "teams.json").read_bytes(), original)
        self.assertFalse(list(self.data.glob("*.tmp")))

    def test_invalid_json_cannot_be_replaced_by_workflow(self):
        path = self.data / "engagements.json"
        path.write_text("broken JSON", encoding="utf-8")
        with self.assertRaises(json.JSONDecodeError):
            workflow.submit_delivery("proposal-1", "Summary")
        self.assertEqual(path.read_text(encoding="utf-8"), "broken JSON")


if __name__ == "__main__":
    unittest.main()
