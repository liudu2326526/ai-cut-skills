from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest.mock import patch


REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "scripts"))

import ai_review_agent  # noqa: E402


def advisory_review(head_sha: str) -> dict:
    return {
        "reviewed_head_sha": head_sha,
        "summary": "No concrete issue found in the supplied change.",
        "findings": [],
        "limitations": [],
    }


class AiReviewAgentTests(unittest.TestCase):
    def test_base_url_requires_https_without_embedded_credentials(self) -> None:
        self.assertEqual(
            ai_review_agent.normalize_base_url("https://example.test/v1/"),
            "https://example.test/v1",
        )
        for value in ("http://example.test/v1", "https://user:pass@example.test/v1"):
            with self.subTest(value=value), self.assertRaises(ai_review_agent.AiReviewError):
                ai_review_agent.normalize_base_url(value)

    def test_advisory_review_must_match_head(self) -> None:
        head_sha = "a" * 40
        self.assertEqual(
            ai_review_agent.validate_review_shape(advisory_review(head_sha), head_sha)["reviewed_head_sha"],
            head_sha,
        )
        mismatched = advisory_review("b" * 40)
        with self.assertRaisesRegex(ai_review_agent.AiReviewError, "head SHA"):
            ai_review_agent.validate_review_shape(mismatched, head_sha)

    def test_timeout_defaults_and_bounds(self) -> None:
        self.assertEqual(
            ai_review_agent.parse_timeout_seconds(None),
            ai_review_agent.DEFAULT_TIMEOUT_SECONDS,
        )
        self.assertEqual(ai_review_agent.parse_timeout_seconds("480"), 480)
        for value in ("29", "901", "not-a-number"):
            with self.subTest(value=value), self.assertRaises(ai_review_agent.AiReviewError):
                ai_review_agent.parse_timeout_seconds(value)

    def test_legacy_merge_decisions_are_rejected(self) -> None:
        head_sha = "a" * 40
        review = advisory_review(head_sha)
        review["decision"] = "block"
        with self.assertRaisesRegex(ai_review_agent.AiReviewError, "schema"):
            ai_review_agent.validate_review_shape(review, head_sha)

    def test_high_severity_findings_and_limitations_are_valid_advice(self) -> None:
        head_sha = "a" * 40
        for severity in ("P0", "P1", "P2", "P3"):
            with self.subTest(severity=severity):
                review = advisory_review(head_sha)
                review["findings"] = [{
                    "severity": severity, "path": "skills/demo/run.py", "line": 5,
                    "title": "Unsafe deletion", "detail": "Restrict the deletion target.",
                }]
                review["limitations"] = ["Only the supplied patch was reviewed."]
                self.assertEqual(ai_review_agent.validate_review_shape(review, head_sha), review)

    def test_limitations_must_be_nonempty_strings(self) -> None:
        for limitations in ("unknown", [None], [""]):
            with self.subTest(limitations=limitations):
                review = advisory_review("a" * 40)
                review["limitations"] = limitations
                with self.assertRaises(ai_review_agent.AiReviewError):
                    ai_review_agent.validate_review_shape(review, "a" * 40)

    def test_responses_request_uses_strict_schema(self) -> None:
        head_sha = "a" * 40
        response = {
            "status": "completed",
            "output": [
                {
                    "type": "message",
                    "content": [
                        {"type": "output_text", "text": __import__("json").dumps(advisory_review(head_sha))}
                    ],
                }
            ],
        }
        with patch.object(ai_review_agent, "_request_json", return_value=response) as request:
            result = ai_review_agent.request_ai_review(
                {"number": 1, "base": {"repo": {"full_name": "o/r"}}},
                [{"filename": "README.md", "status": "modified", "patch": "+ok"}],
                expected_head_sha=head_sha,
                api_key="not-a-real-key",
                base_url="https://example.test/v1",
                model="gpt-test",
                timeout_seconds=480,
            )
        self.assertEqual(result["reviewed_head_sha"], head_sha)
        url, _api_key, payload = request.call_args.args
        self.assertEqual(url, "https://example.test/v1/responses")
        self.assertTrue(payload["text"]["format"]["strict"])
        self.assertFalse(payload["store"])
        self.assertNotIn("decision", payload["text"]["format"]["schema"]["properties"])
        self.assertNotIn("blocking_reasons", payload["text"]["format"]["schema"]["properties"])
        self.assertEqual(request.call_args.kwargs["timeout_seconds"], 480)


if __name__ == "__main__":
    unittest.main()
