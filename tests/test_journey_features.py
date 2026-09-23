"""Cross-page tests for direction selection, delivery acceptance and reputation."""

from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from streamlit.testing.v1 import AppTest

from services import storage, workflow
from services.ai import AIError

ROOT = Path(__file__).resolve().parent.parent


class JourneyTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.patch = patch.object(storage, "DATA_DIR", Path(self.directory.name))
        self.patch.start()
        storage.save_records("tasks", [{"id": "challenge", "title": "Urgent feedback",
            "expected_result": "Alert the manager about urgent complaints",
            "success_criteria": "Each urgent example triggers an alert"}])
        storage.save_records("teams", [{"id": "team", "name": "Nova"}])
        storage.save_records("proposals", [])

    def tearDown(self):
        self.patch.stop()
        self.directory.cleanup()

    def app(self):
        app = AppTest.from_file(str(ROOT / "app.py"), default_timeout=20).run()
        app.sidebar.radio[0].set_value("Create Task").run()
        self.assertFalse(app.exception)
        return app

    def proposal(self):
        return storage.submit_proposal("challenge", {"team_name": "Nova", "solution_idea": "Send alerts",
            "plan": "Build then test using the provided examples", "estimated_time": "One week",
            "definition_of_done": "Each urgent example triggers an alert", "prototype_url": ""})

    def click_label(self, app, label):
        next(button for button in app.button if button.label == label).click().run()
        self.assertFalse(app.exception)

    def test_hypotheses_require_selection_and_manual_confirmation_and_publish_once(self):
        app = self.app()
        app.text_area(key="business_description").set_value("Хотим AI для анализа отзывов").run()
        app.button(key="explore_guided").click().run()
        self.assertFalse(app.exception)
        self.assertEqual(app.text_area(key="card_expected_result").value, "")
        app.button(key="direction_0").click().run()
        outcome = app.text_area(key="card_expected_result").value
        self.assertTrue(outcome)
        self.assertEqual(app.text_area(key="card_data_materials").value, "")
        app.text_input(key="card_title").set_value("Feedback project").run()
        app.button(key="publish").click().run()
        self.assertTrue(app.error)
        self.assertEqual(len(storage.load_records("tasks")), 1)
        app.checkbox(key="confirm_publish").check().run()
        app.button(key="publish").click().run()
        self.assertEqual(len(storage.load_records("tasks")), 2)
        saved = storage.load_records("tasks")[-1]
        self.assertEqual(saved["expected_result"], outcome)
        self.assertEqual(saved["selected_direction"]["source"], "Guided templates")
        app.run()
        self.assertTrue(app.button(key="publish").disabled)
        app.button(key="new_brief").click().run()
        self.assertEqual(app.text_input(key="card_title").value, "")
        self.assertEqual(app.text_area(key="card_expected_result").value, "")

    def test_editing_selected_outcome_is_used_for_ai_grounding(self):
        with patch("services.ai.analyze_task", side_effect=AIError("Controlled test error")) as analyze:
            app = self.app()
            app.text_area(key="business_description").set_value("Analyze customer reviews").run()
            app.button(key="explore_guided").click().run()
            app.button(key="direction_0").click().run()
            app.text_area(key="card_expected_result").set_value("Notify a manager about urgent cases").run()
            app.button(key="analyze").click().run()
        self.assertIn("Notify a manager about urgent cases", analyze.call_args.args[0])
        self.assertEqual(app.text_area(key="card_expected_result").value, "Notify a manager about urgent cases")

    def test_proposal_delivery_revision_review_and_leaderboard_across_pages(self):
        app = self.app()
        app.sidebar.radio[0].set_value("Catalog").run()
        app.text_input(key="team_challenge").set_value("Nova")
        app.text_input(key="timeline_challenge").set_value("One week")
        app.text_area(key="idea_challenge").set_value("Send alerts")
        app.text_area(key="plan_challenge").set_value("Build and validate against examples")
        app.text_area(key="done_challenge").set_value("Each urgent example triggers an alert")
        app.button(key="proposal_submit_challenge").click().run()
        proposal_id = storage.load_records("proposals")[0]["id"]
        app.sidebar.radio[0].set_value("Business Dashboard").run()
        app.button(key=f"compare_{proposal_id}").click().run()
        self.assertTrue(any("Локальный чек-лист" in message.value for message in app.caption))
        app.button(key=f"accept_{proposal_id}").click().run()
        app.sidebar.radio[0].set_value("Team Workspace").run()
        app.text_input(key=f"milestone_title_{proposal_id}_0").set_value("Working prototype")
        app.text_area(key=f"milestone_evidence_{proposal_id}_0").set_value("Prototype tested against supplied urgent reviews")
        app.button(key=f"milestone_submit_{proposal_id}").click().run()
        work = workflow.get_engagement(proposal_id)
        self.assertEqual(workflow.team_stats("team")["xp"], 0)
        milestone_id = work["milestones"][0]["id"]
        app.sidebar.radio[0].set_value("Business Dashboard").run()
        app.button(key=f"confirm_{milestone_id}").click().run()
        self.assertEqual(workflow.team_stats("team")["xp"], 10)
        app.sidebar.radio[0].set_value("Team Workspace").run()
        app.text_area(key=f"delivery_summary_{proposal_id}").set_value("Prototype and acceptance report")
        app.button(key=f"delivery_submit_{proposal_id}").click().run()
        app.sidebar.radio[0].set_value("Business Dashboard").run()
        app.text_area(key=f"revision_{proposal_id}").set_value("Include the missing urgent example in the report")
        self.click_label(app, "Вернуть на доработку")
        self.assertEqual(workflow.get_engagement(proposal_id)["status"], "Revision requested")
        app.sidebar.radio[0].set_value("Team Workspace").run()
        app.text_area(key=f"delivery_summary_{proposal_id}").set_value("All supplied urgent examples now included")
        app.button(key=f"delivery_submit_{proposal_id}").click().run()
        app.sidebar.radio[0].set_value("Business Dashboard").run()
        app.button(key=f"delivery_accept_{proposal_id}").click().run()
        app.select_slider(key=f"rating_{proposal_id}").set_value(5)
        app.text_area(key=f"review_comment_{proposal_id}").set_value("All agreed criteria verified; useful result")
        app.checkbox(key=f"review_confirm_{proposal_id}").check()
        self.click_label(app, "Опубликовать отзыв")
        self.assertEqual(workflow.team_stats("team")["xp"], 50)
        self.assertEqual(workflow.team_stats("team")["review_count"], 1)
        app.sidebar.radio[0].set_value("Teams & Ratings").run()
        self.assertFalse(app.exception)
        self.assertEqual(app.dataframe[0].value.iloc[0]["XP"], 50)
        self.assertEqual(app.dataframe[0].value.iloc[0]["Оценка"], "5.0 / 5")
        # Data survives a fresh UI session; browsing does not add XP.
        app = self.app()
        app.sidebar.radio[0].set_value("Team Workspace").run()
        self.assertEqual(workflow.team_stats("team")["xp"], 50)

    def test_duplicate_proposals_share_one_work_panel_and_final_review_locks_milestones(self):
        first, second = self.proposal(), self.proposal()
        for proposal in (first, second):
            storage.review_proposal(proposal["id"], "Accepted")
        work = workflow.submit_milestone(first["id"], "Prototype", "Demonstrated prototype")
        milestone_id = work["milestones"][0]["id"]
        pending = self.proposal()
        app = self.app()
        app.sidebar.radio[0].set_value("Business Dashboard").run()
        self.assertFalse(app.exception)
        self.assertEqual(sum(button.key == f"confirm_{milestone_id}" for button in app.button), 1)
        self.assertFalse(app.button(key=f"reject_{pending['id']}").disabled)
        app.button(key=f"reject_{pending['id']}").click().run()
        self.assertEqual(storage.load_records("proposals")[-1]["status"], "Rejected")
        workflow.submit_delivery(first["id"], "Verified final work")
        workflow.accept_delivery(first["id"])
        workflow.leave_review(first["id"], 4, "Good result")
        app.run()
        self.assertFalse(app.exception)
        self.assertNotIn(f"confirm_{milestone_id}", [button.key for button in app.button])
        self.assertEqual(workflow.team_stats("team")["xp"], 20)

    def test_overview_example_preserves_existing_draft_and_never_auto_publishes(self):
        with patch("services.ai.analyze_task") as analyze:
            app = AppTest.from_file(str(ROOT / "app.py"), default_timeout=20).run()
            self.assertEqual(app.sidebar.radio[0].value, "Overview")
            app.button(key="overview_demo").click().run()
            self.assertFalse(app.exception)
            self.assertEqual(app.sidebar.radio[0].value, "Create Task")
            self.assertIn("отзывов", app.text_input(key="card_title").value)
            self.assertFalse(app.checkbox(key="confirm_publish").value)
            self.assertEqual(len(storage.load_records("tasks")), 1)
            app.text_input(key="card_title").set_value("Мой собственный проект").run()
            app.text_input(key="task_industry").set_value("Моя отрасль").run()
            app.sidebar.radio[0].set_value("Overview").run()
            app.button(key="overview_demo").click().run()
            self.assertEqual(app.text_input(key="card_title").value, "Мой собственный проект")
            self.assertEqual(app.text_input(key="task_industry").value, "Моя отрасль")
            self.assertTrue(any("Ваш черновик сохранён" in item.value for item in app.info))
            self.assertEqual(len(storage.load_records("tasks")), 1)
            analyze.assert_not_called()

    def test_published_task_opens_catalog_with_clear_filters(self):
        app = self.app()
        app.sidebar.radio[0].set_value("Catalog").run()
        app.text_input(key="catalog_search").set_value("no-match").run()
        app.sidebar.radio[0].set_value("Create Task").run()
        app.button(key="load_example").click().run()
        app.checkbox(key="confirm_publish").check().run()
        app.button(key="publish").click().run()
        self.assertFalse(app.exception)
        self.assertEqual(len(storage.load_records("tasks")), 2)
        app.button(key="view_published").click().run()
        self.assertEqual(app.sidebar.radio[0].value, "Catalog")
        self.assertEqual(app.text_input(key="catalog_search").value, "")
        self.assertEqual(app.selectbox(key="catalog_sort").value, "Newest first")
        self.assertTrue(any("Помощник для анализа отзывов" in row.label for row in app.expander))


if __name__ == "__main__":
    unittest.main()
