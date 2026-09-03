#!/usr/bin/env python3
"""Run the privileged AI review gate and safely enable PR auto-merge."""

from __future__ import annotations

import os
import subprocess
import sys
from typing import Any

from ai_review_agent import AiReviewError, request_ai_review
from evaluate_merge_gate import (
    GateError,
    GitHubClient,
    evaluate_ai_review,
    parse_trusted_actors,
    preflight_merge_gate,
    publish_commit_status,
    render_review_comment,
    upsert_review_comment,
)


def require_environment(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        raise GateError(f"required environment variable is missing: {name}")
    return value


def workflow_url() -> str:
    return (
        f"{require_environment('GITHUB_SERVER_URL')}/"
        f"{require_environment('GITHUB_REPOSITORY')}/actions/runs/"
        f"{require_environment('GITHUB_RUN_ID')}"
    )


def enable_auto_merge(repository: str, pull_request_number: int, head_sha: str) -> None:
    process = subprocess.run(
        [
            "gh",
            "pr",
            "merge",
            str(pull_request_number),
            "--repo",
            repository,
            "--auto",
            "--squash",
            "--match-head-commit",
            head_sha,
        ],
        check=False,
        capture_output=True,
        text=True,
        env={**os.environ, "GH_TOKEN": require_environment("GITHUB_TOKEN")},
    )
    if process.returncode != 0:
        message = " ".join((process.stderr or process.stdout or "unknown error").split())
        raise GateError(f"could not enable auto-merge: {message[:500]}")


def _write_outputs(pull_request_number: int, head_sha: str) -> None:
    output_path = os.environ.get("GITHUB_OUTPUT")
    if not output_path:
        return
    with open(output_path, "a", encoding="utf-8") as handle:
        handle.write(f"pull_request_number={pull_request_number}\n")
        handle.write(f"head_sha={head_sha}\n")


def main() -> int:
    token = require_environment("GITHUB_TOKEN")
    repository = require_environment("GITHUB_REPOSITORY")
    pull_request_number = int(require_environment("PR_NUMBER"))
    head_sha = require_environment("PR_HEAD_SHA")
    workflow_run_id = int(require_environment("PR_CHECKS_RUN_ID"))
    model = require_environment("AI_REVIEW_MODEL")
    base_url = require_environment("AI_REVIEW_BASE_URL")
    trusted_actors = parse_trusted_actors(require_environment("AUTO_MERGE_TRUSTED_ACTORS"))
    target_url = workflow_url()
    client = GitHubClient(token)
    review: dict[str, Any] | None = None
    reasons: list[str] = []
    status_started = False

    try:
        publish_commit_status(
            client,
            repository=repository,
            sha=head_sha,
            state="pending",
            description="AI and deterministic merge review in progress",
            target_url=target_url,
        )
        status_started = True

        preflight = preflight_merge_gate(
            client,
            repository=repository,
            pull_request_number=pull_request_number,
            expected_head_sha=head_sha,
            workflow_run_id=workflow_run_id,
            trusted_actors=trusted_actors,
        )
        if not preflight.passed:
            reasons.extend(preflight.reasons)
            raise GateError("deterministic preflight blocked the pull request")
        assert preflight.pull_request is not None

        review = request_ai_review(
            preflight.pull_request,
            preflight.changed_files,
            expected_head_sha=head_sha,
            api_key=require_environment("AI_REVIEW_API_KEY"),
            base_url=base_url,
            model=model,
        )
        reasons.extend(evaluate_ai_review(review, head_sha))
        if reasons:
            raise GateError("AI review blocked the pull request")

        current = client.get(f"repos/{repository}/pulls/{pull_request_number}")
        if not isinstance(current, dict) or current.get("state") != "open":
            raise GateError("pull request closed while it was being reviewed")
        if current.get("head", {}).get("sha") != head_sha:
            raise GateError("pull request head changed while it was being reviewed")

        enable_auto_merge(repository, pull_request_number, head_sha)
        upsert_review_comment(
            client,
            repository=repository,
            pull_request_number=pull_request_number,
            body=render_review_comment(review, [], model=model, passed=True),
        )
        publish_commit_status(
            client,
            repository=repository,
            sha=head_sha,
            state="success",
            description="AI review and deterministic policy passed",
            target_url=target_url,
        )
        _write_outputs(pull_request_number, head_sha)
        print(f"AI review gate passed for PR #{pull_request_number} at {head_sha}")
        return 0
    except (AiReviewError, GateError, KeyError, TypeError, ValueError) as exc:
        if not reasons:
            reasons.append(str(exc))
        try:
            upsert_review_comment(
                client,
                repository=repository,
                pull_request_number=pull_request_number,
                body=render_review_comment(review, reasons, model=model, passed=False),
            )
        except GateError as comment_error:
            print(f"Could not publish gate comment: {comment_error}", file=sys.stderr)
        if status_started:
            try:
                publish_commit_status(
                    client,
                    repository=repository,
                    sha=head_sha,
                    state="failure",
                    description="AI review gate blocked this pull request",
                    target_url=target_url,
                )
            except GateError as status_error:
                print(f"Could not publish final gate status: {status_error}", file=sys.stderr)
        print(f"AI review gate blocked PR #{pull_request_number}: {reasons[0]}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
