#!/usr/bin/env python3
"""Discover and capability-check reusable Python environments before installation."""

from __future__ import annotations

import argparse
import json
import os
import platform
import re
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any, Callable, Iterable


UNIFIED_ENVIRONMENT_NAME = "ai-video-editing"
SKILL_ROOT = Path(__file__).resolve().parent.parent
CHECK_SCRIPT = SKILL_ROOT / "scripts" / "check_environment.py"
PROFILES = (
    "base-video",
    "soda-scripted-render",
    "soda-timeline-render",
    "soda-detect-pauses",
)
MOTION_MODES = ("auto", "off", "required")


def environment_python_paths(root: Path, system: str | None = None) -> list[Path]:
    current_system = system or platform.system()
    if current_system == "Windows":
        return [root / "Scripts" / "python.exe", root / "python.exe", root / "bin" / "python.exe"]
    return [root / "bin" / "python", root / "python"]


def default_environment_path(home: Path | None = None) -> Path:
    return (home or Path.home()) / ".virtualenvs" / UNIFIED_ENVIRONMENT_NAME


def add_candidate(
    candidates: list[dict[str, Any]],
    seen: dict[str, dict[str, Any]],
    path: str | Path | None,
    source: str,
    *,
    include_missing: bool = False,
) -> None:
    if not path:
        return
    candidate_path = Path(path).expanduser()
    # Preserve a venv's Python path instead of resolving its symlink to the base
    # interpreter; invoking the venv path is what activates its sys.prefix.
    normalized = Path(os.path.abspath(str(candidate_path)))
    key = os.path.normcase(str(normalized))
    existing = seen.get(key)
    if existing:
        if source not in existing["sources"]:
            existing["sources"].append(source)
        return
    if not include_missing and not normalized.is_file():
        return
    candidate = {"python_executable": str(normalized), "sources": [source]}
    candidates.append(candidate)
    seen[key] = candidate


def add_environment_root(
    candidates: list[dict[str, Any]],
    seen: dict[str, dict[str, Any]],
    root: Path,
    source: str,
    *,
    system: str | None = None,
) -> None:
    for python_path in environment_python_paths(root, system):
        if python_path.is_file():
            add_candidate(candidates, seen, python_path, source)
            return


def conda_environment_roots() -> list[Path]:
    conda = shutil.which("conda")
    if not conda:
        return []
    try:
        process = subprocess.run(
            [conda, "env", "list", "--json"],
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
            timeout=20,
        )
        payload = json.loads(process.stdout) if process.returncode == 0 else {}
    except (OSError, subprocess.TimeoutExpired, json.JSONDecodeError):
        return []
    return [Path(value).expanduser() for value in payload.get("envs", []) if isinstance(value, str)]


def windows_launcher_pythons() -> list[Path]:
    if platform.system() != "Windows":
        return []
    launcher = shutil.which("py")
    if not launcher:
        return []
    try:
        process = subprocess.run(
            [launcher, "-0p"],
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
            timeout=20,
        )
    except (OSError, subprocess.TimeoutExpired):
        return []
    paths: list[Path] = []
    for line in process.stdout.splitlines():
        match = re.search(r"([A-Za-z]:\\.*?python(?:\.exe)?)\s*$", line.strip(), re.IGNORECASE)
        if match:
            paths.append(Path(match.group(1)))
    return paths


def discover_candidates(
    explicit_pythons: Iterable[str] = (),
    *,
    cwd: Path | None = None,
    home: Path | None = None,
    environ: dict[str, str] | None = None,
) -> list[dict[str, Any]]:
    workdir = (cwd or Path.cwd()).expanduser().resolve()
    user_home = (home or Path.home()).expanduser().resolve()
    environment = dict(os.environ) if environ is None else environ
    system = platform.system()
    candidates: list[dict[str, Any]] = []
    seen: dict[str, dict[str, Any]] = {}

    for value in explicit_pythons:
        add_candidate(candidates, seen, value, "explicit", include_missing=True)

    add_candidate(candidates, seen, sys.executable, "current-python")

    for variable in ("VIRTUAL_ENV", "CONDA_PREFIX"):
        value = environment.get(variable)
        if value:
            add_environment_root(candidates, seen, Path(value), f"activated:{variable}", system=system)

    add_environment_root(
        candidates,
        seen,
        default_environment_path(user_home),
        f"unified:{UNIFIED_ENVIRONMENT_NAME}",
        system=system,
    )

    try:
        project_children = sorted(path for path in workdir.iterdir() if path.is_dir())
    except OSError:
        project_children = []
    for root in project_children:
        if (root / "pyvenv.cfg").is_file() or root.name in {".venv", "venv"}:
            add_environment_root(candidates, seen, root, "project-virtualenv", system=system)

    for parent_name in (".virtualenvs", ".venvs"):
        parent = user_home / parent_name
        if not parent.is_dir():
            continue
        try:
            roots = sorted(path for path in parent.iterdir() if path.is_dir())
        except OSError:
            roots = []
        for root in roots:
            add_environment_root(candidates, seen, root, f"managed-root:{parent_name}", system=system)

    for root in conda_environment_roots():
        add_environment_root(candidates, seen, root, "conda", system=system)

    for python_path in windows_launcher_pythons():
        add_candidate(candidates, seen, python_path, "windows-py-launcher")

    for command in ("python", "python3"):
        add_candidate(candidates, seen, shutil.which(command), f"PATH:{command}")

    return candidates


