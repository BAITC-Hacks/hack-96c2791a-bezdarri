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
        self.assertFalse(app.exception)
        app.button[0].click().run()
        self.assertTrue(app.error)
        app.text_input[0].set_value("Test published task")
        for field in app.text_area:
            field.set_value("Example detail for the student team")
        app.button[0].click().run()
        self.assertFalse(app.exception)
        self.assertTrue(app.success)
        published = storage.load_records("tasks")[-1]
        self.assertEqual(published["readiness_score"], 100)

        app.sidebar.radio[0].set_value("Catalog").run()
        self.assertFalse(app.exception)
        scores = [int(expander.label.split(" — ")[1].split("/")[0])
                  for expander in app.expander if " — " in expander.label]
        self.assertEqual(scores, sorted(scores, reverse=True))
        app.selectbox[0].set_value("Draft").run()
        self.assertEqual(len(app.expander), 2)  # One task plus the teams list.
        self.assertIn("30/100", app.expander[0].label)
        app.selectbox[0].set_value("Priority").run()

        # Propose on the first displayed task; blank and malformed submissions fail.
        submit = next(button for button in app.button if button.label == "Submit proposal")
        submit.click().run()
        self.assertTrue(app.error)
        app.text_input[0].set_value("Campus Coders")
        app.text_input[1].set_value("10 hours")
        app.text_input[2].set_value("invalid-url")
        app.text_area[0].set_value("Build a dashboard")
        app.text_area[1].set_value("Interview, prototype, test")
        app.button[0].click().run()
        self.assertTrue(app.error)
        app.text_input[2].set_value("https://example.com/prototype")
        app.button[0].click().run()
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


if __name__ == "__main__":
    unittest.main()
