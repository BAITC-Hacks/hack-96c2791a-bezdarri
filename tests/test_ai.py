"""Real SDK with mocked HTTP: no credentials, network, or API charges."""
import json
import os
import unittest
from unittest.mock import patch
import httpx
from openai import OpenAI
from services import ai
from services.scoring import TASK_KEYS

DESCRIPTION = "Хотим AI для анализа отзывов"
def result():
    task = {k: "" for k in TASK_KEYS}
    task.update(title="Анализ отзывов", context=DESCRIPTION)
    return {"task":task, "questions":[{"field":k,"question":ai.QUESTIONS[k]} for k in ("users","data_materials","success_criteria")]}

class AITests(unittest.TestCase):
    def test_local_unknowns_and_dynamic_questions(self):
        draft = ai.local_analysis(DESCRIPTION)
        self.assertIn("Локальный", draft["provider"])
        self.assertEqual(draft["task"]["data_materials"], "")
        self.assertTrue(3 <= len(draft["questions"]) <= 5)
        updated = ai.local_analysis(DESCRIPTION, [{"field":"data_materials","answer":"пока не знаю"}], draft["task"])
        self.assertEqual(updated["task"]["data_materials"], "")
        updated = ai.local_analysis(DESCRIPTION, [{"field":"data_materials","answer":"300 отзывов в CSV"}], draft["task"])
        self.assertEqual(updated["task"]["data_materials"], "300 отзывов в CSV")
        self.assertNotIn("data_materials", [q["field"] for q in updated["questions"]])

    def test_schema_and_grounding_guards(self):
        ai.validate_analysis(result(), [DESCRIPTION])
        for change in (
            lambda r: r["task"].update(contact="invented@example.com"),
            lambda r: r["task"].update(constraints="14 дней"),
            lambda r: r.update(questions=[]),
            lambda r: r.update(questions=[r["questions"][0]]*3),
            lambda r: r["task"].pop("users"),
            lambda r: r.update(scoring=100),
        ):
            r = result()
            change(r)
            with self.assertRaises(ValueError):
                ai.validate_analysis(r, [DESCRIPTION])

    def test_rescore_preserves_manual_card(self):
        r = result()
        edited = {**r["task"], "title":"Manual title"}
        with self.assertRaises(ValueError):
            ai.validate_analysis(r, [DESCRIPTION], edited)

    def call_with(self, body, code=200):
        requests = []
        def handle(request):
            requests.append(json.loads(request.content))
            if code != 200:
                return httpx.Response(code, json={"error":{"message":"private detail","type":"api_error"}})
            return httpx.Response(200,json={"id":"resp_test","object":"response","created_at":1,"status":"completed","model":"gpt-4o-mini",
                "output":[{"id":"msg_test","type":"message","role":"assistant","status":"completed","content":[{"type":"output_text","text":json.dumps(body) if not isinstance(body,str) else body,"annotations":[]}]}]})
        def client(**kwargs):
            return OpenAI(**kwargs,http_client=httpx.Client(transport=httpx.MockTransport(handle)))
        with patch.object(ai,"OpenAI",side_effect=client), patch.object(ai,"load_dotenv"), patch.dict(os.environ,{"OPENAI_API_KEY":"test-placeholder"}):
            response = ai.analyze_task(DESCRIPTION)
        return response, requests

    def test_valid_api_response_and_privacy_contract(self):
        response, requests = self.call_with(result())
        self.assertEqual(response["task"]["context"], DESCRIPTION)
        self.assertIn("OpenAI", response["provider"])
        self.assertFalse(requests[0]["store"])
        self.assertTrue(requests[0]["text"]["format"]["strict"])
        self.assertNotIn("test-placeholder", requests[0]["input"])

    def test_invalid_api_and_safe_failures(self):
        for body, code in [("not json",200), ({"invalid":True},200), ({},401), ({},429), ({},500)]:
            with self.subTest(code=code), self.assertRaises(ai.AIError) as caught:
                self.call_with(body,code)
            self.assertNotIn("private detail", str(caught.exception))
            self.assertNotIn("test-placeholder", str(caught.exception))
        with patch.object(ai,"load_dotenv"), patch.dict(os.environ,{"OPENAI_API_KEY":""}), self.assertRaises(ai.AIError):
            ai.analyze_task(DESCRIPTION)

if __name__ == "__main__":
    unittest.main()
