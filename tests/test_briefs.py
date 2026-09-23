"""Contract and failure tests for optional suggestions, without live API calls."""

from copy import deepcopy
import json
import os
import unittest
from unittest.mock import patch

import httpx
from openai import OpenAI

from services import briefs
from services.ai import AIError


DESCRIPTION = "We want to understand customer reviews and notice urgent complaints."
TASK = {"expected_result": "Immediate notifications about urgent complaints",
        "success_criteria": "Notify the manager when an urgent complaint appears"}
PROPOSAL = {"definition_of_done": "A weekly report of feedback themes",
            "plan": "Read reviews, group themes and produce a report"}
COMPARISON = {
    "summary": "The delivery frequency needs agreement before work starts.",
    "agreements": ["Both the business and the team discuss customer feedback."],
    "gaps": ["The business asks for 'Immediate notifications'; the team proposes 'A weekly report'."],
    "questions": ["Should urgent complaints trigger immediate alerts or appear in the weekly report?"],
}


class BriefTests(unittest.TestCase):
    def setUp(self):
        self.requests = []
        self.responses = []

        def handle(request):
            self.requests.append(json.loads(request.content))
            body = self.responses.pop(0)
            if isinstance(body, Exception):
                raise body
            if isinstance(body, int):
                return httpx.Response(body, json={"error": {"message": "Private provider detail", "type": "api_error"}})
            status = "incomplete" if body == "incomplete" else "completed"
            if body == "refusal":
                content = [{"type": "refusal", "refusal": "Private refusal detail"}]
            else:
                content = [{"type": "output_text", "text": body if isinstance(body, str) else json.dumps(body), "annotations": []}]
            return httpx.Response(200, json={
                "id": "resp_test", "object": "response", "created_at": 1, "status": status,
                "model": "gpt-4o-mini", "output": [{"id": "msg_test", "type": "message", "role": "assistant",
                    "status": "completed", "content": content}],
            })

        def client(**kwargs):
            return OpenAI(**kwargs, http_client=httpx.Client(transport=httpx.MockTransport(handle)))

        for patcher in (patch.object(briefs, "OpenAI", side_effect=client),
                        patch.object(briefs, "load_dotenv"),
                        patch.dict(os.environ, {"OPENAI_API_KEY": "test-placeholder", "OPENAI_MODEL": "gpt-4o-mini"})):
            patcher.start()
            self.addCleanup(patcher.stop)

    def interpretations_response(self):
        result = briefs.generate_interpretations(DESCRIPTION, use_ai=False)
        result.pop("source")
        return result

    def test_interpretations_api_contract_and_no_implicit_selection(self):
        self.responses.append(self.interpretations_response())
        result = briefs.generate_interpretations(DESCRIPTION)
        self.assertEqual(result["source"], "AI")
        self.assertEqual(len(result["interpretations"]), 3)
        request = self.requests[0]
        self.assertEqual(request["model"], "gpt-4o-mini")
        self.assertFalse(request["store"])
        self.assertTrue(request["text"]["format"]["strict"])
        self.assertEqual(json.loads(request["input"]), {"description": DESCRIPTION})
        self.assertIn("unconfirmed hypothesis", request["instructions"])
        self.assertIn("untrusted project data", request["instructions"])
        self.assertNotIn("selected", result)

    def test_comparison_uses_only_relevant_fields_and_does_not_mutate_inputs(self):
        task = {**TASK, "contact": "private@business.example", "id": "private-id"}
        proposal = {**PROPOSAL, "team_name": "Private Team", "status": "Pending"}
        original_task, original_proposal = deepcopy(task), deepcopy(proposal)
        self.responses.append(deepcopy(COMPARISON))
        result = briefs.check_expectations(task, proposal)
        self.assertEqual(result, {"source": "AI", **COMPARISON})
        payload = json.loads(self.requests[0]["input"])
        self.assertEqual(payload, {"business": TASK, "team": PROPOSAL})
        self.assertNotIn("private", self.requests[0]["input"])
        self.assertEqual(task, original_task)
        self.assertEqual(proposal, original_proposal)
        self.assertFalse(self.requests[0]["store"])
        self.assertNotIn("winner", result)
        self.assertNotIn("score", result)

    def test_offline_is_explicit_and_never_opens_provider(self):
        with patch.object(briefs, "OpenAI", side_effect=AssertionError("No API permitted")):
            english = briefs.generate_interpretations(DESCRIPTION, use_ai=False)
            russian = briefs.generate_interpretations("Хотим анализировать отзывы", use_ai=False)
            generic = briefs.generate_interpretations("We want to improve a process", use_ai=False)
            comparison = briefs.check_expectations({}, {}, use_ai=False)
        self.assertEqual(english, russian)
        self.assertNotEqual(english["interpretations"], generic["interpretations"])
        self.assertEqual(comparison["source"], "Guided templates")
        self.assertEqual(comparison["agreements"], [])
        self.assertEqual(len(comparison["gaps"]), 4)
        self.assertEqual(len(comparison["questions"]), 4)
        self.assertEqual(self.requests, [])

    def test_local_comparison_never_claims_semantic_alignment_from_shared_words(self):
        result = briefs.check_expectations(TASK, PROPOSAL, use_ai=False)
        self.assertEqual(result["agreements"], [])
        self.assertEqual(result["gaps"], [])
        self.assertGreaterEqual(len(result["questions"]), 3)
        self.assertIn("Meaning", result["summary"])
        same = briefs.check_expectations(TASK, {**PROPOSAL, "definition_of_done": TASK["expected_result"]}, use_ai=False)
        self.assertEqual(len(same["agreements"]), 1)
        self.assertIn("exactly", same["agreements"][0])

    def test_malformed_or_unsupported_interpretations_are_rejected(self):
        good = self.interpretations_response()
        bad_results = [None, [], {"interpretations": []}, {**good, "selected": True}]
        for value in (None, "", "x" * 801, "Use https://invented.example/data", "Deliver within 14 days"):
            bad = deepcopy(good)
            bad["interpretations"][0]["outcome"] = value
            bad_results.append(bad)
        bad = deepcopy(good)
        bad["interpretations"][1]["title"] = bad["interpretations"][0]["title"]
        bad_results.append(bad)
        bad = deepcopy(good)
        bad["interpretations"][1]["outcome"] = bad["interpretations"][0]["outcome"]
        bad_results.append(bad)
        for bad in bad_results:
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                briefs.validate_interpretations(bad, DESCRIPTION)

    def test_comparison_validation_rejects_invented_metrics_or_agreement_without_evidence(self):
        payload = {"business": TASK, "team": PROPOSAL}
        invalid = [{**COMPARISON, "score": 100}, {**COMPARISON, "gaps": "missing"},
                   {**COMPARISON, "summary": "Achieve 95% accuracy"},
                   {**COMPARISON, "questions": ["Question?"] * 6},
                   {**COMPARISON, "agreements": ["same", "same"]},
                   {**COMPARISON, "summary": ""}]
        for result in invalid:
            with self.subTest(result=result), self.assertRaises(ValueError):
                briefs.validate_comparison(result, payload)
        payload["business"] = {"expected_result": "", "success_criteria": ""}
        with self.assertRaises(ValueError):
            briefs.validate_comparison(COMPARISON, payload)

    def test_provider_failures_refusal_and_incomplete_return_safe_errors(self):
        for body in (401, 429, 500, "not JSON", "refusal", "incomplete", {"invalid": "data"}, httpx.ReadTimeout("Private detail")):
            with self.subTest(body=body):
                self.responses.append(body)
                with self.assertRaises(AIError) as caught:
                    briefs.generate_interpretations(DESCRIPTION)
                self.assertIn("Guided templates", str(caught.exception))
                self.assertNotIn("Private", str(caught.exception))
                self.assertNotIn("test-placeholder", str(caught.exception))
        self.assertEqual(len(self.requests), 8)

    def test_missing_key_and_invalid_input_do_not_make_requests(self):
        with patch.dict(os.environ, {"OPENAI_API_KEY": ""}), self.assertRaisesRegex(AIError, "Configure"):
            briefs.generate_interpretations(DESCRIPTION)
        for text in ("", "  ", None, 42, "x" * (briefs.MAX_INPUT + 1)):
            with self.subTest(text=str(text)[:30]), self.assertRaises(ValueError):
                briefs.generate_interpretations(text)
        with self.assertRaises(ValueError):
            briefs.check_expectations({"expected_result": False}, PROPOSAL)
        self.assertEqual(self.requests, [])


if __name__ == "__main__":
    unittest.main()