def validate_candidate(
    candidate: dict[str, Any],
    profile: str,
    motion_effects: str,
    timeout: int,
) -> dict[str, Any]:
    python_executable = Path(str(candidate["python_executable"]))
    result = {**candidate, "ok": False, "status": "invalid", "report": None, "error": None}
    if not python_executable.is_file():
        result["status"] = "missing"
        result["error"] = "Python executable does not exist"
        return result

    environment = dict(os.environ)
    environment["PATH"] = str(python_executable.parent) + os.pathsep + environment.get("PATH", "")
    command = [
        str(python_executable),
        str(CHECK_SCRIPT),
        "--profile",
        profile,
        "--motion-effects",
        motion_effects,
    ]
    try:
        process = subprocess.run(
            command,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
            timeout=timeout,
            env=environment,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        result["error"] = str(exc)
        return result

    try:
        report = json.loads(process.stdout)
    except json.JSONDecodeError:
        result["error"] = (process.stderr or process.stdout or "Invalid checker output").strip()[:1000]
        return result

    reusable = process.returncode == 0 and bool(report.get("ok"))
    result.update(
        {
            "ok": reusable,
            "status": "reusable" if reusable else "capability-check-failed",
            "report": report,
            "error": None if reusable else (process.stderr.strip() or None),
        }
    )
    return result


Validator = Callable[[dict[str, Any], str, str, int], dict[str, Any]]


def evaluate_candidates(
    candidates: list[dict[str, Any]],
    profile: str,
    motion_effects: str,
    timeout: int,
    validator: Validator = validate_candidate,
) -> tuple[dict[str, Any] | None, list[dict[str, Any]]]:
    evaluations: list[dict[str, Any]] = []
    for candidate in candidates:
        evaluation = validator(candidate, profile, motion_effects, timeout)
        evaluations.append(evaluation)
        if evaluation.get("ok"):
            return evaluation, evaluations
    return None, evaluations


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--profile", choices=PROFILES, default="soda-scripted-render")
    parser.add_argument("--motion-effects", choices=MOTION_MODES, default="auto")
    parser.add_argument("--python", action="append", default=[], dest="pythons")
    parser.add_argument("--candidate-timeout", type=int, default=120)
    parser.add_argument("--output-json", type=Path)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    candidates = discover_candidates(args.pythons)
    selected, evaluations = evaluate_candidates(
        candidates,
        args.profile,
        args.motion_effects,
        args.candidate_timeout,
    )
    report = {
        "ok": selected is not None,
        "status": "reusable-environment-found" if selected else "installation-required",
        "profile": args.profile,
        "motion_effects": args.motion_effects,
        "selected_environment": selected,
        "candidates": evaluations,
        "install_required": selected is None,
        "recommended_environment_name": UNIFIED_ENVIRONMENT_NAME,
        "recommended_environment_path": str(default_environment_path().resolve()),
        "environment_policy": {
            "discover_before_install": True,
            "validate_by_capability_not_name": True,
            "business_environments_may_be_reused_if_valid": True,
            "named_environment_is_never_assumed_valid": True,
        },
    }
    content = json.dumps(report, ensure_ascii=False, indent=2) + "\n"
    if args.output_json:
        output = args.output_json.expanduser().resolve()
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(content, encoding="utf-8")
    print(content, end="")
    return 0 if selected else 2


if __name__ == "__main__":
    raise SystemExit(main())
