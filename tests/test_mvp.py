"""Domain and real Streamlit state-machine tests, always using temporary data."""
import json
import shutil
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest.mock import patch
from streamlit.testing.v1 import AppTest
from services import storage as db
from services.scoring import FIELDS, TASK_KEYS, has_value, task_readiness, readiness_level
from services.matching import skill_match, expectation_check, interpretations

ROOT = Path(__file__).resolve().parent.parent

class Workspace(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        for source in (ROOT / "data").glob("*.json"):
            shutil.copy(source, self.tmp.name)
        p = patch.object(db, "DATA_DIR", Path(self.tmp.name))
        p.start()
        self.addCleanup(p.stop)
        db.save_records("proposals", [])

    def proposal(self, team="team-1", task="task-1"):
        return db.submit_proposal(task, dict(team_id=team, solution_idea="Build it", plan="Prototype, test", estimated_time="2 weeks", definition_of_done="Dashboard and alerts", prototype_url="https://example.com"))

class DomainTests(Workspace):
    def test_confirmation_and_unknowns(self):
        task = {k: "Provided business detail" for k in TASK_KEYS}
        self.assertEqual(task_readiness(task)["score"], 0)
        task["confirmed_fields"] = TASK_KEYS
        self.assertEqual(task_readiness(task)["score"], 100)
        for placeholder in ("пока не знаю", "не знаю.", "Not provided", "no data", "?", "-", "   "):
            task["data_materials"] = placeholder
            self.assertEqual(task_readiness(task)["score"], 80)
        task["data_materials"] = "CSV"
        task["confirmed_fields"] = [k for k in TASK_KEYS if k != "data_materials"]
        self.assertEqual(task_readiness(task)["score"], 80)
        task["ai_analysis"] = {"scoring": {"total_score": 999}}
        self.assertEqual(task_readiness(task)["score"], 80)

    def test_levels(self):
        for score, level in [(0,"Draft"),(39,"Draft"),(40,"Workable"),(69,"Workable"),(70,"Ready"),(89,"Ready"),(90,"Priority"),(100,"Priority")]:
            self.assertEqual(readiness_level(score), level)

    def test_seed_data_meets_case(self):
        for name in ("tasks", "teams", "drafts"):
            self.assertGreaterEqual(len(db.load_records(name)), 5)
        original = json.loads((ROOT / "data/proposals.json").read_text(encoding="utf-8-sig"))
        self.assertGreaterEqual(len(original), 5)
        self.assertEqual({task_readiness(t)["level"] for t in db.load_records("tasks")}, {"Draft","Workable","Ready","Priority"})
        for team in db.load_records("teams")[:5]:
            self.assertTrue(team["skills"])
            self.assertTrue(team["interests"])

    def test_publish_confirmation_and_low_score_access(self):
        with self.assertRaises(ValueError):
            db.publish_task({"title": "Test", "topic": "AI"})
        task = db.publish_task({"title": "Low score", "topic": "AI"}, True)
        self.assertEqual(task["readiness_score"], 0)
        p = self.proposal(task=task["id"])
        self.assertEqual(p["status"], "Pending")

    def test_multi_team_manual_selection(self):
        a, b, c = self.proposal(), self.proposal("team-2"), self.proposal("team-3")
        db.review_proposal(a["id"], "Accepted")
        db.review_proposal(b["id"], "Accepted")
        self.assertEqual([p["status"] for p in db.load_records("proposals")], ["Accepted","Accepted","Pending"])
        db.review_proposal(c["id"], "Rejected")
        self.assertEqual(db.team_stats("team-1")["xp"], 0)

    def test_xp_limits_duplicate_reviews_and_results(self):
        p = self.proposal()
        with self.assertRaises(ValueError):
            db.confirm_milestone(p["id"], "First", "Proof")
        with self.assertRaises(ValueError):
            db.submit_result(p["id"], "Done")
        db.review_proposal(p["id"], "Accepted")
        with self.assertRaises(ValueError):
            db.leave_review(p["id"], 5, "Great")
        db.confirm_milestone(p["id"], "First", "Criteria 1 checked")
        with self.assertRaises(ValueError):
            db.confirm_milestone(p["id"], "First", "Again")
        db.confirm_milestone(p["id"], "Second", "Criteria 2 checked")
        with self.assertRaises(ValueError):
            db.confirm_milestone(p["id"], "Third", "Not allowed")
        db.submit_result(p["id"], "All agreed cases passed")
        db.leave_review(p["id"], 5, "All agreed acceptance checks passed")
        stats = db.team_stats("team-1")
        self.assertEqual((stats["xp"], stats["completed"], stats["average"]), (60,1,5))
        with self.assertRaises(ValueError):
            db.leave_review(p["id"], 5, "Again")
        with self.assertRaises(ValueError):
            db.review_proposal(p["id"], "Rejected")

    def test_cap_across_duplicate_proposals(self):
        a, b = self.proposal(), self.proposal()
        for p in (a,b):
            db.review_proposal(p["id"], "Accepted")
        db.confirm_milestone(a["id"], "First", "Proof")
        db.confirm_milestone(b["id"], "Second", "Proof")
        with self.assertRaises(ValueError):
            db.confirm_milestone(b["id"], "Third", "Proof")
        db.submit_result(a["id"], "Done")
        db.submit_result(b["id"], "Done")
        db.leave_review(a["id"], 4, "Meets criteria")
        with self.assertRaises(ValueError):
            db.leave_review(b["id"], 5, "Duplicate")
        self.assertEqual(db.team_stats("team-1")["xp"], 40)

    def test_rating_table_nonnegative_and_reason(self):
        for rating, xp in db.REVIEW_XP.items():
            db.save_records("proposals", [])
            p = self.proposal()
            db.review_proposal(p["id"], "Accepted")
            db.submit_result(p["id"], "Submission")
            with self.assertRaises(ValueError):
                db.leave_review(p["id"], rating, "  ")
            db.leave_review(p["id"], rating, "Acceptance case explained")
            self.assertEqual(db.team_stats("team-1")["xp"], max(0, xp))

    def test_agreement_snapshot_survives_task_edit(self):
        p = self.proposal()
        db.review_proposal(p["id"], "Accepted")
        original = db.load_records("proposals")[0]["agreement"]
        task = db.load_records("tasks")[0]
        task["success_criteria"] = "Completely different criteria"
        db.publish_task(task, True, task["id"])
        self.assertEqual(db.load_records("proposals")[0]["agreement"], original)

    def test_url_and_service_validation(self):
        for url in ("javascript:alert(1)", "file:///etc/passwd", "https://", "https://x y", "https://user:pass@example.com"):
            self.assertFalse(db.valid_url(url))
        self.assertTrue(db.valid_url("https://github.com/example/project"))
        with self.assertRaises(ValueError):
            db.submit_proposal("task-1", {"team_id": "team-1"})
        with self.assertRaises(ValueError):
            db.save_team("Campus Coders", [], [])
        with self.assertRaises(ValueError):
            db.load_records("../private")

    def test_corrupt_json_preserved(self):
        path = db.DATA_DIR / "tasks.json"
        path.write_text("corrupt", encoding="utf-8")
        with self.assertRaises(json.JSONDecodeError):
            db.add_record("tasks", {"title":"Test"})
        self.assertEqual(path.read_text(), "corrupt")

    def test_concurrent_writes_keep_every_proposal(self):
        with ThreadPoolExecutor(max_workers=8) as pool:
            list(pool.map(lambda _: self.proposal(), range(24)))
        self.assertEqual(len(db.load_records("proposals")), 24)
        self.assertEqual(len({p["id"] for p in db.load_records("proposals")}), 24)

    def test_matching_and_expectation_check(self):
        m = skill_match({"required_skills":["Python","React","NLP"]}, {"skills":["python","React.js"]})
        self.assertEqual(m["percent"], 67)
        self.assertIsNone(skill_match({}, {})["percent"])
        result = expectation_check({"expected_result":"Срочные уведомления управляющему"}, {"definition_of_done":"Еженедельный отчёт"})
        self.assertIn("уведомления", result["missing"])
        self.assertEqual(len(interpretations("Хотим AI для отзывов")), 3)

class UITests(Workspace):
    def app(self):
        app = AppTest.from_file(str(ROOT / "app.py"), default_timeout=30).run()
        self.assertFalse(app.exception)
        return app

    def test_all_pages_render(self):
        app = self.app()
        for name in ("Каталог задач","Кабинет бизнеса","Моя команда","Лидеры","О проекте","Конструктор"):
            app.radio(key="navigation").set_value(name).run()
            self.assertFalse(app.exception, name)

    def test_api_failure_preserves_manual_work(self):
        app = self.app()
        app.text_input(key="card_title").set_value("Мой черновик").run()
        app.text_area(key="business_description").set_value("Хотим AI для отзывов").run()
        app.radio(key="assistant_mode").set_value("OpenAI").run()
        from services.ai import AIError
        with patch("services.ai.analyze_task", side_effect=AIError("AI недоступен")):
            app.button(key="analyze").click().run()
        self.assertFalse(app.exception)
        self.assertTrue(app.error)
        self.assertEqual(app.text_input(key="card_title").value, "Мой черновик")
        self.assertTrue(app.button(key="publish").disabled)
        app.radio(key="assistant_mode").set_value("Локальный помощник").run()
        app.button(key="analyze").click().run()
        self.assertFalse(app.error)
        self.assertIn("Локальный", app.session_state["analysis"]["provider"])

    def test_corrupt_profiles_show_recoverable_error(self):
        (db.DATA_DIR / "teams.json").write_text("broken", encoding="utf-8")
        app = self.app()
        self.assertTrue(app.error)

    def test_team_registration(self):
        app = self.app()
        app.radio(key="navigation").set_value("Моя команда").run()
        app.text_input(key="new_team_name").set_value("Hackathon Team")
        app.multiselect(key="new_interests").set_value(["AI", "Web"])
        app.text_input(key="new_skills").set_value("Python, React")
        app.button(key="create_team").click().run()
        self.assertFalse(app.exception)
        created = db.load_records("teams")[-1]
        self.assertEqual(created["skills"], ["Python", "React"])
        self.assertEqual(app.session_state["active_team"], created["id"])

    def test_entire_hackathon_flow(self):
        app = self.app()
        self.assertTrue(app.button(key="publish").disabled)
        app.text_area(key="business_description").set_value("Хотим AI для анализа отзывов").run()
        app.multiselect(key="interpret_choices").set_value(["Срочные сигналы"]).run()
        app.button(key="analyze").click().run()
        self.assertFalse(app.exception)
        self.assertIn("уведомления", app.session_state["draft"]["expected_result"].lower())
        self.assertGreaterEqual(len(app.session_state["analysis"]["questions"]), 3)
        # Exercise clarification including an explicit unknown.
        version = app.session_state["analysis_version"]
        questions = app.session_state["analysis"]["questions"]
        for i, q in enumerate(questions):
            app.text_area(key=f"answer_{version}_{i}").set_value("пока не знаю" if q["field"] == "data_materials" else "Подтверждённая деталь бизнеса")
        next(b for b in app.button if b.label == "Собрать карточку из ответов").click().run()
        self.assertEqual(app.session_state["draft"]["data_materials"], "")
        app.text_input(key="card_title").set_value("UI Demo")
        for field, *_ in FIELDS:
            app.text_area(key=f"card_{field}").set_value("Конкретная деталь для " + field)
        app.run()
        self.assertEqual(task_readiness(app.session_state["draft"])["score"], 0)
        app.button(key="confirm_all").click().run()
        self.assertEqual(task_readiness(app.session_state["draft"])["score"], 100)
        app.checkbox(key="confirm_publish").check().run()
        app.text_area(key="card_constraints").set_value("Срок 3 недели").run()
        self.assertTrue(app.button(key="publish").disabled)
        self.assertEqual(task_readiness(app.session_state["draft"])["score"], 90)
        # Draft edits survive navigation.
        app.radio(key="navigation").set_value("Каталог задач").run()
        app.radio(key="navigation").set_value("Конструктор").run()
        self.assertEqual(app.text_area(key="card_constraints").value, "Срок 3 недели")
        app.button(key="confirm_all").click().run()
        app.checkbox(key="confirm_publish").check().run()
        app.button(key="publish").click().run()
        self.assertFalse(app.exception)
        published = db.load_records("tasks")[-1]
        self.assertEqual(published["readiness_score"], 100)
        tid = published["id"]
        app.radio(key="navigation").set_value("Каталог задач").run()
        scores = [int(e.label.split(" — ")[1].split("/")[0]) for e in app.expander]
        self.assertEqual(scores, sorted(scores, reverse=True))
        app.text_area(key=f"idea_{tid}").set_value("Решение")
        app.text_area(key=f"plan_{tid}").set_value("Собрать, проверить, передать")
        app.text_input(key=f"time_{tid}").set_value("2 недели")
        app.text_area(key=f"done_{tid}").set_value("Пройдены согласованные критерии")
        app.button(key=f"send_{tid}").click().run()
        self.assertFalse(app.exception)
        p = db.load_records("proposals")[-1]
        app.radio(key="navigation").set_value("Кабинет бизнеса").run()
        # Selection uses the real dict option.
        app.selectbox(key="business_task").set_value(published).run()
        app.button(key=f'accept_{p["id"]}').click().run()
        app.text_input(key=f'stage_{p["id"]}').set_value("Прототип")
        app.text_area(key=f'evidence_{p["id"]}').set_value("Проверены тестовые сценарии")
        app.button(key=f'confirm_stage_{p["id"]}').click().run()
        self.assertEqual(db.team_stats("team-1")["xp"], 10)
        app.radio(key="navigation").set_value("Моя команда").run()
        app.text_area(key=f'result_summary_{p["id"]}').set_value("Все критерии пройдены")
        app.button(key=f'submit_result_{p["id"]}').click().run()
        app.radio(key="navigation").set_value("Кабинет бизнеса").run()
        app.selectbox(key="business_task").set_value(published).run()
        app.text_area(key=f'review_text_{p["id"]}').set_value("Согласованные критерии выполнены")
        app.checkbox(key=f'review_confirm_{p["id"]}').check()
        app.button(key=f'review_submit_{p["id"]}').click().run()
        self.assertFalse(app.exception)
        self.assertEqual(db.team_stats("team-1")["xp"], 50)
        self.assertEqual(db.team_stats("team-1")["completed"], 1)

    def test_filters_empty_state_and_draft_access(self):
        app = self.app()
        app.radio(key="navigation").set_value("Каталог задач").run()
        app.selectbox(key="filter_level").set_value("Draft").run()
        self.assertTrue(app.expander)
        self.assertTrue(all("Draft" in e.label for e in app.expander))
        self.assertTrue(any(b.label == "Отправить предложение" for b in app.button))
        app.text_input(key="catalog_search").set_value("unfindable-xyz").run()
        self.assertFalse(app.expander)
        self.assertFalse(app.exception)

if __name__ == "__main__":
    unittest.main()
