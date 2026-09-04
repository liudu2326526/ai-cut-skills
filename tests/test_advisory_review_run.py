from __future__ import annotations

import os
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "scripts"))

import run_ai_review  # noqa: E402
from ai_review_policy import REQUIRED_JOBS  # noqa: E402


class AdvisoryClient:
    def __init__(self):
        self.writes = []
        self.current_sha = "a" * 40
        self.state = "open"
        self.owner = "trusted-bot"
        self.workflow_sha = "a" * 40
        self.mergeable = True
        self.mergeable_state = "clean"
        self.has_patch = True

    def get(self, path, *, query=None):
        if "/actions/runs/" in path:
            return {
                "name": "PR Checks", "event": "pull_request", "conclusion": "success",
                "head_sha": self.workflow_sha, "head_branch": "bot/change",
                "head_repository": {
                    "full_name": "trusted-bot/repo", "owner": {"login": "trusted-bot"},
                },
                "pull_requests": [],
            }
        if path.endswith("/pulls/9"):
            return {
                "number": 9, "state": self.state, "draft": False,
                "user": {"login": self.owner},
                "base": {"ref": "main", "repo": {"full_name": "owner/repo"}},
                "head": {
                    "sha": self.current_sha, "ref": "bot/change",
                    "repo": {
                        "full_name": "trusted-bot/repo", "owner": {"login": "trusted-bot"},
                    },
                },
                "mergeable": self.mergeable, "mergeable_state": self.mergeable_state,
            }
        if "/git/trees/" in path:
            return {"tree": [{
                "path": "skills/demo/SKILL.md", "type": "blob", "mode": "100644",
            }]}
        raise AssertionError(path)

    def paginate(self, path):
        if path.endswith("/files"):
            return [{
                "filename": "skills/demo/SKILL.md", "status": "modified",
                "additions": 1, "deletions": 1,
                **({"patch": "-old\n+new"} if self.has_patch else {}),
            }]
        if path.endswith("/comments"):
            return []
        raise AssertionError(path)

    def paginate_collection(self, path, key):
        return [
            {"name": name, "status": "completed", "conclusion": "success"}
            for name in REQUIRED_JOBS
        ]

    def post(self, path, payload):
        # Status, review-verdict and merge writes must fail this integration test.
        if path != "repos/owner/repo/issues/9/comments":
            raise AssertionError(f"Non-comment write: {path}")
        self.writes.append((path, payload))


class AdvisoryRunTests(unittest.TestCase):
    def setUp(self):
        self.client = AdvisoryClient()
        environment = patch.dict(os.environ, {
            "GITHUB_TOKEN": "test-token", "GITHUB_REPOSITORY": "owner/repo",
            "PR_CHECKS_RUN_ID": "123", "PR_NUMBER": "9", "AI_REVIEW_MODEL": "gpt-test",
            "AI_REVIEW_BASE_URL": "https://example.test/v1", "AI_REVIEW_API_KEY": "test-key",
            "AI_REVIEW_TRUSTED_ACTORS": "owner,trusted-bot",
        }, clear=True)
        environment.start()
        self.addCleanup(environment.stop)

    def review(self, severity=None):
        return {
            "reviewed_head_sha": "a" * 40, "summary": "Review suggestions.",
            "limitations": [],
            "findings": [{
                "severity": severity, "path": "skills/demo/SKILL.md", "line": 1,
                "title": "Unsafe deletion", "detail": "Restrict the target path.",
            }] if severity else [],
        }

    def execute(self, *, review=None, effect=None):
        with patch.object(run_ai_review, "GitHubClient", return_value=self.client):
            with patch.object(
                run_ai_review, "request_ai_review", return_value=review, side_effect=effect,
            ) as request:
                code = run_ai_review.main()
        return code, request

    def test_all_severities_only_publish_advice_and_succeed(self):
        for severity in (None, "P0", "P1", "P2", "P3"):
            with self.subTest(severity=severity):
                self.client.writes.clear()
                code, request = self.execute(review=self.review(severity))
                self.assertEqual(code, 0)
                request.assert_called_once()
                self.assertEqual(len(self.client.writes), 1)
                body = self.client.writes[0][1]["body"]
                self.assertIn("最终由人手动合并", body)
                self.assertIn("a" * 40, body)
                self.assertNotIn("BLOCK", body)
                self.assertNotIn("PASS", body)

    def test_timeout_only_reports_incomplete_review(self):
        code, _ = self.execute(effect=run_ai_review.AiReviewError("endpoint timed out"))
        self.assertEqual(code, 1)  # operational failure, not a required check
        body = self.client.writes[0][1]["body"]
        self.assertIn("AI 审查未完成", body)
        self.assertIn("endpoint timed out", body)
        self.assertNotIn("BLOCK", body)

    def test_old_success_or_failure_never_overwrites_new_head_comment(self):
        for fails in (False, True):
            with self.subTest(fails=fails):
                self.client.current_sha = "a" * 40

                def finish(*args, **kwargs):
                    self.client.current_sha = "b" * 40
                    if fails:
                        raise run_ai_review.AiReviewError("endpoint timed out")
                    return self.review("P1")

                self.execute(effect=finish)
                self.assertEqual(self.client.writes, [])

    def test_closed_pr_is_not_commented(self):
        def finish(*args, **kwargs):
            self.client.state = "closed"
            return self.review()
        code, _ = self.execute(effect=finish)
        self.assertEqual(code, 0)
        self.assertEqual(self.client.writes, [])

    def test_mismatched_ai_sha_is_not_published_as_advice(self):
        review = self.review()
        review["reviewed_head_sha"] = "b" * 40
        code, _ = self.execute(review=review)
        self.assertEqual(code, 1)
        self.assertIn("AI 审查未完成", self.client.writes[0][1]["body"])

    def test_conflicts_or_behind_state_do_not_prevent_advice(self):
        for mergeable, state in ((False, "dirty"), (True, "behind"), (None, "unknown")):
            with self.subTest(state=state):
                self.client.mergeable = mergeable
                self.client.mergeable_state = state
                code, request = self.execute(review=self.review())
                self.assertEqual(code, 0)
                request.assert_called_once()

    def test_untrusted_author_or_missing_diff_skips_provider(self):
        for attribute, value in (("owner", "stranger"), ("has_patch", False)):
            with self.subTest(attribute=attribute):
                self.client = AdvisoryClient()
                setattr(self.client, attribute, value)
                code, request = self.execute(review=self.review())
                self.assertEqual(code, 1)
                request.assert_not_called()
                self.assertIn("AI 审查未完成", self.client.writes[0][1]["body"])

    def test_stale_ci_never_calls_provider_or_posts_a_comment(self):
        self.client.current_sha = "b" * 40
        code, request = self.execute(review=self.review())
        self.assertEqual(code, 1)
        request.assert_not_called()
        self.assertEqual(self.client.writes, [])

    def test_workflow_has_only_comment_write_permissions(self):
        workflow = (REPO_ROOT / ".github/workflows/ai-review-suggestions.yml").read_text()
        permissions = workflow.split("permissions:\n", 1)[1].split("\n\n", 1)[0]
        self.assertEqual(permissions.splitlines(), [
            "  actions: read", "  contents: read", "  issues: write", "  pull-requests: read",
        ])
        self.assertIn("ref: main", workflow)
        self.assertIn("persist-credentials: false", workflow)
        self.assertIn("run: python scripts/run_ai_review.py", workflow)
        self.assertNotIn("gh pr merge", workflow)
        self.assertFalse((REPO_ROOT / ".github/workflows/ai-review-merge.yml").exists())


if __name__ == "__main__":
    unittest.main()
