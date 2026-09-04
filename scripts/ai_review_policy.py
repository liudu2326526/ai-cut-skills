#!/usr/bin/env python3
"""Validate safe review input and publish advice, never merge decisions."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import PurePosixPath
from typing import Any, Iterable
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

GITHUB_API = "https://api.github.com"
GITHUB_API_VERSION = "2026-03-10"
REQUIRED_JOBS = {"test", "lint", "security-scan"}
BLOCKED_BASENAMES = {
    ".env",
}
BLOCKED_SUFFIXES = (".key", ".pem", ".p12", ".pfx", ".keystore")
MAX_CHANGED_FILES = 80
MAX_CHANGED_LINES = 5_000
MAX_PATCH_CHARS = 160_000
SAFE_REPOSITORY = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")
SAFE_SHA = re.compile(r"^[0-9a-f]{40}$")


class ReviewError(RuntimeError):
    """Raised when GitHub state cannot be validated."""


@dataclass
class ReviewAssessment:
    passed: bool
    reasons: list[str] = field(default_factory=list)
    pull_request: dict[str, Any] | None = None
    changed_files: list[dict[str, Any]] = field(default_factory=list)


class GitHubClient:
    def __init__(self, token: str, *, api_base: str = GITHUB_API) -> None:
        if not token:
            raise ReviewError("GITHUB_TOKEN is missing")
        self.token = token
        self.api_base = api_base.rstrip("/")

    def request(
        self,
        method: str,
        path: str,
        *,
        payload: dict[str, Any] | None = None,
        query: dict[str, Any] | None = None,
    ) -> Any:
        # This client can only write issue comments, even if a caller regresses.
        if method != "GET" and not (
            method == "POST"
            and re.fullmatch(r"repos/[^/]+/[^/]+/issues/[0-9]+/comments", path)
            or method == "PATCH"
            and re.fullmatch(r"repos/[^/]+/[^/]+/issues/comments/[0-9]+", path)
        ):
            raise ReviewError("AI review can only write pull request comments")
        url = path if path.startswith("https://") else f"{self.api_base}/{path.lstrip('/')}"
        if query:
            url = f"{url}?{urlencode(query)}"
        data = None
        if payload is not None:
            data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        request = Request(
            url,
            data=data,
            method=method,
            headers={
                "Authorization": f"Bearer {self.token}",
                "Accept": "application/vnd.github+json",
                "Content-Type": "application/json",
                "X-GitHub-Api-Version": GITHUB_API_VERSION,
            },
        )
        try:
            with urlopen(request, timeout=30) as response:
                body = response.read()
        except HTTPError as exc:
            error_body = exc.read().decode("utf-8", errors="replace")
            try:
                message = json.loads(error_body).get("message", "request failed")
            except (json.JSONDecodeError, AttributeError):
                message = "request failed"
            raise ReviewError(f"GitHub API returned HTTP {exc.code}: {message}") from exc
        except (URLError, TimeoutError) as exc:
            raise ReviewError(f"GitHub API request failed: {exc}") from exc
        if not body:
            return None
        try:
            return json.loads(body.decode("utf-8"))
        except json.JSONDecodeError as exc:
            raise ReviewError("GitHub API returned invalid JSON") from exc

    def get(self, path: str, *, query: dict[str, Any] | None = None) -> Any:
        return self.request("GET", path, query=query)

    def post(self, path: str, payload: dict[str, Any]) -> Any:
        return self.request("POST", path, payload=payload)

    def patch(self, path: str, payload: dict[str, Any]) -> Any:
        return self.request("PATCH", path, payload=payload)

    def paginate(self, path: str) -> list[dict[str, Any]]:
        items: list[dict[str, Any]] = []
        for page in range(1, 11):
            batch = self.get(path, query={"per_page": 100, "page": page})
            if not isinstance(batch, list):
                raise ReviewError("GitHub paginated endpoint returned a non-array")
            items.extend(item for item in batch if isinstance(item, dict))
            if len(batch) < 100:
                return items
        raise ReviewError("GitHub pagination exceeded the safety limit")

    def paginate_collection(self, path: str, key: str) -> list[dict[str, Any]]:
        items: list[dict[str, Any]] = []
        for page in range(1, 11):
            response = self.get(path, query={"per_page": 100, "page": page})
            if not isinstance(response, dict) or not isinstance(response.get(key), list):
                raise ReviewError(f"GitHub paginated endpoint did not return {key!r}")
            batch = response[key]
            items.extend(item for item in batch if isinstance(item, dict))
            if len(batch) < 100:
                return items
        raise ReviewError("GitHub pagination exceeded the safety limit")


def validate_repository(repository: str) -> str:
    if not SAFE_REPOSITORY.fullmatch(repository):
        raise ReviewError("repository must be in owner/name form")
    return repository


def validate_sha(value: str, label: str = "SHA") -> str:
    normalized = value.strip().lower()
    if not SAFE_SHA.fullmatch(normalized):
        raise ReviewError(f"{label} must be a full lowercase SHA-1")
    return normalized


def parse_trusted_actors(value: str) -> set[str]:
    actors = {actor.strip().casefold() for actor in value.split(",") if actor.strip()}
    if not actors:
        raise ReviewError("AI_REVIEW_TRUSTED_ACTORS is empty")
    if any(not re.fullmatch(r"[A-Za-z0-9-]+", actor) for actor in actors):
        raise ReviewError("trusted actor list contains an invalid GitHub login")
    return actors


def get_pull_request(
    client: GitHubClient,
    repository: str,
    pull_request_number: int,
) -> dict[str, Any]:
    repository = validate_repository(repository)
    result = client.get(f"repos/{repository}/pulls/{pull_request_number}")
    if not isinstance(result, dict):
        raise ReviewError("pull request response is not an object")
    return result


def get_changed_files(
    client: GitHubClient,
    repository: str,
    pull_request_number: int,
) -> list[dict[str, Any]]:
    return client.paginate(f"repos/{validate_repository(repository)}/pulls/{pull_request_number}/files")


def _path_failure(path_text: Any) -> str | None:
    if not isinstance(path_text, str) or not path_text:
        return "changed file has an invalid path"
    if (
        "\x00" in path_text
        or "\\" in path_text
        or "//" in path_text
        or path_text.startswith("/")
        or any(ord(character) < 32 for character in path_text)
    ):
        return f"unsafe path: {path_text!r}"
    path = PurePosixPath(path_text)
    if any(part in {"", ".", ".."} for part in path.parts):
        return f"unsafe path: {path_text!r}"
    if (
        path.name in BLOCKED_BASENAMES
        or path.name.startswith(".env.")
        or path.name.lower().endswith(BLOCKED_SUFFIXES)
    ):
        return f"sensitive file requires human review: {path_text}"
    return None


def validate_changed_files(
    client: GitHubClient,
    repository: str,
    expected_head_sha: str,
    changed_files: list[dict[str, Any]],
) -> list[str]:
    reasons: list[str] = []
    if not changed_files:
        reasons.append("pull request has no changed files")
    if len(changed_files) > MAX_CHANGED_FILES:
        reasons.append(f"too many changed files: {len(changed_files)} > {MAX_CHANGED_FILES}")

    changed_lines = 0
    patch_chars = 0
    current_paths: set[str] = set()
    for changed_file in changed_files:
        filename = changed_file.get("filename")
        failure = _path_failure(filename)
        if failure:
            reasons.append(failure)
        previous_filename = changed_file.get("previous_filename")
        if previous_filename and (failure := _path_failure(previous_filename)):
            reasons.append(f"renamed source {failure}")
        status = changed_file.get("status")
        if status not in {"added", "modified", "removed", "renamed", "copied", "changed"}:
            reasons.append(f"unsupported file status for {filename}: {status!r}")
        additions = changed_file.get("additions")
        deletions = changed_file.get("deletions")
        if not isinstance(additions, int) or not isinstance(deletions, int):
            reasons.append(f"missing line counts for {filename}")
        else:
            changed_lines += additions + deletions
        patch = changed_file.get("patch")
        if status != "removed" and not isinstance(patch, str):
            reasons.append(f"binary or truncated diff requires human review: {filename}")
        elif isinstance(patch, str):
            patch_chars += len(patch)
        if status != "removed" and isinstance(filename, str):
            current_paths.add(filename)

    if changed_lines > MAX_CHANGED_LINES:
        reasons.append(f"change is too large: {changed_lines} lines > {MAX_CHANGED_LINES}")
    if patch_chars > MAX_PATCH_CHARS:
        reasons.append(f"diff is too large: {patch_chars} characters > {MAX_PATCH_CHARS}")

    tree = client.get(
        f"repos/{validate_repository(repository)}/git/trees/{validate_sha(expected_head_sha)}",
        query={"recursive": 1},
    )
    if not isinstance(tree, dict) or tree.get("truncated") is True:
        reasons.append("head tree could not be validated completely")
        return reasons
    tree_entries = {
        entry.get("path"): entry
        for entry in tree.get("tree", [])
        if isinstance(entry, dict) and isinstance(entry.get("path"), str)
    }
    for path_text in current_paths:
        entry = tree_entries.get(path_text)
        if not entry:
            reasons.append(f"changed path is missing from the head tree: {path_text}")
            continue
        if entry.get("type") != "blob" or entry.get("mode") == "120000":
            reasons.append(f"non-regular file requires human review: {path_text}")
    return reasons


def validate_workflow_run(
    client: GitHubClient,
    repository: str,
    workflow_run_id: int,
    pull_request_number: int,
    expected_head_sha: str,
    pull_request: dict[str, Any],
) -> list[str]:
    reasons: list[str] = []
    run = client.get(f"repos/{validate_repository(repository)}/actions/runs/{workflow_run_id}")
    if not isinstance(run, dict):
        return ["workflow run response is not an object"]
    if run.get("name") != "PR Checks":
        reasons.append("review was not triggered by the trusted PR Checks workflow")
    if run.get("event") != "pull_request" or run.get("conclusion") != "success":
        reasons.append("PR Checks workflow did not complete successfully")
    if run.get("head_sha") != expected_head_sha:
        reasons.append("workflow run head SHA does not match the pull request")
    if run.get("head_branch") != pull_request.get("head", {}).get("ref"):
        reasons.append("workflow run head branch does not match the pull request")
    if run.get("head_repository", {}).get("full_name") != pull_request.get("head", {}).get(
        "repo", {}
    ).get("full_name"):
        reasons.append("workflow run head repository does not match the pull request")
    associations = run.get("pull_requests")
    if not isinstance(associations, list):
        reasons.append("workflow run pull request associations are invalid")
    elif associations and not any(
        isinstance(item, dict)
        and item.get("number") == pull_request_number
        and item.get("head", {}).get("sha") == expected_head_sha
        for item in associations
    ):
        reasons.append("workflow run is not associated with the current PR head")

    jobs = client.paginate_collection(
        f"repos/{validate_repository(repository)}/actions/runs/{workflow_run_id}/jobs",
        "jobs",
    )
    successful_jobs = {
        job.get("name")
        for job in jobs
        if job.get("status") == "completed" and job.get("conclusion") == "success"
    }
    missing = sorted(REQUIRED_JOBS - successful_jobs)
    if missing:
        reasons.append(f"required workflow jobs did not pass: {', '.join(missing)}")
    return reasons


def preflight_review(
    client: GitHubClient,
    *,
    repository: str,
    pull_request_number: int,
    expected_head_sha: str,
    workflow_run_id: int,
    trusted_actors: set[str],
) -> ReviewAssessment:
    expected_head_sha = validate_sha(expected_head_sha, "expected head SHA")
    pull_request = get_pull_request(client, repository, pull_request_number)
    changed_files = get_changed_files(client, repository, pull_request_number)
    reasons: list[str] = []

    if pull_request.get("state") != "open":
        reasons.append("pull request is not open")
    if pull_request.get("draft") is True:
        reasons.append("automatic review is skipped for draft pull requests")
    if pull_request.get("base", {}).get("ref") != "main":
        reasons.append("pull request does not target main")
    if pull_request.get("head", {}).get("sha") != expected_head_sha:
        reasons.append("pull request head changed after checks started")
    author = pull_request.get("user", {}).get("login")
    head_owner = pull_request.get("head", {}).get("repo", {}).get("owner", {}).get("login")
    if not isinstance(author, str) or author.casefold() not in trusted_actors:
        reasons.append(f"pull request author is not trusted: {author!r}")
    if not isinstance(head_owner, str) or head_owner.casefold() not in trusted_actors:
        reasons.append(f"pull request head repository owner is not trusted: {head_owner!r}")

    reasons.extend(
        validate_workflow_run(
            client,
            repository,
            workflow_run_id,
            pull_request_number,
            expected_head_sha,
            pull_request,
        )
    )
    reasons.extend(
        validate_changed_files(client, repository, expected_head_sha, changed_files)
    )
    return ReviewAssessment(
        passed=not reasons,
        reasons=list(dict.fromkeys(reasons)),
        pull_request=pull_request,
        changed_files=changed_files,
    )


def _escape_mentions(text: str) -> str:
    return text.replace("@", "@\u200b").replace("`", "\\`")


def render_review_comment(
    review: dict[str, Any] | None,
    reasons: Iterable[str],
    *,
    model: str,
    head_sha: str,
) -> str:
    # Reuse the old marker so a new advisory replaces an old PASS/BLOCK comment.
    marker = "<!-- ai-review-gate -->"
    lines = [
        marker,
        "## AI 审查建议" if review is not None else "## AI 审查未完成",
        "",
        "仅供人工参考：AI 不批准、不阻止、不执行合并，所有问题由维护者判断。",
        "测试、lint 和安全扫描仍是独立的必需检查。",
        "",
        f"Reviewed head: `{validate_sha(head_sha)}`",
        "",
    ]
    if review:
        lines.extend([_escape_mentions(str(review.get("summary", "")))[:2_000], ""])
        findings = review.get("findings", [])
        if findings:
            lines.append("### Findings")
            lines.append("")
            for finding in findings[:30]:
                location = _escape_mentions(str(finding.get("path", "unknown")))
                if finding.get("line"):
                    location += f":{finding['line']}"
                title = _escape_mentions(str(finding.get("title", "finding")))
                detail = _escape_mentions(str(finding.get("detail", "")))
                lines.append(
                    f"- **{finding.get('severity', 'P?')}** `{location}` — {title}: {detail}"
                )
            lines.append("")
    limitations = list(reasons) + (review.get("limitations", []) if review else [])
    unique_reasons = list(dict.fromkeys(str(reason) for reason in limitations if str(reason).strip()))
    if unique_reasons:
        lines.extend(["### 审查限制 / 未完成原因（不阻止合并）", ""])
        lines.extend(f"- {_escape_mentions(reason)}" for reason in unique_reasons[:30])
        lines.append("")
    lines.append(f"Model: `{_escape_mentions(model)}`. 最终由人手动合并。")
    return "\n".join(lines)[:60_000]


def upsert_review_comment(
    client: GitHubClient,
    *,
    repository: str,
    pull_request_number: int,
    body: str,
) -> None:
    marker = "<!-- ai-review-gate -->"
    comments = client.paginate(
        f"repos/{validate_repository(repository)}/issues/{pull_request_number}/comments"
    )
    for comment in comments:
        if (
            marker in str(comment.get("body", ""))
            and comment.get("user", {}).get("login") == "github-actions[bot]"
        ):
            client.patch(f"repos/{repository}/issues/comments/{comment['id']}", {"body": body})
            return
    client.post(f"repos/{repository}/issues/{pull_request_number}/comments", {"body": body})
