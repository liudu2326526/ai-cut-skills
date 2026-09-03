#!/usr/bin/env python3
"""Validate and submit a scoped change from the ai-cut-skills repository."""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from urllib.parse import urlparse


SAFE_SEGMENT = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")
CHANGE_TYPES = {"feat", "fix", "docs", "refactor", "test", "chore"}
EXCLUDED_NAMES = {
    ".DS_Store",
    ".idea",
    ".cache",
    ".npm",
    ".ruff_cache",
    "__pycache__",
    "build",
    "coverage",
    "dist",
    "node_modules",
}
EXCLUDED_SUFFIXES = (".pyc", ".pyo")


class ReleaseError(RuntimeError):
    """A validation or repository operation failed."""


@dataclass(frozen=True)
class ReleaseConfig:
    repo_root: Path
    skills: tuple[str, ...]
    includes: tuple[str, ...]
    group: str
    change_type: str
    summary: str
    scope: str
    date: str
    base_remote: str
    base_branch: str
    push_remote: str
    github_account: str | None
    target_repository: str | None
    execute: bool
    skip_tests: bool
    keep_worktree: bool


def run_command(
    args: list[str],
    cwd: Path,
    *,
    check: bool = True,
    input_text: str | None = None,
) -> str:
    completed = subprocess.run(
        args,
        cwd=str(cwd),
        input=input_text,
        text=True,
        capture_output=True,
        encoding="utf-8",
        errors="replace",
    )
    if check and completed.returncode != 0:
        detail = (completed.stderr or completed.stdout).strip()
        raise ReleaseError(f"命令失败：{' '.join(args)}\n{detail[-2000:]}")
    return completed.stdout.strip()


def run_bytes(args: list[str], cwd: Path) -> bytes:
    completed = subprocess.run(args, cwd=str(cwd), capture_output=True)
    if completed.returncode != 0:
        detail = completed.stderr.decode("utf-8", "replace").strip()
        raise ReleaseError(f"命令失败：{' '.join(args)}\n{detail[-2000:]}")
    return completed.stdout


def validate_segment(value: str, field: str) -> str:
    value = value.strip()
    if not value or not SAFE_SEGMENT.fullmatch(value) or value in {".", ".."}:
        raise ReleaseError(f"{field} 不是合法的分支片段：{value!r}")
    return value


def validate_date(value: str) -> str:
    try:
        parsed = datetime.strptime(value, "%Y%m%d")
    except ValueError as exc:
        raise ReleaseError("日期必须是 YYYYMMDD") from exc
    return parsed.strftime("%Y%m%d")


def build_branch_name(group: str, change_type: str, scope: str, date: str) -> str:
    group = validate_segment(group, "组别")
    change_type = validate_segment(change_type, "变更类型")
    scope = validate_segment(scope, "作用域")
    date = validate_date(date)
    return f"{group}/{change_type}-{scope}-{date}"


def normalize_relative_path(value: str) -> str:
    path = Path(value.replace("\\", "/"))
    if path.is_absolute() or ".." in path.parts or not path.parts:
        raise ReleaseError(f"路径必须位于仓库内：{value!r}")
    return path.as_posix()


def selected_pathspecs(config: ReleaseConfig) -> list[str]:
    paths = [f"skills/{skill}" for skill in config.skills]
    paths.extend(config.includes)
    return list(dict.fromkeys(paths))


def path_is_allowed(path: str, pathspecs: list[str]) -> bool:
    candidate = Path(path.replace("\\", "/"))
    return any(candidate == Path(spec) or Path(spec) in candidate.parents for spec in pathspecs)


def validate_skill_paths(repo_root: Path, skills: tuple[str, ...]) -> None:
    for skill in skills:
        if not SAFE_SEGMENT.fullmatch(skill) or skill in {".", ".."}:
            raise ReleaseError(f"Skill 名称不合法：{skill!r}")
        skill_root = repo_root / "skills" / skill
        if not (skill_root / "SKILL.md").is_file():
            raise ReleaseError(f"目标 Skill 不存在或缺少 SKILL.md：{skill_root}")


