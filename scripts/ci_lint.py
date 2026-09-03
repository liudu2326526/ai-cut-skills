#!/usr/bin/env python3
"""Zero-side-effect repository lint checks used by pull requests."""

from __future__ import annotations

import argparse
import ast
import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Any

import yaml


REPO_ROOT = Path(__file__).resolve().parents[1]
PINNED_ACTION = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+@[0-9a-f]{40}$")


class WorkflowLoader(yaml.SafeLoader):
    """YAML 1.2-like loader that does not treat ``on`` as a boolean."""


WorkflowLoader.yaml_implicit_resolvers = {
    key: list(value) for key, value in yaml.SafeLoader.yaml_implicit_resolvers.items()
}
for first_character, resolvers in list(WorkflowLoader.yaml_implicit_resolvers.items()):
    WorkflowLoader.yaml_implicit_resolvers[first_character] = [
        resolver for resolver in resolvers if resolver[0] != "tag:yaml.org,2002:bool"
    ]
WorkflowLoader.add_implicit_resolver(
    "tag:yaml.org,2002:bool",
    re.compile(r"^(?:true|false)$", re.IGNORECASE),
    list("tTfF"),
)


def tracked_files() -> list[Path]:
    process = subprocess.run(
        ["git", "ls-files", "--cached", "--others", "--exclude-standard", "-z"],
        cwd=REPO_ROOT,
        check=True,
        capture_output=True,
    )
    return [REPO_ROOT / item.decode("utf-8") for item in process.stdout.split(b"\0") if item]


def validate_python(path: Path) -> list[str]:
    try:
        ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    except (SyntaxError, UnicodeDecodeError) as exc:
        return [f"{path.relative_to(REPO_ROOT)}: {exc}"]
    return []


def validate_json(path: Path) -> list[str]:
    try:
        json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        return [f"{path.relative_to(REPO_ROOT)}: {exc}"]
    return []


def _iter_steps(workflow: dict[str, Any]):
    jobs = workflow.get("jobs", {})
    if not isinstance(jobs, dict):
        return
    for job in jobs.values():
        if not isinstance(job, dict):
            continue
        for step in job.get("steps", []):
            if isinstance(step, dict):
                yield step


def validate_workflow(path: Path) -> list[str]:
    relative = path.relative_to(REPO_ROOT)
    errors: list[str] = []
    try:
        workflow = yaml.load(path.read_text(encoding="utf-8"), Loader=WorkflowLoader)
    except (yaml.YAMLError, UnicodeDecodeError) as exc:
        return [f"{relative}: invalid YAML: {exc}"]
    if not isinstance(workflow, dict):
        return [f"{relative}: workflow root must be an object"]
    if not isinstance(workflow.get("name"), str) or not workflow["name"].strip():
        errors.append(f"{relative}: workflow name is required")
    if "on" not in workflow:
        errors.append(f"{relative}: workflow trigger is required")
    if not isinstance(workflow.get("permissions"), dict):
        errors.append(f"{relative}: explicit least-privilege permissions are required")
    jobs = workflow.get("jobs")
    if not isinstance(jobs, dict) or not jobs:
        errors.append(f"{relative}: jobs must be a non-empty object")
    if "pull_request_target" in workflow.get("on", {}):
        errors.append(f"{relative}: pull_request_target is forbidden")
    for step in _iter_steps(workflow) or ():
        action = step.get("uses")
        if isinstance(action, str) and not action.startswith("./") and not PINNED_ACTION.fullmatch(action):
            errors.append(f"{relative}: action must be pinned to a full commit SHA: {action}")
        command = step.get("run")
        if isinstance(command, str) and "${{ github.event.pull_request" in command:
            errors.append(
                f"{relative}: do not interpolate pull-request fields directly into shell commands"
            )
    return errors


def validate_diff_whitespace(base_sha: str | None, head_sha: str | None) -> list[str]:
    if not base_sha or not head_sha:
        return []
    process = subprocess.run(
        ["git", "diff", "--check", f"{base_sha}...{head_sha}"],
        cwd=REPO_ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    return [line for line in process.stdout.splitlines() if line]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base")
    parser.add_argument("--head")
    args = parser.parse_args(argv)
    errors: list[str] = []
    for path in tracked_files():
        if path.suffix == ".py":
            errors.extend(validate_python(path))
        elif path.suffix == ".json" or path.name == "skill-catalog.yaml":
            errors.extend(validate_json(path))
        elif path.parent == REPO_ROOT / ".github" / "workflows" and path.suffix in {".yml", ".yaml"}:
            errors.extend(validate_workflow(path))
    errors.extend(validate_diff_whitespace(args.base, args.head))
    if errors:
        print("Repository lint failed:", file=sys.stderr)
        for error in errors:
            print(f"- {error}", file=sys.stderr)
        return 1
    print("Repository lint passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
