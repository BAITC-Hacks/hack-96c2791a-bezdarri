"""Offline API-contract and full UI-flow tests. No credentials or live API calls."""

from copy import deepcopy
from contextlib import contextmanager
import json
import os
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest.mock import patch

import httpx
from openai import OpenAI
from streamlit.testing.v1 import AppTest
import streamlit as st

from services import ai, storage
from services.scoring import readiness_level

ROOT = Path(__file__).resolve().parent.parent
DESCRIPTION = "We run an online clothing store and many customers abandon their carts. We want students to help us understand why."
INITIAL = {key: "" for key in ai.TASK_KEYS}
INITIAL.update(title="online clothing store", context="We run an online clothing store",
               need="many customers abandon their carts")
DETAILS = {
    "users": "Store analysts and checkout designers",
    "data_materials": "12 months of anonymized GA4 events and order history are available as CSV",
    "constraints": "Two weeks, Python only, no personal customer data",
    "expected_result": "A funnel dashboard and three recommendations",
    "success_criteria": "Identify the top three exit steps and reproduce counts within 1% of source data",
    "contact": "Alex at alex@store.example, weekly video calls",
}


def response_for(task, scores):
    missing = [key for key, value in task.items() if not value]
    targets = missing or ["constraints", "success_criteria", "contact"]
    question_text = {
        "title": "Which business problem should the student project focus on?",
        "context": "At which checkout stage do clothing-store customers leave, if known?",
        "need": "What does the store need to learn about abandoned carts to decide its next steps?",
        "data_materials": "What behavioral or transaction data is available for shoppers who abandon checkout?",
        "expected_result": "What should students deliver to help your store act on the checkout findings?",
        "success_criteria": "What measurable reduction in cart abandonment would make this project successful?",
        "constraints": "What deadline or customer-data privacy limits apply to this checkout analysis?",
        "users": "Who will use the checkout findings, and how can students contact that team?",
        "contact": "How can students contact your store to discuss checkout findings?",
    }
    questions = [{"field": key, "question": question_text[key]} for key in targets[:5]]
    total = sum(scores)
    return {"task": deepcopy(task), "missing_fields": missing, "questions": questions,
            "scoring": {"total_score": total, "level": readiness_level(total), "breakdown": [
                {"category": name, "max_score": maximum, "score": points,
                 "reason": "Concrete detail supplied." if points else "No information supplied.",
                 "improvement": f"Clarify the scope of {name.lower()}."}
                for (name, maximum, _), points in zip(ai.RUBRIC, scores)]}}