def list_changed_paths(repo_root: Path, base_ref: str | None, pathspecs: list[str]) -> tuple[list[str], list[str]]:
    diff_args = ["git", "diff", "--name-only"]
    if base_ref:
        diff_args.append(base_ref)
    else:
        # Include both staged and unstaged changes during a read-only plan.
        diff_args.append("HEAD")
    diff_args.extend(["--", *pathspecs])
    try:
        tracked_output = run_command(diff_args, repo_root)
    except ReleaseError:
        if base_ref:
            raise
        # Repositories without a first commit cannot diff against HEAD yet.
        tracked_output = run_command(["git", "diff", "--name-only", "--", *pathspecs], repo_root)
    tracked = [line for line in tracked_output.splitlines() if line]
    untracked = [
        line
        for line in run_command(
            ["git", "ls-files", "--others", "--exclude-standard", "--", *pathspecs],
            repo_root,
        ).splitlines()
        if line
    ]
    return list(dict.fromkeys(tracked)), list(dict.fromkeys(untracked))


def quick_validator_path() -> Path | None:
    codex_home = Path(os.environ.get("CODEX_HOME", Path.home() / ".codex"))
    candidate = codex_home / "skills" / ".system" / "skill-creator" / "scripts" / "quick_validate.py"
    return candidate if candidate.is_file() else None


def run_checks(repo_root: Path, config: ReleaseConfig, *, changed_paths: list[str]) -> dict[str, object]:
    checks: list[dict[str, object]] = []

    def check(name: str, args: list[str]) -> None:
        try:
            output = run_command(args, repo_root)
            checks.append({"name": name, "ok": True, "output": output[-2000:]})
        except ReleaseError as exc:
            checks.append({"name": name, "ok": False, "output": str(exc)[-2000:]})

    validator = quick_validator_path()
    for skill in config.skills:
        if validator:
            check(
                f"quick_validate:{skill}",
                [sys.executable, "-X", "utf8", str(validator), str(repo_root / "skills" / skill)],
            )
        else:
            checks.append({"name": f"quick_validate:{skill}", "ok": False, "output": "找不到 quick_validate.py"})

    sync_script = repo_root / "scripts" / "sync_skills.py"
    if sync_script.is_file():
        check("catalog", [sys.executable, "-X", "utf8", str(sync_script), "--check"])

    python_files = []
    for skill in config.skills:
        python_files.extend((repo_root / "skills" / skill).rglob("*.py"))
    if python_files:
        check("python_syntax", [sys.executable, "-m", "py_compile", *map(str, python_files)])

    check("diff_check", ["git", "diff", "--check"])
    check("cached_diff_check", ["git", "diff", "--cached", "--check"])

    tests_root = repo_root / "tests"
    if config.skip_tests:
        checks.append({"name": "tests", "ok": True, "output": "skipped by --skip-tests"})
    elif tests_root.is_dir() and any(tests_root.glob("test_*.py")):
        check(
            "tests",
            [sys.executable, "-X", "utf8", "-m", "unittest", "discover", "-s", "tests", "-p", "test_*.py", "-v"],
        )
    else:
        checks.append({"name": "tests", "ok": True, "output": "no repository unittest files"})

    checks.append({"name": "changed_paths", "ok": True, "output": "\n".join(changed_paths)})
    return {"ok": all(bool(item.get("ok")) for item in checks), "checks": checks}


def remote_repository(repo_root: Path, remote: str) -> str:
    url = run_command(["git", "remote", "get-url", remote], repo_root)
    if url.startswith("git@github.com:"):
        value = url.split(":", 1)[1]
    else:
        parsed = urlparse(url)
        if parsed.hostname != "github.com":
            raise ReleaseError(f"远端不是 GitHub 仓库，无法自动创建 PR：{url}")
        value = parsed.path.lstrip("/")
    value = value.removesuffix(".git").strip("/")
    if value.count("/") != 1:
        raise ReleaseError(f"无法解析 GitHub 仓库：{url}")
    return value


def github_login(repo_root: Path, expected: str | None) -> str:
    try:
        login = run_command(["gh", "api", "user", "--jq", ".login"], repo_root).strip()
    except ReleaseError as exc:
        raise ReleaseError("GitHub CLI 未登录或不可用，请先完成 gh auth login") from exc
    if not login:
        raise ReleaseError("GitHub CLI 未返回当前账户")
    if expected and login.casefold() != expected.casefold():
        raise ReleaseError(f"GitHub 当前账户为 {login}，与要求账户 {expected} 不一致")
    return login


