from __future__ import annotations

import sys
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "scripts"))

import run_ai_review_gate  # noqa: E402


class ResolveClient:
    def __init__(self) -> None:
        self.queries = []

    def get(self, path, *, query=None):
        if "/actions/runs/" in path:
            return {
                "head_sha": "a" * 40,
                "head_branch": "bot/change",
                "head_repository": {
                    "full_name": "trusted-bot/repo",
                    "owner": {"login": "trusted-bot"},
                },
            }
        if path.endswith("/pulls"):
            self.queries.append(query)
            return [
                {
                    "number": 9,
                    "head": {
                        "sha": "a" * 40,
                        "ref": "bot/change",
                        "repo": {"full_name": "trusted-bot/repo"},
                    },
                }
            ]
        raise AssertionError(path)


class RunAiReviewGateTests(unittest.TestCase):
    def test_empty_workflow_association_resolves_unique_fork_pr(self) -> None:
        client = ResolveClient()
        number, head_sha = run_ai_review_gate.resolve_pull_request_context(
            client,
            "owner/repo",
            123,
            "",
        )
        self.assertEqual((number, head_sha), (9, "a" * 40))
        self.assertEqual(client.queries[0]["head"], "trusted-bot:bot/change")

    def test_workflow_payload_hint_is_preferred_when_present(self) -> None:
        number, head_sha = run_ai_review_gate.resolve_pull_request_context(
            ResolveClient(),
            "owner/repo",
            123,
            "17",
        )
        self.assertEqual((number, head_sha), (17, "a" * 40))


if __name__ == "__main__":
    unittest.main()