class AITests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        for source in (ROOT / "data").glob("*.json"):
            shutil.copy(source, self.directory.name)
        self.patch = patch.object(storage, "DATA_DIR", Path(self.directory.name))
        self.patch.start()
        self.addCleanup(self.patch.stop)
        # Ignore local demo submissions; never assume live JSON files are pristine.
        storage.save_records("tasks", [task for task in storage.load_records("tasks") if task["id"] in {f"task-{i}" for i in range(1, 6)}])
        storage.save_records("proposals", [])
        self.requests = []
        self.responses = []

        def handle(request):
            self.requests.append(json.loads(request.content))
            body = self.responses.pop(0)
            if isinstance(body, Exception):
                raise body
            if isinstance(body, int):
                return httpx.Response(body, json={"error": {"message": "Do not display raw errors", "type": "api_error"}})
            if body == "refusal":
                return httpx.Response(200, json={"id": "resp_test", "object": "response", "created_at": 1,
                    "status": "completed", "model": "gpt-4o-mini", "output": [{"id": "msg_test", "type": "message",
                    "role": "assistant", "status": "completed", "content": [{"type": "refusal", "refusal": "Cannot help"}]}]})
            return httpx.Response(200, json={
                "id": "resp_test", "object": "response", "created_at": 1, "status": "completed",
                "model": "gpt-4o-mini", "output": [{"id": "msg_test", "type": "message", "role": "assistant",
                    "status": "completed", "content": [{"type": "output_text", "text": body if isinstance(body, str) else json.dumps(body), "annotations": []}]}],
            })

        def client(**kwargs):
            return OpenAI(**kwargs, http_client=httpx.Client(transport=httpx.MockTransport(handle)))

        for patcher in [patch.object(ai, "OpenAI", side_effect=client),
                        patch.object(ai, "load_dotenv"), patch.dict(os.environ, {"OPENAI_API_KEY": "test-placeholder"})]:
            patcher.start()
            self.addCleanup(patcher.stop)

    def test_validation_rejects_invalid_and_invented_results(self):
        good = response_for(INITIAL, [16, 0, 0, 0, 0, 0, 0])
        ai.validate_analysis(deepcopy(good), [DESCRIPTION])
        invalid = []
        bad = deepcopy(good); bad["scoring"]["total_score"] = 99; invalid.append(bad)
        bad = deepcopy(good); bad["scoring"]["level"] = "Priority"; invalid.append(bad)
        bad = deepcopy(good); bad["scoring"]["breakdown"][0]["score"] = 21; invalid.append(bad)
        bad = deepcopy(good); bad["scoring"]["breakdown"][0]["max_score"] = 30; invalid.append(bad)
        bad = deepcopy(good); bad["questions"] = bad["questions"][:2]; invalid.append(bad)
        for missing in (None, "users", [123], ["unrecognized_field"]):
            bad = deepcopy(good); bad["missing_fields"] = missing; invalid.append(bad)
        bad = deepcopy(good); bad["task"]["contact"] = "Email alex@invented.example"; invalid.append(bad)
        bad = deepcopy(good); bad["scoring"]["breakdown"][1]["score"] = 1; invalid.append(bad)
        bad = deepcopy(good); bad["scoring"]["breakdown"][1] = bad["scoring"]["breakdown"][0]; invalid.append(bad)
        bad = deepcopy(good); bad["task"] = []; invalid.append(bad)
        for result in invalid:
            with self.subTest(result=result), self.assertRaises(ValueError):
                ai.validate_analysis(result, [DESCRIPTION])

    def test_missing_fields_normalizes_omitted_blanks(self):
        task = {**INITIAL, "users": None, "data_materials": "", "contact": "   "}
        for reported in ([], ["data_materials"], ["need", "data_materials", "data_materials"]):
            with self.subTest(reported=reported):
                response = response_for(INITIAL, [16, 0, 0, 0, 0, 0, 0])
                response["task"] = deepcopy(task)
                response["missing_fields"] = reported
                scoring = deepcopy(response["scoring"])
                result = ai.validate_analysis(response, [DESCRIPTION])
                expected = list(dict.fromkeys(reported + [key for key in ai.TASK_KEYS if not (task[key] or "").strip()]))
                self.assertEqual(result["missing_fields"], expected)
                self.assertEqual(result["scoring"], scoring)
                self.assertEqual(result["task"]["users"], "")
                self.assertEqual(result["task"]["contact"], "")
                self.assertEqual(ai.validate_analysis(deepcopy(result), [DESCRIPTION]), result)

    def test_paraphrased_title_and_fields_are_accepted(self):
        task = {**INITIAL, "title": "Investigate cart abandonment",
                "context": "An online apparel retailer has customers leaving items in their carts.",
                "need": "Understand why shoppers abandon checkout with help from students."}
        result = ai.validate_analysis(response_for(task, [16, 0, 0, 0, 0, 0, 0]), [DESCRIPTION])
        self.assertEqual(result["task"], task)
        self.assertGreaterEqual(len(result["questions"]), 3)
        self.assertEqual(result["task"]["data_materials"], "")

    def test_all_unknown_categories_stay_missing_and_score_zero(self):
        full_task = {**INITIAL, **DETAILS}
        for mode in ("draft", "clarify", "rescore"):
            for index, (category, maximum, fields) in enumerate(ai.RUBRIC):
                for blank in (None, "", "   "):
                    with self.subTest(mode=mode, category=category, blank=blank):
                        task = {**full_task, **{field: blank for field in fields}}
                        scores = [row[1] for row in ai.RUBRIC]
                        scores[index] = 0
                        response = response_for(task, scores)
                        # The normalizer must recover missing fields, not infer 'none'.
                        response["missing_fields"] = []
                        sources = [value for value in task.values() if value and value.strip()]
                        result = ai.validate_analysis(response, sources, mode=mode)
                        for field in fields:
                            self.assertEqual(result["task"][field], "")
                            self.assertIn(field, result["missing_fields"])
                        self.assertEqual(result["scoring"]["breakdown"][index]["score"], 0)
                        self.assertEqual(result["scoring"]["total_score"], 100 - maximum)

                        # Even with consistent arithmetic, missing facts cannot earn points.
                        bad = deepcopy(result)
                        bad["scoring"]["breakdown"][index]["score"] = maximum
                        bad["scoring"]["total_score"] = 100
                        bad["scoring"]["level"] = "Priority"
                        with self.assertRaises(ValueError):
                            ai.validate_analysis(bad, sources, mode=mode)

    def test_explicit_no_constraints_is_supplied_information(self):
        statement = "There are no constraints."
        task = {**INITIAL, "constraints": statement}
        self.responses.append(response_for(task, [16, 0, 0, 0, 5, 0, 0]))
        result = ai.analyze_task(DESCRIPTION + " " + statement)
        self.assertEqual(result["task"]["constraints"], statement)
        self.assertNotIn("constraints", result["missing_fields"])
        row = next(row for row in result["scoring"]["breakdown"] if row["category"] == "Constraints")
        self.assertEqual(row["score"], 5)  # Explicit absence need not receive full marks.

    def test_absence_policy_is_sent_in_every_analysis_mode(self):
        # Check the prompt contract sent to OpenAI; mocked responses cannot prove
        # a live model's semantic compliance with this instruction.
        for mode in ("draft", "clarify", "rescore"):
            with self.subTest(mode=mode):
                response = response_for(INITIAL, [16, 0, 0, 0, 0, 0, 0])
                self.responses.append(response)
                result = ai.analyze_task(DESCRIPTION, current_task=INITIAL, mode=mode)
                instructions = self.requests[-1]["instructions"]
                self.assertIn("ABSENCE OF INFORMATION MUST NEVER BE INTERPRETED AS ABSENCE OF CONSTRAINTS.", instructions)
                self.assertIn("'Not mentioned' means UNKNOWN", instructions)
                self.assertIn("no constraints mentioned -> constraints=null, 0/10, missing", instructions)
                self.assertIn("no data mentioned -> data_materials=null, 0/20, missing", instructions)
                self.assertIn("no contact mentioned -> contact=null, 0/10, missing", instructions)
                for field in ("constraints", "data_materials", "contact"):
                    self.assertEqual(result["task"][field], "")
                    self.assertIn(field, result["missing_fields"])

    def test_unsupported_specifics_are_rejected_but_supplied_ones_allow_rewording(self):
        for key, value in [("contact", "Email alex@invented.example"),
                           ("data_materials", "Download at https://invented.example/data"),
                           ("constraints", "Finish within 14 days"),
                           ("success_criteria", "Reduce abandonment by 25%")]:
            with self.subTest(key=key), self.assertRaisesRegex(ValueError, "unsupported"):
                ai.validate_analysis(response_for({**INITIAL, key: value}, [16, 0, 0, 0, 0, 0, 0]), [DESCRIPTION])
        task = {**INITIAL, "contact": "Contact: alex@store.example (weekly video check-in)",
                "constraints": "Complete the project in 14 days"}
        ai.validate_analysis(response_for(task, [16, 0, 0, 0, 5, 0, 5]),
                             [DESCRIPTION, "We have 14 days. Email alex@store.example for weekly video calls."])

    def test_question_count_depends_on_missing_information(self):
        task = {**INITIAL, **DETAILS}
        result = response_for(task, [16, 16, 12, 12, 7, 8, 7])
        result["questions"] = []
        ai.validate_analysis(result, list(task.values()))
        task["contact"] = ""
        result = response_for(task, [16, 16, 12, 12, 7, 8, 0])
        self.assertEqual(len(result["questions"]), 1)
        ai.validate_analysis(result, list(task.values()))

    def test_three_to_five_questions_allow_uncovered_missing_fields(self):
        for count in (3, 4, 5):
            with self.subTest(count=count):
                response = response_for(INITIAL, [16, 0, 0, 0, 0, 0, 0])
                response["questions"] = response["questions"][:count]
                result = ai.validate_analysis(response, [DESCRIPTION])
                self.assertEqual(len(result["questions"]), count)
                self.assertIn("contact", result["missing_fields"])
                self.assertEqual(result["task"]["contact"], "")
                self.assertNotIn("contact", [question["field"] for question in result["questions"]])

    def test_question_limits_reject_two_or_six_for_an_incomplete_brief(self):
        response = response_for(INITIAL, [16, 0, 0, 0, 0, 0, 0])
        response["questions"] = response["questions"][:2]
        with self.assertRaisesRegex(ValueError, "Too few"):
            ai.validate_analysis(response, [DESCRIPTION])
        response = response_for(INITIAL, [16, 0, 0, 0, 0, 0, 0])
        response["questions"].append({"field": "contact", "question": "How can students reach the store manager?"})
        with self.assertRaisesRegex(ValueError, "More than five"):
            ai.validate_analysis(response, [DESCRIPTION])

    def test_draft_rejects_fewer_than_three_questions_with_significant_gaps(self):
        for count in (0, 1, 2):
            with self.subTest(count=count):
                response = response_for(INITIAL, [16, 0, 0, 0, 0, 0, 0])
                response["questions"] = response["questions"][:count]
                with self.assertRaisesRegex(ValueError, "Too few"):
                    ai.validate_analysis(response, [DESCRIPTION], mode="draft")

    def test_clarify_accepts_zero_one_or_two_questions_despite_remaining_gaps(self):
        for count in (0, 1, 2):
            with self.subTest(count=count):
                response = response_for(INITIAL, [16, 0, 0, 0, 0, 0, 0])
                response["questions"] = response["questions"][:count]
                result = ai.validate_analysis(response, [DESCRIPTION], mode="clarify")
                self.assertEqual(len(result["questions"]), count)
                self.assertGreaterEqual(len(result["missing_fields"]), 3)
                self.assertEqual(result["scoring"]["total_score"], 16)

    def test_clarify_keeps_question_types_maximum_and_score_validation(self):
        good = response_for(INITIAL, [16, 0, 0, 0, 0, 0, 0])
        invalid = []
        bad = deepcopy(good); bad["questions"] = None; invalid.append(bad)
        bad = deepcopy(good); bad["questions"].append({"field": "contact", "question": "How can students reach the store?"}); invalid.append(bad)
        bad = deepcopy(good); bad["questions"] = []; bad["scoring"]["total_score"] = 101; invalid.append(bad)
        bad = deepcopy(good); bad["questions"] = []; bad["scoring"]["breakdown"][0]["score"] = 21; invalid.append(bad)
        bad = deepcopy(good); bad["questions"] = []; bad["scoring"]["breakdown"][0]["max_score"] = 30; invalid.append(bad)
        bad = deepcopy(good); bad["questions"] = []; bad["scoring"]["total_score"] = 15; invalid.append(bad)
        bad = deepcopy(good); bad["questions"] = []; bad["task"]["context"] = 123; invalid.append(bad)
        bad = deepcopy(good); bad["questions"] = []; bad["task"]["contact"] = "invented@store.example"; invalid.append(bad)
        for response in invalid:
            with self.subTest(response=response), self.assertRaises(ValueError):
                ai.validate_analysis(response, [DESCRIPTION], mode="clarify")

    def test_clarify_uses_original_description_all_answers_and_current_card(self):
        self.responses.append(response_for(INITIAL, [16, 0, 0, 0, 0, 0, 0]))
        app = AppTest.from_file(str(ROOT / "app.py")).run()
        app.sidebar.radio[0].set_value("Create Task").run()
        app.text_area(key="business_description").set_value(DESCRIPTION)
        app.button(key="analyze").click().run()
        app.text_area(key="card_constraints").set_value(DETAILS["constraints"]).run()
        current_card = deepcopy(app.session_state["draft"])
        question = app.session_state["analysis"]["questions"][0]
        self.assertEqual(question["field"], "data_materials")
        app.text_area(key="answer_1_0").set_value(DETAILS["data_materials"])
        updated = {**current_card, "data_materials": DETAILS["data_materials"]}
        first = response_for(updated, [16, 16, 0, 0, 7, 0, 0])
        first["questions"] = first["questions"][:1]
        self.responses.append(first)
        app.button(key="clarify").click().run()
        self.assertFalse(app.error)
        payload = json.loads(self.requests[-1]["input"])
        self.assertEqual(payload["mode"], "clarify")
        self.assertEqual(payload["description"], DESCRIPTION)
        self.assertEqual(payload["current_card"], current_card)
        self.assertEqual(payload["answers"], [{**question, "answer": DETAILS["data_materials"]}])
        first_answers = deepcopy(payload["answers"])

        # A second round must retain earlier answers and use the latest manual card.
        app.text_area(key="card_contact").set_value(DETAILS["contact"]).run()
        app.text_area(key="business_description").set_value("Unsubmitted replacement description").run()
        current_card = deepcopy(app.session_state["draft"])
        question = app.session_state["analysis"]["questions"][0]
        app.text_area(key="answer_2_0").set_value(DETAILS[question["field"]])
        updated = {**current_card, question["field"]: DETAILS[question["field"]]}
        second = response_for(updated, [16, 16, 12, 0, 7, 0, 7])
        second["questions"] = []
        self.responses.append(second)
        app.button(key="clarify").click().run()
        self.assertFalse(app.exception)
        self.assertFalse(app.error)
        payload = json.loads(self.requests[-1]["input"])
        self.assertEqual(payload["description"], DESCRIPTION)
        self.assertEqual(payload["current_card"], current_card)
        self.assertEqual(payload["answers"], first_answers + [{**question, "answer": DETAILS[question["field"]]}])
        self.assertEqual(app.session_state["analysis"]["questions"], [])
        self.assertEqual(app.session_state["analysis"]["scoring"]["total_score"], 58)
        self.assertEqual(app.session_state["draft"], updated)

    def test_question_minimum_also_applies_to_weak_nonempty_fields(self):
        task = {**INITIAL, **DETAILS}
        response = response_for(task, [16, 16, 12, 12, 7, 8, 7])
        response["missing_fields"] = ["data_materials", "expected_result", "success_criteria"]
        response["questions"] = response["questions"][:2]
        with self.assertRaisesRegex(ValueError, "Too few"):
            ai.validate_analysis(response, list(task.values()))

    def test_rescore_still_preserves_manual_edits(self):
        result = response_for(INITIAL, [16, 0, 0, 0, 0, 0, 0])
        result["task"]["title"] = "Investigate abandoned shopping carts"
        with self.assertRaisesRegex(ValueError, "manually edited"):
            ai.validate_analysis(result, [DESCRIPTION], current_task=INITIAL)

    def test_safe_errors_and_missing_key(self):
        with patch.dict(os.environ, {"OPENAI_API_KEY": ""}), self.assertRaisesRegex(ai.AIError, "Configure OPENAI_API_KEY"):
            ai.analyze_task(DESCRIPTION)
        for response in [401, 429, 500, {"invalid": "data"}, "not JSON", "refusal", httpx.ReadTimeout("Private error")]:
            self.responses.append(response)
            with self.assertRaises(ai.AIError) as caught:
                ai.analyze_task(DESCRIPTION)
            self.assertNotIn("test-placeholder", str(caught.exception))
            self.assertNotIn("Do not display", str(caught.exception))

    def test_exception_logging_redacts_credentials_and_keeps_cause(self):
        key = "sk-test-secret-for-redaction"
        error = ai.OpenAIError(f"Incorrect API key: {key}; masked: sk-test***tion; Authorization: Bearer private-token")
        error.__cause__ = ConnectionError("Underlying connection failure")
        with patch.object(ai, "OpenAI", side_effect=error), patch.dict(os.environ, {"OPENAI_API_KEY": key}):
            with self.assertLogs("services.ai", level="ERROR") as logs, self.assertRaises(ai.AIError):
                ai.analyze_task(DESCRIPTION)
        output = "\n".join(logs.output)
        self.assertIn("Incorrect API key", output)
        self.assertIn("Underlying connection failure", output)
        self.assertIn("[REDACTED]", output)
        for secret in (key, "sk-test***tion", "private-token"):
            self.assertNotIn(secret, output)

    def test_missing_key_keeps_manual_card_and_never_publishes(self):
        app = AppTest.from_file(str(ROOT / "app.py")).run()
        app.sidebar.radio[0].set_value("Create Task").run()
        app.text_input(key="card_title").set_value("Manual draft").run()
        app.text_area(key="business_description").set_value(DESCRIPTION)
        with patch.dict(os.environ, {"OPENAI_API_KEY": ""}):
            app.button(key="analyze").click().run()
        self.assertFalse(app.exception)
        self.assertTrue(app.error)
        self.assertEqual(app.text_input(key="card_title").value, "Manual draft")
        self.assertEqual(len(self.requests), 0)
        self.assertEqual(len(storage.load_records("tasks")), 5)

    def test_successful_result_survives_rerun_during_spinner_cleanup(self):
        self.responses.append(response_for(INITIAL, [16, 0, 0, 0, 0, 0, 0]))
        app = AppTest.from_file(str(ROOT / "app.py")).run()
        app.sidebar.radio[0].set_value("Create Task").run()
        app.text_area(key="business_description").set_value(DESCRIPTION)

        @contextmanager
        def interrupted_spinner(*args, **kwargs):
            yield
            # A queued rerun can be serviced when spinner cleanup sends a delta.
            st.rerun()

        with patch("streamlit.spinner", interrupted_spinner):
            app.button(key="analyze").click().run()
        for _ in range(3):
            self.assertFalse(app.exception)
            self.assertFalse(app.error)
            self.assertEqual(app.session_state["analysis_version"], 1)
            self.assertEqual(app.session_state["analysis"]["scoring"]["total_score"], 16)
            self.assertEqual(app.text_area(key="business_description").value, DESCRIPTION)
            self.assertEqual(app.session_state["analyzed_description"], DESCRIPTION)
            self.assertTrue(any(metric.value == "16/100" and metric.delta == "Черновик" for metric in app.metric))
            self.assertTrue(any("Можно уточнить ещё" in caption.value for caption in app.caption))
            self.assertEqual(len(app.table), 1)
            for i, question in enumerate(app.session_state["analysis"]["questions"]):
                self.assertEqual(app.text_area(key=f"answer_1_{i}").label, question["question"])
            app.run()
        self.assertEqual(len(self.requests), 1)
        self.assertEqual(len(storage.load_records("tasks")), 5)

    def test_ai_to_publish_proposal_and_manual_review(self):
        initial_response = response_for(INITIAL, [16, 0, 0, 0, 0, 0, 0])
        initial_response["task"]["users"] = None
        initial_response["missing_fields"].remove("users")
        self.responses.append(initial_response)
        app = AppTest.from_file(str(ROOT / "app.py"), default_timeout=30).run()
        app.sidebar.radio[0].set_value("Create Task").run()
        app.text_area(key="business_description").set_value(DESCRIPTION)
        app.button(key="analyze").click().run()
        self.assertFalse(app.exception)
        self.assertEqual(len(self.requests), 1)
        self.assertTrue(self.requests[0]["text"]["format"]["strict"])
        self.assertFalse(self.requests[0]["store"])
        self.assertEqual(app.session_state["analysis"]["scoring"]["total_score"], 16)
        self.assertIn("users", app.session_state["analysis"]["missing_fields"])
        self.assertFalse(app.error)
        self.assertTrue(any(item.value == "Уточним детали" for item in app.subheader))
        self.assertEqual(app.text_area(key="card_data_materials").value, "")
        self.assertGreaterEqual(len(app.session_state["analysis"]["questions"]), 3)
        self.assertLessEqual(len(app.session_state["analysis"]["questions"]), 5)
        self.assertEqual(len(storage.load_records("tasks")), 5)
        self.assertTrue(app.button(key="publish").disabled)

        improved = {**INITIAL, **DETAILS}
        for i, question in enumerate(app.session_state["analysis"]["questions"]):
            answer = DETAILS[question["field"]]
            if question["field"] == "users":
                answer += ". " + DETAILS["contact"]  # One answer clarifies users and contact.
            app.text_area(key=f"answer_1_{i}").set_value(answer)
        self.responses.append(response_for(improved, [16, 16, 12, 12, 7, 8, 7]))
        app.button(key="clarify").click().run()
        self.assertFalse(app.exception)
        self.assertEqual(app.session_state["analysis"]["scoring"]["total_score"], 78)
        self.assertEqual(app.session_state["previous_score"], 16)
        payload = json.loads(self.requests[-1]["input"])
        self.assertEqual(payload["description"], DESCRIPTION)
        self.assertEqual(len(payload["answers"]), 5)
        self.assertIn(DETAILS["contact"], payload["answers"][-1]["answer"])
        self.assertTrue(any(metric.value == "16 → 78" for metric in app.metric))

        # Manual edits invalidate the prior score, survive navigation and API errors.
        app.text_area(key="card_constraints").set_value("Three weeks, Python only").run()
        self.assertTrue(app.button(key="publish").disabled)
        app.sidebar.radio[0].set_value("Catalog").run()
        app.sidebar.radio[0].set_value("Create Task").run()
        self.assertEqual(app.text_area(key="card_constraints").value, "Three weeks, Python only")
        self.responses.append(500)
        app.button(key="rescore").click().run()
        self.assertTrue(app.error)
        self.assertTrue(app.button(key="publish").disabled)
        improved["constraints"] = "Three weeks, Python only"
        self.responses.append(response_for(improved, [16, 16, 12, 12, 7, 8, 7]))
        app.button(key="rescore").click().run()
        self.assertFalse(app.exception)
        self.assertFalse(app.error)
        app.checkbox(key="confirm_publish").check().run()
        app.button(key="publish").click().run()
        published = storage.load_records("tasks")[-1]
        self.assertEqual(published["readiness_score"], 78)
        self.assertEqual(published["ai_analysis"]["scoring"]["total_score"], 78)

        app.sidebar.radio[0].set_value("Catalog").run()
        labels = [expander.label for expander in app.expander if " — " in expander.label]
        scores = [int(label.split(" — ")[1].split("/")[0]) for label in labels]
        self.assertEqual(scores, [100, 90, 78, 75, 55, 30])
        # The saved quality score is 78, even though every field is filled (checklist 100).
        target = next(expander for expander in app.expander if "online clothing store — 78" in expander.label)
        task_id = published["id"]
        target.text_input(key=f"team_{task_id}").set_value("Campus Coders")
        target.text_input(key=f"timeline_{task_id}").set_value("Two weeks")
        target.text_area(key=f"idea_{task_id}").set_value("Analyze funnel events")
        target.text_area(key=f"plan_{task_id}").set_value("Clean data, compare segments, present findings")
        target.text_area(key=f"done_{task_id}").set_value("The business can inspect findings about checkout drop-off")
        target.button(key=f"proposal_submit_{task_id}").click().run()
        proposal = storage.load_records("proposals")[-1]
        self.assertEqual(proposal["task_id"], published["id"])
        self.assertEqual(proposal["status"], "Pending")
        app.sidebar.radio[0].set_value("Business Dashboard").run()
        app.button(key=f"accept_{proposal['id']}").click().run()
        self.assertEqual(storage.load_records("proposals")[-1]["status"], "Accepted")
        app.button(key=f"reject_{proposal['id']}").click().run()
        self.assertEqual(storage.load_records("proposals")[-1]["status"], "Rejected")
        self.assertFalse(app.exception)
        self.assertEqual(len(self.requests), 4)  # No requests for publish, catalog, or review.


if __name__ == "__main__":
    unittest.main()