def find_open_pr(
    repo_root: Path,
    repository: str,
    branch: str,
    head_owner: str,
    base_branch: str,
) -> dict[str, object] | None:
    raw = run_command(
        [
            "gh",
            "pr",
            "list",
            "--repo",
            repository,
            "--head",
            f"{head_owner}:{branch}",
            "--base",
            base_branch,
            "--state",
            "open",
            "--json",
            "number,url,headRefName,headRepositoryOwner,baseRefName",
        ],
        repo_root,
    )
    try:
        records = json.loads(raw or "[]")
    except json.JSONDecodeError as exc:
        raise ReleaseError("GitHub CLI 返回的 PR 列表不是有效 JSON") from exc

    if not isinstance(records, list):
        raise ReleaseError("GitHub CLI 返回的 PR 列表格式不正确")

    for record in records:
        if not isinstance(record, dict):
            continue
        if record.get("headRefName") not in {None, branch}:
            continue
        owner = record.get("headRepositoryOwner")
        if isinstance(owner, dict) and owner.get("login") not in {None, head_owner}:
            continue
        if record.get("baseRefName") not in {None, base_branch}:
            continue
        return record

    return None


def remote_branch_sha(repo_root: Path, remote: str, branch: str) -> str | None:
    output = run_command(
        ["git", "ls-remote", "--heads", remote, f"refs/heads/{branch}"],
        repo_root,
    )
    for line in output.splitlines():
        parts = line.split()
        if len(parts) < 2 or parts[1] != f"refs/heads/{branch}":
            continue
        sha = parts[0]
        if not re.fullmatch(r"[0-9a-fA-F]{40,64}", sha):
            raise ReleaseError(f"远端分支 {branch} 返回了无效 commit SHA")
        return sha
    return None


def validate_remote_branch_reuse(branch: str, remote_sha: str | None, existing_pr: dict[str, object] | None) -> None:
    if remote_sha and not existing_pr:
        raise ReleaseError(
            f"远端分支 {branch} 已存在，但没有找到当前账户在目标 base 分支下的打开 PR；"
            "为避免覆盖未知改动，已停止。请更换作用域/日期，或先人工处理该分支。"
        )


def build_push_args(remote: str, branch: str, remote_sha: str | None) -> list[str]:
    if not remote_sha:
        return ["git", "push", "--set-upstream", remote, branch]

    return [
        "git",
        "push",
        f"--force-with-lease=refs/heads/{branch}:{remote_sha}",
        "--set-upstream",
        remote,
        branch,
    ]


def apply_source_changes(repo_root: Path, worktree: Path, base_ref: str, pathspecs: list[str], untracked: list[str]) -> None:
    patch = run_bytes(["git", "diff", "--binary", base_ref, "--", *pathspecs], repo_root)
    if patch:
        patch_path = worktree.parent / "source-changes.patch"
        patch_path.write_bytes(patch)
        try:
            run_command(["git", "apply", "--3way", "--index", str(patch_path)], worktree)
        finally:
            patch_path.unlink(missing_ok=True)

    for relative in untracked:
        source = repo_root / relative
        destination = worktree / relative
        if not source.is_file():
            continue
        if any(part in EXCLUDED_NAMES for part in Path(relative).parts) or source.name.endswith(EXCLUDED_SUFFIXES):
            continue
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, destination)


def create_worktree(repo_root: Path, branch: str, base_ref: str, pathspecs: list[str], untracked: list[str]) -> tuple[Path, Path]:
    parent = Path(tempfile.mkdtemp(prefix="ai-cut-skills-release-"))
    worktree = parent / "repo"
    branch_created = False
    try:
        run_command(["git", "worktree", "add", "-b", branch, str(worktree), base_ref], repo_root)
        branch_created = True
        apply_source_changes(repo_root, worktree, base_ref, pathspecs, untracked)
        return parent, worktree
    except Exception:
        if worktree.exists():
            run_command(["git", "worktree", "remove", "--force", str(worktree)], repo_root, check=False)
        if branch_created:
            run_command(["git", "branch", "-D", branch], repo_root, check=False)
        shutil.rmtree(parent, ignore_errors=True)
        raise


