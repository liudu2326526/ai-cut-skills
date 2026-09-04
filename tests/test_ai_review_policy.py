from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest.mock import patch


REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "scripts"))

import ai_review_policy  # noqa: E402


class FakeGitHubClient:
    def get(self, path, *, query=None):
        if "/git/trees/" in path:
            return {
                "truncated": False,
                "tree": [{"path": "skills/demo/SKILL.md", "type": "blob", "mode": "100644"}],
            }
        raise AssertionError(path)


class AiReviewPolicyTests(unittest.TestCase):
    def test_trusted_actors_are_normalized_and_required(self) -> None:
        self.assertEqual(
            ai_review_policy.parse_trusted_actors("Owner, BOT-user"),
            {"owner", "bot-user"},
        )
        with self.assertRaises(ai_review_policy.ReviewError):
            ai_review_policy.parse_trusted_actors("  ")

    def test_path_policy_allows_automation_review_but_not_credentials(self) -> None:
        self.assertIsNone(ai_review_policy._path_failure("skills/demo/SKILL.md"))
        self.assertIsNone(ai_review_policy._path_failure("skill-catalog.yaml"))
        self.assertIsNone(ai_review_policy._path_failure("scripts/ai_review_policy.py"))
        self.assertIsNone(ai_review_policy._path_failure(".github/workflows/review.yml"))
        self.assertIn("sensitive", ai_review_policy._path_failure("skills/demo/private.pem"))
        self.assertIn("sensitive", ai_review_policy._path_failure(".env.production"))

    def test_binary_or_truncated_patch_is_blocked(self) -> None:
        reasons = ai_review_policy.validate_changed_files(
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

    def test_high_severity_comment_is_advisory_not_a_merge_verdict(self) -> None:
        head_sha = "a" * 40
        review = {
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
            "limitations": ["Only the supplied patch was reviewed."],
        }
        body = ai_review_policy.render_review_comment(review, [], model="gpt-test", head_sha=head_sha)
        self.assertIn("P1", body)
        self.assertIn("Unsafe deletion", body)
        self.assertIn("最终由人手动合并", body)
        self.assertIn(head_sha, body)
        self.assertIn("Only the supplied patch", body)
        self.assertNotIn("BLOCK", body)
        self.assertNotIn("PASS", body)

    def test_comment_escapes_mentions(self) -> None:
        body = ai_review_policy.render_review_comment(
            None,
            ["Ask @owner"],
            model="gpt-test",
            head_sha="a" * 40,
        )
        self.assertNotIn("@owner", body)
        self.assertIn("<!-- ai-review-gate -->", body)
        self.assertIn("AI 审查未完成", body)

    def test_client_rejects_all_writes_except_issue_comments(self) -> None:
        client = ai_review_policy.GitHubClient("test-token")
        forbidden = [
            ("PUT", "repos/owner/repo/pulls/9/merge"),
            ("POST", "graphql"),
            ("POST", "repos/owner/repo/statuses/" + "a" * 40),
            ("POST", "repos/owner/repo/pulls/9/reviews"),
            ("PATCH", "repos/owner/repo/git/refs/heads/main"),
            ("DELETE", "repos/owner/repo/issues/comments/1"),
        ]
        with patch.object(ai_review_policy, "urlopen") as request:
            for method, path in forbidden:
                with self.subTest(method=method, path=path):
                    with self.assertRaisesRegex(ai_review_policy.ReviewError, "only write"):
                        client.request(method, path, payload={})
            request.assert_not_called()

    def test_client_allows_post_and_update_comments(self) -> None:
        client = ai_review_policy.GitHubClient("test-token")
        with patch.object(ai_review_policy, "urlopen") as request:
            request.return_value.__enter__.return_value.read.return_value = b'{}'
            client.post("repos/owner/repo/issues/9/comments", {"body": "Advice"})
            client.patch("repos/owner/repo/issues/comments/1", {"body": "New advice"})
            self.assertEqual(request.call_count, 2)

    def test_new_advice_updates_only_the_existing_bot_comment(self) -> None:
        class CommentClient:
            def paginate(self, path):
                return [
                    {"id": 1, "body": "<!-- ai-review-gate -->", "user": {"login": "owner"}},
                    {"id": 2, "body": "<!-- ai-review-gate --> BLOCK", "user": {"login": "github-actions[bot]"}},
                ]

            def patch(self, path, payload):
                self.updated = (path, payload)

        client = CommentClient()
        ai_review_policy.upsert_review_comment(
            client, repository="owner/repo", pull_request_number=9, body="Advice",
        )
        self.assertEqual(client.updated, ("repos/owner/repo/issues/comments/2", {"body": "Advice"}))

    def test_empty_workflow_pr_associations_are_allowed_when_head_matches(self) -> None:
        class WorkflowClient:
            def get(self, path, *, query=None):
                return {
                    "name": "PR Checks",
                    "event": "pull_request",
                    "conclusion": "success",
                    "head_sha": "a" * 40,
                    "head_branch": "bot/change",
                    "head_repository": {"full_name": "bot/repo"},
                    "pull_requests": [],
                }

            def paginate_collection(self, path, key):
                return [
                    {"name": name, "status": "completed", "conclusion": "success"}
                    for name in ai_review_policy.REQUIRED_JOBS
                ]

        reasons = ai_review_policy.validate_workflow_run(
            WorkflowClient(),
            "owner/repo",
            123,
            9,
            "a" * 40,
            {
                "head": {
                    "sha": "a" * 40,
                    "ref": "bot/change",
                    "repo": {"full_name": "bot/repo"},
                }
            },
        )
        self.assertEqual(reasons, [])


if __name__ == "__main__":
    unittest.main()
