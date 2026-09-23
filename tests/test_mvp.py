"""Run with: python -m unittest discover -s tests -v"""

import json
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest.mock import patch

from streamlit.testing.v1 import AppTest

from services import storage
from services.scoring import FIELDS, calculate_readiness, readiness_level

ROOT = Path(__file__).resolve().parent.parent


class TaskForgeTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.data = Path(self.directory.name)
        for source in (ROOT / "data").glob("*.json"):
            shutil.copy(source, self.data / source.name)
        self.data_patch = patch.object(storage, "DATA_DIR", self.data)
        self.data_patch.start()
        storage.save_records("tasks", [task for task in storage.load_records("tasks") if task["id"] in {f"task-{i}" for i in range(1, 6)}])
        storage.save_records("teams", [team for team in storage.load_records("teams") if team["id"] in {f"team-{i}" for i in range(1, 6)}])
        storage.save_records("proposals", [])

    def tearDown(self):
        self.data_patch.stop()
        self.directory.cleanup()

    def test_scoring_and_boundaries(self):
        self.assertEqual(calculate_readiness({})["score"], 0)
        self.assertEqual(calculate_readiness({key: "value" for key, *_ in FIELDS})["score"], 100)
        self.assertEqual(calculate_readiness({"context": "Context", "need": "  "})["score"], 10)
        for score, level in [(0, "Draft"), (39, "Draft"), (40, "Working"), (69, "Working"),
                             (70, "Ready"), (89, "Ready"), (90, "Priority"), (100, "Priority")]:
            self.assertEqual(readiness_level(score), level)
        for task in storage.load_records("tasks"):
            result = calculate_readiness(task)
            self.assertEqual(result["score"], task["readiness_score"])
            self.assertEqual(result["level"], task["readiness_level"])

    def test_bad_json_is_not_overwritten(self):
        path = self.data / "tasks.json"
        path.write_text("broken JSON", encoding="utf-8")
        with self.assertRaises(json.JSONDecodeError):
            storage.add_record("tasks", {"title": "Test"})
        self.assertEqual(path.read_text(encoding="utf-8"), "broken JSON")

    def test_complete_ui_flow(self):
        app = AppTest.from_file(str(ROOT / "app.py"), default_timeout=20).run()
        app.sidebar.radio[0].set_value("Create Task").run()
        self.assertFalse(app.exception)
        app.button(key="publish").click().run()
        self.assertTrue(app.error)
        app.text_input(key="card_title").set_value("Test published task")
        app.text_input(key="task_industry").set_value("Education")
        for key, *_ in FIELDS:
            app.text_area(key=f"card_{key}").set_value("Example detail for the student team")
        app.run()
        app.checkbox(key="confirm_publish").check().run()
        app.button(key="publish").click().run()
        self.assertFalse(app.exception)
        self.assertTrue(app.success)
        published = storage.load_records("tasks")[-1]
        self.assertEqual(published["readiness_score"], 100)
        self.assertEqual(published["industry"], "Education")

        app.sidebar.radio[0].set_value("Catalog").run()
        self.assertFalse(app.exception)
        scores = [int(expander.label.split(" — ")[1].split("/")[0])
                  for expander in app.expander if " — " in expander.label]
        self.assertEqual(scores, sorted(scores, reverse=True))
        app.selectbox(key="catalog_readiness").set_value("Draft").run()
        task_expanders = [expander for expander in app.expander if " — " in expander.label]
        self.assertEqual(len(task_expanders), 1)
        self.assertIn("30/100", task_expanders[0].label)
        app.selectbox(key="catalog_readiness").set_value("Priority").run()

        # Propose on the published task; blank and malformed submissions fail.
        task_id = published["id"]
        submit = app.button(key=f"proposal_submit_{task_id}")
        submit.click().run()
        self.assertTrue(app.error)
        app.text_input(key=f"team_{task_id}").set_value("Campus Coders")
        app.text_input(key=f"timeline_{task_id}").set_value("10 hours")
        app.text_input(key=f"url_{task_id}").set_value("invalid-url")
        app.text_area(key=f"idea_{task_id}").set_value("Build a dashboard")
        app.text_area(key=f"plan_{task_id}").set_value("Interview, prototype, test")
        app.text_area(key=f"done_{task_id}").set_value("Business can inspect the dashboard")
        app.button(key=f"proposal_submit_{task_id}").click().run()
        self.assertTrue(app.error)
        app.text_input(key=f"url_{task_id}").set_value("https://example.com/prototype")
        app.button(key=f"proposal_submit_{task_id}").click().run()
        self.assertFalse(app.exception)
        proposals = storage.load_records("proposals")
        self.assertEqual(len(proposals), 1)
        self.assertEqual(proposals[0]["status"], "Pending")
        self.assertEqual(len(storage.load_records("teams")), 5)
        second = storage.submit_proposal(proposals[0]["task_id"], {
            "team_name": "New Test Team", "solution_idea": "Alternative", "plan": "Test it",
            "estimated_time": "One week", "prototype_url": ""})
        self.assertEqual(len(storage.load_records("teams")), 6)

        app.sidebar.radio[0].set_value("Business Dashboard").run()
        self.assertFalse(app.exception)
        app.button(key=f"accept_{proposals[0]['id']}").click().run()
        saved = storage.load_records("proposals")
        self.assertEqual(saved[0]["status"], "Accepted")
        self.assertEqual(saved[1]["status"], "Pending")
        app.button(key=f"reject_{second['id']}").click().run()
        self.assertEqual(storage.load_records("proposals")[1]["status"], "Rejected")
        app = AppTest.from_file(str(ROOT / "app.py")).run()
        app.sidebar.radio[0].set_value("Business Dashboard").run()
        self.assertFalse(app.exception)
        self.assertTrue(app.button(key=f"accept_{proposals[0]['id']}").disabled)
        self.assertTrue(app.button(key=f"reject_{second['id']}").disabled)

    def test_catalog_industry_filters_keep_legacy_and_draft_tasks(self):
        tasks = storage.load_records("tasks")
        for task in tasks:
            task.pop("industry", None)
        tasks[0]["industry"] = "Retail"
        tasks[1]["industry"] = None
        tasks[2]["industry"] = "  "
        tasks[3]["industry"] = "Retail"  # Draft: still visible alongside full briefs.
        storage.save_records("tasks", tasks)
        original_json = (self.data / "tasks.json").read_bytes()
        app = AppTest.from_file(str(ROOT / "app.py"), default_timeout=20).run()
        app.sidebar.radio[0].set_value("Catalog").run()

        def visible_scores():
            return [int(item.label.split(" — ")[1].split("/")[0])
                    for item in app.expander if " — " in item.label]

        self.assertFalse(app.exception)
        self.assertEqual(visible_scores(), [100, 90, 75, 55, 30])
        self.assertEqual(app.selectbox(key="catalog_industry").options, ["Все отрасли", "Другое", "Retail"])
        self.assertTrue(any('class="tf-badge">Другое</span>' in item.value for item in app.markdown))
        app.selectbox(key="catalog_industry").set_value("Other").run()
        self.assertEqual(visible_scores(), [90, 75, 55])
        app.selectbox(key="catalog_industry").set_value("Retail").run()
        self.assertEqual(visible_scores(), [100, 30])
        app.selectbox(key="catalog_readiness").set_value("Draft").run()
        self.assertEqual(visible_scores(), [30])
        app.selectbox(key="catalog_readiness").set_value("Ready").run()
        self.assertEqual(visible_scores(), [])
        self.assertTrue(any("Ничего не нашлось" in item.value for item in app.markdown))
        self.assertIsNotNone(app.button(key="reset_catalog"))
        app.selectbox(key="catalog_industry").set_value("All")
        app.selectbox(key="catalog_readiness").set_value("All")
        app.selectbox(key="catalog_sort").set_value("Lowest readiness").run()
        self.assertEqual(visible_scores(), [30, 55, 75, 90, 100])
        self.assertFalse(app.exception)
        self.assertEqual((self.data / "tasks.json").read_bytes(), original_json)

    def test_multiple_teams_can_submit_and_be_reviewed_independently(self):
        app = AppTest.from_file(str(ROOT / "app.py"), default_timeout=20).run()
        app.sidebar.radio[0].set_value("Catalog").run()
        task_id = storage.load_records("tasks")[0]["id"]
        for team in ("First Test Team", "Second Test Team", "Third Test Team"):
            app.text_input(key=f"team_{task_id}").set_value(team)
            app.text_input(key=f"timeline_{task_id}").set_value("Two weeks")
            app.text_input(key=f"url_{task_id}").set_value("https://example.com/demo")
            app.text_area(key=f"idea_{task_id}").set_value("Build and test a prototype")
            app.text_area(key=f"plan_{task_id}").set_value("Interview users, build, collect feedback")
            app.text_area(key=f"done_{task_id}").set_value("An inspectable working prototype")
            app.button(key=f"proposal_submit_{task_id}").click().run()
            self.assertFalse(app.exception)
            self.assertTrue(app.success)
        proposals = storage.load_records("proposals")
        self.assertEqual(len(proposals), 3)
        self.assertEqual(len({p["task_id"] for p in proposals}), 1)
        app.sidebar.radio[0].set_value("Business Dashboard").run()
        for index, proposal in enumerate(proposals):
            self.assertIsNotNone(app.button(key=f"accept_{proposal['id']}"))
            app.button(key=f"accept_{proposal['id']}").click().run()
            self.assertEqual([p["status"] for p in storage.load_records("proposals")],
                             ["Accepted"] * (index + 1) + ["Pending"] * (2 - index))
        for index, proposal in enumerate(proposals):
            app.button(key=f"reject_{proposal['id']}").click().run()
            self.assertEqual([p["status"] for p in storage.load_records("proposals")],
                             ["Rejected"] * (index + 1) + ["Accepted"] * (2 - index))
        self.assertFalse(app.exception)


if __name__ == "__main__":
    unittest.main()
