"""Exercise team pages against isolated persisted data without calling AI."""

from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from streamlit.testing.v1 import AppTest

from services import storage
from services.workflow import (accept_delivery, confirm_milestone, get_engagement,
                               leave_review, request_revision, submit_delivery,
                               submit_milestone, team_stats)


class TeamPageTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.patch = patch.object(storage, "DATA_DIR", Path(self.directory.name))
        self.patch.start()
        storage.save_records("tasks", [{"id": "test-task", "title": "Feedback triage",
                                        "expected_result": "Flag urgent feedback",
                                        "success_criteria": "Route urgent cases within one minute"}])
        storage.save_records("teams", [{"id": "test-team", "name": "Test Team", "xp": 99999}])
        storage.save_records("proposals", [{"id": "test-proposal", "team_id": "test-team",
                                            "team_name": "Test Team", "task_id": "test-task",
                                            "status": "Accepted", "solution_idea": "Build a triage tool",
                                            "plan": "Prototype and test", "estimated_time": "Two weeks",
                                            "definition_of_done": "Alerts within one minute"}])

    def tearDown(self):
        self.patch.stop()
        self.directory.cleanup()

    def page(self, name):
        return AppTest.from_string(f"from ui.team_pages import {name}\n{name}()", default_timeout=20).run()

    def test_team_can_submit_checkpoint_and_deliver_without_receiving_unconfirmed_xp(self):
        app = self.page("team_workspace")
        self.assertFalse(app.exception)
        self.assertEqual(app.metric[0].value, "0")
        self.assertEqual(app.metric[1].value, "Новая")
        self.assertEqual([tab.label for tab in app.tabs], ["Результат", "Этапы", "Договорённости"])
        app.text_input(key="milestone_title_test-proposal_0").set_value("Prototype tested")
        app.text_area(key="milestone_evidence_test-proposal_0").set_value("Tested urgent and routine messages with three users.")
        app.button(key="milestone_submit_test-proposal").click().run()
        self.assertFalse(app.exception)
        engagement = get_engagement("test-proposal")
        self.assertEqual(len(engagement["milestones"]), 1)
        self.assertEqual(engagement["milestones"][0]["status"], "Submitted")
        self.assertEqual(team_stats("test-team")["xp"], 0)
        self.assertEqual(app.text_input(key="milestone_title_test-proposal_1").value, "")
        app.text_area(key="delivery_summary_test-proposal").set_value("Triage prototype flags urgent messages within 30 seconds on the supplied examples.")
        app.text_input(key="delivery_url_test-proposal").set_value("https://example.com/demo")
        app.button(key="delivery_submit_test-proposal").click().run()
        self.assertFalse(app.exception)
        self.assertEqual(get_engagement("test-proposal")["status"], "Delivery submitted")
        self.assertEqual(team_stats("test-team")["xp"], 0)
        self.assertTrue(any("Результат на проверке у бизнеса" in message.value for message in app.info))
        self.assertNotIn("delivery_submit_test-proposal", [button.key for button in app.button])

    def test_pending_proposal_cannot_deliver(self):
        proposals = storage.load_records("proposals")
        proposals[0]["status"] = "Pending"
        storage.save_records("proposals", proposals)
        app = self.page("team_workspace")
        self.assertFalse(app.exception)
        self.assertTrue(any("Ожидаем решения бизнеса" in message.value for message in app.info))
        self.assertNotIn("delivery_submit_test-proposal", [button.key for button in app.button])

    def test_invalid_delivery_retains_input_and_creates_no_engagement(self):
        app = self.page("team_workspace")
        app.text_area(key="delivery_summary_test-proposal").set_value("Working result with documented acceptance checks")
        app.text_input(key="delivery_url_test-proposal").set_value("javascript:alert(1)")
        app.button(key="delivery_submit_test-proposal").click().run()
        self.assertFalse(app.exception)
        self.assertTrue(app.error)
        self.assertIn("Укажите корректную ссылку", app.error[0].value)
        self.assertEqual(app.text_area(key="delivery_summary_test-proposal").value,
                         "Working result with documented acceptance checks")
        self.assertIsNone(get_engagement("test-proposal")["delivery"])

    def test_profile_save_and_leaderboard_search(self):
        app = self.page("team_workspace")
        app.text_area(key="team_about_test-team").set_value("We turn customer research into working prototypes.")
        app.text_input(key="team_skills_test-team").set_value("Python, UX research")
        app.text_input(key="team_interests_test-team").set_value("Retail, education")
        app.button(key="team_profile_save_test-team").click().run()
        self.assertFalse(app.exception)
        team = storage.load_records("teams")[0]
        self.assertEqual(team["skills"], ["Python", "UX research"])
        self.assertEqual(team["interests"], ["Retail", "education"])
        public = self.page("teams_page")
        self.assertFalse(public.exception)
        public.text_input(key="team_search").set_value("UX research").run()
        self.assertFalse(public.exception)
        self.assertEqual(public.dataframe[0].value.iloc[0]["XP"], 0)
        self.assertEqual(public.dataframe[0].value.iloc[0]["Оценка"], "Новая команда")
        public.text_input(key="team_search").set_value("no matching team").run()
        self.assertTrue(any("Команды не найдены" in message.value for message in public.markdown))

    def test_empty_team_pages_have_actionable_states(self):
        storage.save_records("teams", [])
        storage.save_records("proposals", [])
        for name in ("team_workspace", "teams_page"):
            app = self.page(name)
            self.assertFalse(app.exception)
            self.assertTrue(any("tf-empty" in message.value for message in app.markdown))
            app.button[0].click().run()
            self.assertEqual(app.session_state["page"], "Catalog")

    def test_revision_and_negative_review_are_visible_with_original_criteria(self):
        engagement = submit_milestone("test-proposal", "Prototype", "Working prototype with sample messages")
        confirm_milestone("test-proposal", engagement["milestones"][0]["id"])
        submit_delivery("test-proposal", "First result", "https://example.com/v1")
        request_revision("test-proposal", "Add the promised urgent-message routing.")
        tasks = storage.load_records("tasks")
        tasks[0]["success_criteria"] = "A different requirement added after work started"
        storage.save_records("tasks", tasks)
        app = self.page("team_workspace")
        self.assertFalse(app.exception)
        content = " ".join(item.value for item in app.markdown)
        self.assertIn("Route urgent cases within one minute", content)
        self.assertNotIn("A different requirement", content)
        self.assertIn("Add the promised urgent-message routing.", content)
        self.assertEqual(app.text_area(key="delivery_summary_test-proposal").value, "First result")
        app.text_area(key="delivery_summary_test-proposal").set_value("Added urgency routing and test instructions.")
        app.button(key="delivery_submit_test-proposal").click().run()
        self.assertFalse(app.exception)
        self.assertEqual(get_engagement("test-proposal")["delivery"]["version"], 2)
        self.assertTrue(any("История версий" in item.label for item in app.expander))
        accept_delivery("test-proposal")
        leave_review("test-proposal", 1, "Several urgent messages were missed.",
                     "The agreed one-minute routing criterion was not met on supplied examples.")
        app.run()
        self.assertFalse(app.exception)
        self.assertEqual(app.metric[0].value, "0")
        self.assertEqual(app.metric[1].value, "1.0 / 5")
        self.assertEqual(app.metric[2].value, "1")
        self.assertNotIn("delivery_submit_test-proposal", [button.key for button in app.button])
        public = self.page("teams_page")
        self.assertFalse(public.exception)
        self.assertEqual(public.dataframe[0].value.iloc[0]["Оценка"], "1.0 / 5")
        ledger = public.dataframe[1].value
        self.assertEqual(ledger.iloc[0]["Изменение XP"], -20)
        self.assertEqual(ledger.iloc[0]["Начислено"], -10)
        self.assertEqual(ledger.iloc[0]["Баланс"], 0)


if __name__ == "__main__":
    unittest.main()