def remove_worktree(repo_root: Path, worktree: Path, parent: Path, branch: str | None = None) -> None:
    run_command(["git", "worktree", "remove", "--force", str(worktree)], repo_root, check=False)
    if branch:
        run_command(["git", "branch", "-D", branch], repo_root, check=False)
    shutil.rmtree(parent, ignore_errors=True)


def ensure_staged_scope(worktree: Path, pathspecs: list[str]) -> list[str]:
    run_command(["git", "add", "--all", "--", *pathspecs], worktree)
    staged = [line for line in run_command(["git", "diff", "--cached", "--name-only"], worktree).splitlines() if line]
    outside = [path for path in staged if not path_is_allowed(path, pathspecs)]
    if outside:
        raise ReleaseError(f"暂存区出现允许范围外文件：{', '.join(outside)}")
    if not staged:
        raise ReleaseError("目标路径没有可提交的变更")
    return staged


def pr_body(config: ReleaseConfig, branch: str, staged: list[str], checks: dict[str, object]) -> str:
    rows = checks.get("checks", [])
    status = "通过" if checks.get("ok") else "失败"
    check_lines = "\n".join(
        f"- {'通过' if row.get('ok') else '失败'}：{row.get('name')}"
        for row in rows
        if row.get("name") not in {"changed_paths"}
    )
    files = "\n".join(f"- `{path}`" for path in staged)
    return (
        f"## 变更\n\n{config.summary}\n\n"
        f"## 分支\n\n`{branch}`\n\n"
        f"## 文件\n\n{files}\n\n"
        f"## 校验（{status}）\n\n{check_lines}\n"
    )


def create_or_update_pr(worktree: Path, repository: str, branch: str, head_owner: str, title: str, body: str, base_branch: str) -> str:
    body_file = Path(tempfile.mkstemp(prefix="ai-cut-skills-pr-", suffix=".md")[1])
    body_file.write_text(body, encoding="utf-8")
    try:
        existing = find_open_pr(worktree, repository, branch, head_owner, base_branch)
        if existing:
            number = existing.get("number")
            url = existing.get("url")
            if not number or not isinstance(url, str) or not url:
                raise ReleaseError("已有 PR 缺少可用编号或 URL，已停止更新")
            run_command(
                [
                    "gh",
                    "pr",
                    "edit",
                    str(number),
                    "--repo",
                    repository,
                    "--title",
                    title,
                    "--body-file",
                    str(body_file),
                ],
                worktree,
            )
            return url
        return run_command(
            [
                "gh",
                "pr",
                "create",
                "--repo",
                repository,
                "--base",
                base_branch,
                "--head",
                f"{head_owner}:{branch}",
                "--title",
                title,
                "--body-file",
                str(body_file),
            ],
            worktree,
        ).splitlines()[-1].strip()
    finally:
        body_file.unlink(missing_ok=True)


