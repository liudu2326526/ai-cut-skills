#!/usr/bin/env python3
"""Publish AI suggestions for a current PR head without making merge decisions."""

from __future__ import annotations

import os
import sys

from ai_review_agent import (
    AiReviewError,
    parse_timeout_seconds,
    request_ai_review,
    validate_review_shape,
)
from ai_review_policy import (
    ReviewError,
    GitHubClient,
    parse_trusted_actors,
    preflight_review,
    render_review_comment,
    upsert_review_comment,
    validate_repository,
    validate_sha,
)


def require_environment(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        raise ReviewError(f"required environment variable is missing: {name}")
    return value


def resolve_pull_request_context(
    client: GitHubClient,
    repository: str,
    workflow_run_id: int,
    pull_request_hint: str,
) -> tuple[int, str]:
    run = client.get(f"repos/{repository}/actions/runs/{workflow_run_id}")
    if not isinstance(run, dict):
        raise ReviewError("workflow run response is not an object")
    head_sha = str(run.get("head_sha", ""))
    if pull_request_hint.strip():
        return int(pull_request_hint), head_sha

    head_repository = run.get("head_repository")
    head_branch = run.get("head_branch")
    if not isinstance(head_repository, dict) or not isinstance(head_branch, str):
        raise ReviewError("workflow run does not identify its head repository and branch")
    head_owner = head_repository.get("owner", {}).get("login")
    head_repository_name = head_repository.get("full_name")
    if not isinstance(head_owner, str) or not isinstance(head_repository_name, str):
        raise ReviewError("workflow run head repository metadata is incomplete")
    candidates = client.get(
        f"repos/{repository}/pulls",
        query={
            "state": "open",
            "base": "main",
            "head": f"{head_owner}:{head_branch}",
            "per_page": 100,
        },
    )
    if not isinstance(candidates, list):
        raise ReviewError("pull request lookup returned a non-array")
    matches = [
        pull_request
        for pull_request in candidates
        if isinstance(pull_request, dict)
        and pull_request.get("head", {}).get("sha") == head_sha
        and pull_request.get("head", {}).get("ref") == head_branch
        and pull_request.get("head", {}).get("repo", {}).get("full_name")
        == head_repository_name
    ]
    if len(matches) != 1 or not isinstance(matches[0].get("number"), int):
        raise ReviewError(
            "workflow run could not be mapped to exactly one open pull request"
        )
    return matches[0]["number"], head_sha


def publish_current_review(
    client: GitHubClient,
    repository: str,
    pull_request_number: int,
    head_sha: str,
    body: str,
) -> bool:
    current = client.get(f"repos/{repository}/pulls/{pull_request_number}")
    if not isinstance(current, dict):
        raise ReviewError("pull request response is not an object")
    if current.get("state") != "open" or current.get("head", {}).get("sha") != head_sha:
        print("Review discarded: the pull request closed or its head changed")
        return False
    upsert_review_comment(
        client,
        repository=repository,
        pull_request_number=pull_request_number,
        body=body,
    )
    return True


def _write_outputs(pull_request_number: int, head_sha: str) -> None:
    output_path = os.environ.get("GITHUB_OUTPUT")
    if not output_path:
        return
    with open(output_path, "a", encoding="utf-8") as handle:
        handle.write(f"pull_request_number={pull_request_number}\n")
        handle.write(f"head_sha={head_sha}\n")


def main() -> int:
    token = require_environment("GITHUB_TOKEN")
    repository = validate_repository(require_environment("GITHUB_REPOSITORY"))
    workflow_run_id = int(require_environment("PR_CHECKS_RUN_ID"))
    model = require_environment("AI_REVIEW_MODEL")
    base_url = require_environment("AI_REVIEW_BASE_URL")
    timeout_seconds = parse_timeout_seconds(os.environ.get("AI_REVIEW_TIMEOUT_SECONDS"))
    trusted_actors = parse_trusted_actors(require_environment("AI_REVIEW_TRUSTED_ACTORS"))
    client = GitHubClient(token)
    pull_request_number, head_sha = resolve_pull_request_context(
        client,
        repository,
        workflow_run_id,
        os.environ.get("PR_NUMBER", ""),
    )
    head_sha = validate_sha(head_sha)
    reasons: list[str] = []

    try:
        preflight = preflight_review(
            client,
            repository=repository,
            pull_request_number=pull_request_number,
            expected_head_sha=head_sha,
            workflow_run_id=workflow_run_id,
            trusted_actors=trusted_actors,
        )
        if not preflight.passed:
            reasons.extend(preflight.reasons)
            raise ReviewError("input validation could not establish a safe review context")
        assert preflight.pull_request is not None

        review = request_ai_review(
            preflight.pull_request,
            preflight.changed_files,
            expected_head_sha=head_sha,
            api_key=require_environment("AI_REVIEW_API_KEY"),
            base_url=base_url,
            model=model,
            timeout_seconds=timeout_seconds,
        )
        validate_review_shape(review, head_sha)
        published = publish_current_review(
            client,
            repository,
            pull_request_number,
            head_sha,
            render_review_comment(review, [], model=model, head_sha=head_sha),
        )
        if published:
            _write_outputs(pull_request_number, head_sha)
            print(f"AI suggestions published for PR #{pull_request_number} at {head_sha}; merge is manual")
        return 0
    except (AiReviewError, ReviewError, KeyError, TypeError, ValueError) as exc:
        if not reasons:
            reasons.append(str(exc))
        try:
            publish_current_review(
                client,
                repository,
                pull_request_number,
                head_sha,
                render_review_comment(None, reasons, model=model, head_sha=head_sha),
            )
        except ReviewError as comment_error:
            print(f"Could not publish advisory comment: {comment_error}", file=sys.stderr)
        print(f"AI review incomplete for PR #{pull_request_number}: {reasons[0]}; merge is manual", file=sys.stderr)
        return 1


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (AiReviewError, ReviewError, KeyError, TypeError, ValueError) as exc:
        print(f"AI review could not start: {exc}; merge is manual", file=sys.stderr)
        raise SystemExit(1) from exc
