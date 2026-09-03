from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest.mock import patch


REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "scripts"))

import ai_review_agent  # noqa: E402


def passing_review(head_sha: str) -> dict:
    return {
        "decision": "pass",
        "reviewed_head_sha": head_sha,
        "summary": "No blocking issue found.",
        "findings": [],
        "blocking_reasons": [],
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

    def test_pass_review_must_match_head_and_have_no_blockers(self) -> None:
        head_sha = "a" * 40
        self.assertEqual(
            ai_review_agent.validate_review_shape(passing_review(head_sha), head_sha)["decision"],
            "pass",
        )
        mismatched = passing_review("b" * 40)
        with self.assertRaisesRegex(ai_review_agent.AiReviewError, "head SHA"):
            ai_review_agent.validate_review_shape(mismatched, head_sha)

    def test_contradictory_pass_is_rejected(self) -> None:
        head_sha = "a" * 40
        review = passing_review(head_sha)
        review["blocking_reasons"] = ["Unsafe change"]
        with self.assertRaisesRegex(ai_review_agent.AiReviewError, "contradicts"):
            ai_review_agent.validate_review_shape(review, head_sha)

    def test_responses_request_uses_strict_schema(self) -> None:
        head_sha = "a" * 40
        response = {
            "status": "completed",
            "output": [
                {
                    "type": "message",
                    "content": [
                        {"type": "output_text", "text": __import__("json").dumps(passing_review(head_sha))}
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
            )
        self.assertEqual(result["decision"], "pass")
        url, _api_key, payload = request.call_args.args
        self.assertEqual(url, "https://example.test/v1/responses")
        self.assertTrue(payload["text"]["format"]["strict"])
        self.assertFalse(payload["store"])


if __name__ == "__main__":
    unittest.main()
