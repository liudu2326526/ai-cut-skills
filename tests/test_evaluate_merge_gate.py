from __future__ import annotations

import sys
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "scripts"))

import evaluate_merge_gate  # noqa: E402


class FakeGitHubClient:
    def get(self, path, *, query=None):
        if "/git/trees/" in path:
            return {
                "truncated": False,
                "tree": [{"path": "skills/demo/SKILL.md", "type": "blob", "mode": "100644"}],
            }
        raise AssertionError(path)


class EvaluateMergeGateTests(unittest.TestCase):
    def test_trusted_actors_are_normalized_and_required(self) -> None:
        self.assertEqual(
            evaluate_merge_gate.parse_trusted_actors("Owner, BOT-user"),
            {"owner", "bot-user"},
        )
        with self.assertRaises(evaluate_merge_gate.GateError):
            evaluate_merge_gate.parse_trusted_actors("  ")

    def test_path_policy_allows_skill_changes_but_blocks_gate_code(self) -> None:
        self.assertIsNone(evaluate_merge_gate._path_failure("skills/demo/SKILL.md"))
        self.assertIsNone(evaluate_merge_gate._path_failure("skill-catalog.yaml"))
        self.assertIn(
            "human review",
            evaluate_merge_gate._path_failure("scripts/evaluate_merge_gate.py"),
        )
        self.assertIn("sensitive", evaluate_merge_gate._path_failure("skills/demo/private.pem"))

    def test_binary_or_truncated_patch_is_blocked(self) -> None:
        reasons = evaluate_merge_gate.validate_changed_files(
            FakeGitHubClient(),
            "owner/repo",
            "a" * 40,
            [
                {
                    "filename": "skills/demo/SKILL.md",
                    "status": "modified",
                    "additions": 1,
                    "deletions": 1,
                }
            ],
        )
        self.assertTrue(any("binary or truncated" in reason for reason in reasons))

    def test_ai_p0_blocks_even_if_decision_claims_block(self) -> None:
        head_sha = "a" * 40
        review = {
            "decision": "block",
            "reviewed_head_sha": head_sha,
            "summary": "A dangerous issue exists.",
            "findings": [
                {
                    "severity": "P1",
                    "path": "skills/demo/run.py",
                    "line": 5,
                    "title": "Unsafe deletion",
                    "detail": "Deletes a broad directory.",
                }
            ],
            "blocking_reasons": ["Unsafe destructive behavior"],
        }
        reasons = evaluate_merge_gate.evaluate_ai_review(review, head_sha)
        self.assertIn("Unsafe destructive behavior", reasons)
        self.assertTrue(any(reason.startswith("P1 ") for reason in reasons))

    def test_comment_escapes_mentions(self) -> None:
        body = evaluate_merge_gate.render_review_comment(
            None,
            ["Ask @owner"],
            model="gpt-test",
            passed=False,
        )
        self.assertNotIn("@owner", body)
        self.assertIn("<!-- ai-review-gate -->", body)


if __name__ == "__main__":
    unittest.main()