def parse_args(argv: list[str] | None = None) -> ReleaseConfig:
    parser = argparse.ArgumentParser(description="提交 ai-cut-skills 仓库的限定范围改动并创建 GitHub PR")
    parser.add_argument("--repo-root", type=Path, default=Path.cwd())
    parser.add_argument("--skill", action="append", required=True, help="目标 Skill 名称，可重复")
    parser.add_argument("--include", action="append", default=[], help="额外允许提交的仓库相对路径，可重复")
    parser.add_argument("--group", required=True, help="分支组别，例如 014-code")
    parser.add_argument("--change-type", required=True, choices=sorted(CHANGE_TYPES))
    parser.add_argument("--scope", help="分支作用域，默认使用目标 Skill 名称")
    parser.add_argument("--summary", required=True, help="commit 和 PR 摘要")
    parser.add_argument("--date", default=datetime.now().strftime("%Y%m%d"), help="分支日期 YYYYMMDD")
    parser.add_argument("--base-remote", default="upstream")
    parser.add_argument("--base-branch", default="main")
    parser.add_argument("--push-remote", default="origin")
    parser.add_argument("--github-account", help="期望的 GitHub 登录账户，仅作一致性校验")
    parser.add_argument("--target-repository", help="GitHub owner/repo；默认从 base remote 解析")
    parser.add_argument("--execute", action="store_true", help="执行创建分支、commit、push 和 PR")
    parser.add_argument("--skip-tests", action="store_true")
    parser.add_argument("--keep-worktree", action="store_true")
    args = parser.parse_args(argv)

    skills = tuple(dict.fromkeys(args.skill))
    scope = args.scope or "-".join(skills)
    includes = tuple(normalize_relative_path(value) for value in args.include)
    return ReleaseConfig(
        repo_root=args.repo_root.resolve(),
        skills=skills,
        includes=includes,
        group=validate_segment(args.group, "组别"),
        change_type=args.change_type,
        summary=args.summary.strip(),
        scope=validate_segment(scope, "作用域"),
        date=validate_date(args.date),
        base_remote=args.base_remote,
        base_branch=validate_segment(args.base_branch, "基线分支"),
        push_remote=args.push_remote,
        github_account=args.github_account,
        target_repository=args.target_repository,
        execute=args.execute,
        skip_tests=args.skip_tests,
        keep_worktree=args.keep_worktree,
    )


def run_release(config: ReleaseConfig) -> dict[str, object]:
    repo_root = Path(run_command(["git", "rev-parse", "--show-toplevel"], config.repo_root)).resolve()
    validate_skill_paths(repo_root, config.skills)
    pathspecs = selected_pathspecs(config)
    branch = build_branch_name(config.group, config.change_type, config.scope, config.date)
    base_ref = f"{config.base_remote}/{config.base_branch}"

    if not config.execute:
        tracked, untracked = list_changed_paths(repo_root, None, pathspecs)
        checks = run_checks(repo_root, config, changed_paths=tracked + untracked)
        return {
            "status": "planned",
            "branch": branch,
            "base": base_ref,
            "pathspecs": pathspecs,
            "changed_paths": tracked + untracked,
            "checks": checks,
            "execute_command": "加 --execute 执行提交、推送和创建 PR",
        }

    run_command(["git", "fetch", config.base_remote, config.base_branch], repo_root)
    run_command(["git", "rev-parse", "--verify", base_ref], repo_root)
    tracked, untracked = list_changed_paths(repo_root, base_ref, pathspecs)
    changed = tracked + untracked
    if not changed:
        raise ReleaseError("目标 Skill 相对最新基线没有可提交变更")

    repository = config.target_repository or remote_repository(repo_root, config.base_remote)
    head_owner = github_login(repo_root, config.github_account)
    existing_pr = find_open_pr(repo_root, repository, branch, head_owner, config.base_branch)
    existing_remote_sha = remote_branch_sha(repo_root, config.push_remote, branch)
    validate_remote_branch_reuse(branch, existing_remote_sha, existing_pr)
    parent, worktree = create_worktree(repo_root, branch, base_ref, pathspecs, untracked)
    try:
        staged = ensure_staged_scope(worktree, pathspecs)
        checks = run_checks(worktree, config, changed_paths=staged)
        if not checks.get("ok"):
            raise ReleaseError("提交前校验失败，请先处理 PR 检查结果")
        title = f"{config.change_type}({config.scope}): {config.summary}"
        body = pr_body(config, branch, staged, checks)
        run_command(["git", "commit", "-m", title], worktree)
        run_command(build_push_args(config.push_remote, branch, existing_remote_sha), worktree)
        pr_url = create_or_update_pr(worktree, repository, branch, head_owner, title, body, config.base_branch)
        result = {
            "status": "submitted",
            "branch": branch,
            "commit": run_command(["git", "rev-parse", "HEAD"], worktree),
            "repository": repository,
            "pr_url": pr_url,
            "files": staged,
            "checks": checks,
        }
    finally:
        if not config.keep_worktree:
            remove_worktree(repo_root, worktree, parent, branch)
    return result


def main(argv: list[str] | None = None) -> int:
    try:
        config = parse_args(argv)
        result = run_release(config)
    except ReleaseError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
