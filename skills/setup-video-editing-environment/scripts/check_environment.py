#!/usr/bin/env python3
"""Check cross-platform dependencies used by AI video-editing Skills."""

from __future__ import annotations

import argparse
import json
import os
import platform
import shutil
import subprocess
import sys
import sysconfig
from pathlib import Path
from typing import Any


MINIMUM_PYTHON = (3, 10)
REQUIRED_FILTERS = ("subtitles", "loudnorm", "ebur128")
REQUIRED_ENCODERS = ("libx264", "aac")
PROFILES = {
    "base-video": {"whisper": "unused", "asset_skill": False},
    "soda-scripted-render": {"whisper": "required", "asset_skill": True},
    "soda-timeline-render": {"whisper": "optional", "asset_skill": True},
    "soda-detect-pauses": {"whisper": "optional", "asset_skill": False},
}
MOTION_MODES = ("auto", "off", "required")
SKILL_ROOT = Path(__file__).resolve().parent.parent
SKILLS_ROOT = SKILL_ROOT.parent


def run_capture(command: list[str], timeout: int = 30) -> dict[str, Any]:
    try:
        process = subprocess.run(
            command,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
            timeout=timeout,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return {"ok": False, "output": "", "error": str(exc)}
    output = "\n".join(value for value in (process.stdout, process.stderr) if value)
    return {
        "ok": process.returncode == 0,
        "output": output,
        "error": None if process.returncode == 0 else output.strip()[:500],
    }


def first_line(value: str) -> str | None:
    return next((line.strip() for line in value.splitlines() if line.strip()), None)


def binary_check(name: str) -> dict[str, Any]:
    executable = shutil.which(name)
    if not executable:
        return {"ok": False, "path": None, "version": None, "error": f"{name} not found in PATH"}
    result = run_capture([executable, "-version"])
    return {
        "ok": bool(result["ok"]),
        "path": executable,
        "version": first_line(str(result["output"])),
        "error": result["error"],
    }


def ffmpeg_check() -> dict[str, Any]:
    check = binary_check("ffmpeg")
    executable = check.get("path")
    if not executable or not check["ok"]:
        return check
    filters = run_capture([str(executable), "-hide_banner", "-filters"])
    encoders = run_capture([str(executable), "-hide_banner", "-encoders"])
    filter_text = str(filters["output"])
    encoder_text = str(encoders["output"])
    missing_filters = [name for name in REQUIRED_FILTERS if name not in filter_text]
    missing_encoders = [name for name in REQUIRED_ENCODERS if name not in encoder_text]
    check.update(
        {
            "required_filters": list(REQUIRED_FILTERS),
            "missing_filters": missing_filters,
            "required_encoders": list(REQUIRED_ENCODERS),
            "missing_encoders": missing_encoders,
            "ok": bool(filters["ok"] and encoders["ok"] and not missing_filters and not missing_encoders),
        }
    )
    if not check["ok"]:
        check["error"] = (
            "ffmpeg lacks required capabilities: filters="
            + ",".join(missing_filters)
            + " encoders="
            + ",".join(missing_encoders)
        )
    return check


def find_skill(name: str) -> Path | None:
    codex_home = Path(os.environ.get("CODEX_HOME", Path.home() / ".codex")).expanduser()
    workbuddy_home = Path(os.environ.get("WORKBUDDY_HOME", Path.home() / ".workbuddy")).expanduser()
    candidates = [SKILLS_ROOT / name, codex_home / "skills" / name, workbuddy_home / "skills" / name]
    seen: set[Path] = set()
    for candidate in candidates:
        resolved = candidate.resolve()
        if resolved in seen:
            continue
        seen.add(resolved)
        if (resolved / "SKILL.md").is_file():
            return resolved
    return None


def whisper_cache_candidates() -> list[Path]:
    roots: list[Path] = []
    xdg = os.environ.get("XDG_CACHE_HOME")
    if xdg:
        roots.append(Path(xdg).expanduser())
    roots.append(Path.home() / ".cache")
    candidates: list[Path] = []
    for root in roots:
        candidate = (root / "whisper" / "tiny.pt").resolve()
        if candidate not in candidates:
            candidates.append(candidate)
    return candidates


def whisper_cli_candidate() -> tuple[str | None, bool]:
    from_path = shutil.which("whisper")
    if from_path:
        return from_path, True
    scripts = Path(sysconfig.get_path("scripts"))
    names = ("whisper.exe", "whisper") if os.name == "nt" else ("whisper",)
    for name in names:
        candidate = scripts / name
        if candidate.is_file():
            return str(candidate.resolve()), False
    return None, False


def whisper_check(mode: str) -> dict[str, Any]:
    required = mode == "required"
    executable, visible_in_path = whisper_cli_candidate()
    module = run_capture([sys.executable, "-c", "import whisper; print(whisper.__file__)"])
    cli = run_capture([str(executable), "--help"]) if executable else {"ok": False, "error": "CLI not found"}
    candidates = whisper_cache_candidates()
    cached = next((path for path in candidates if path.is_file()), None)
    usable = bool(module["ok"] and cli["ok"] and visible_in_path and cached)
    return {
        "ok": usable,
        "required": required,
        "mode": mode,
        "python_package": bool(module["ok"]),
        "python_package_path": first_line(str(module.get("output", ""))),
        "cli_path": executable,
        "cli_usable": bool(cli["ok"]),
        "cli_visible_in_path": visible_in_path,
        "tiny_model_cached": bool(cached),
        "tiny_model_path": str(cached) if cached else None,
        "cache_candidates": [str(path) for path in candidates],
    }


def chrome_path() -> str | None:
    variables = [os.environ.get("CHROME_PATH")]
    if os.name == "nt":
        for variable in ("PROGRAMFILES", "PROGRAMFILES(X86)", "LOCALAPPDATA"):
            root = os.environ.get(variable)
            if root:
                variables.extend(
                    [
                        str(Path(root) / "Google" / "Chrome" / "Application" / "chrome.exe"),
                        str(Path(root) / "Chromium" / "Application" / "chrome.exe"),
                    ]
                )
    else:
        variables.extend(
            [
                "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
                "/Applications/Chromium.app/Contents/MacOS/Chromium",
                "/usr/bin/google-chrome",
                "/usr/bin/chromium",
            ]
        )
    return next((value for value in variables if value and Path(value).is_file()), None)


def motion_check(mode: str) -> dict[str, Any]:
    required = mode == "required"
    if mode == "off":
        return {"ok": True, "required": False, "mode": mode, "status": "disabled"}
    root = find_skill("video-motion-effects")
    cli = root / "scripts" / "remotion" / "render.mjs" if root else None
    project = cli.parent if cli else None
    dependencies = (
        "remotion/package.json",
        "@remotion/renderer/package.json",
        "@remotion/bundler/package.json",
        "@vysmo/transitions/package.json",
    )
    missing: list[str] = []
    if not root:
        missing.append("video-motion-effects")
    if not cli or not cli.is_file():
        missing.append("render.mjs")
    if not shutil.which("node"):
        missing.append("node")
    chrome = chrome_path()
    if not chrome:
        missing.append("chrome")
    if project:
        for relative in dependencies:
            if not (project / "node_modules" / relative).is_file():
                missing.append("node_modules/" + relative)
    ready = not missing
    return {
        "ok": ready or not required,
        "required": required,
        "mode": mode,
        "status": "ready" if ready else "static_fallback",
        "ready": ready,
        "skill_root": str(root) if root else None,
        "node": shutil.which("node"),
        "chrome": chrome,
        "missing": missing,
    }


def platform_guidance() -> list[str]:
    system = platform.system()
    skill = str(SKILL_ROOT)
    if system == "Windows":
        return [
            "Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass",
            f'& "{skill}\\scripts\\setup_windows.ps1" -Profile soda-scripted-render -MotionEffects auto -Install -EnvironmentName ai-video-editing',
            "Keep using the same PowerShell session so its Python Scripts PATH remains active.",
        ]
    if system == "Darwin":
        return [
            f'python3 "{skill}/scripts/discover_environments.py" --profile soda-scripted-render --motion-effects auto',
            "brew install python@3.11 ffmpeg",
            "python3.11 -m venv ~/.virtualenvs/ai-video-editing",
            "~/.virtualenvs/ai-video-editing/bin/python -m pip install -U openai-whisper",
            '~/.virtualenvs/ai-video-editing/bin/python -c \'import whisper; whisper.load_model("tiny")\'',
        ]
    return [
        f'python3 "{skill}/scripts/discover_environments.py" --profile soda-scripted-render --motion-effects auto',
        "sudo apt-get update && sudo apt-get install -y python3 python3-venv python3-pip ffmpeg",
        "python3 -m venv ~/.virtualenvs/ai-video-editing",
        "~/.virtualenvs/ai-video-editing/bin/python -m pip install -U openai-whisper",
        '~/.virtualenvs/ai-video-editing/bin/python -c \'import whisper; whisper.load_model("tiny")\'',
    ]


def collect_environment(profile: str, motion_effects: str) -> dict[str, Any]:
    if profile not in PROFILES:
        raise ValueError(f"Unknown profile: {profile}")
    if motion_effects not in MOTION_MODES:
        raise ValueError(f"Unknown motion mode: {motion_effects}")
    policy = PROFILES[profile]
    whisper = whisper_check(str(policy["whisper"]))
    asset_root = find_skill("manage-visual-asset-library")
    checks: dict[str, dict[str, Any]] = {
        "python": {
            "ok": sys.version_info >= MINIMUM_PYTHON,
            "required": True,
            "path": sys.executable,
            "version": platform.python_version(),
            "minimum": ".".join(str(item) for item in MINIMUM_PYTHON),
        },
        "ffmpeg": {**ffmpeg_check(), "required": True},
        "ffprobe": {**binary_check("ffprobe"), "required": True},
        "whisper": whisper,
        "manage_visual_asset_library": {
            "ok": asset_root is not None,
            "required": bool(policy["asset_skill"]),
            "path": str(asset_root) if asset_root else None,
        },
        "video_motion_effects": motion_check(motion_effects),
    }
    errors = [name for name, check in checks.items() if check.get("required") and not check.get("ok")]
    warnings: list[str] = []
    if policy["whisper"] == "optional" and not whisper["ok"]:
        warnings.append("Whisper is incomplete; this profile may continue without word timestamps.")
    if motion_effects == "auto" and not checks["video_motion_effects"].get("ready"):
        warnings.append("Motion effects are incomplete; rendering may use static overlays.")
    return {
        "ok": not errors,
        "status": "ready" if not errors else "blocked",
        "profile": profile,
        "motion_effects": motion_effects,
        "current_environment": {
            "platform": platform.platform(),
            "python_executable": sys.executable,
            "python_version": platform.python_version(),
            "virtual_env": os.environ.get("VIRTUAL_ENV"),
        },
        "environment_policy": {
            "capability_validation_required": True,
            "environment_name_is_not_evidence": True,
            "business_environment_may_be_reused_if_valid": True,
            "discover_before_install": True,
        },
        "checks": checks,
        "errors": errors,
        "warnings": warnings,
        "setup_guidance": platform_guidance(),
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--profile", choices=tuple(PROFILES), default="soda-scripted-render")
    parser.add_argument("--motion-effects", choices=MOTION_MODES, default="auto")
    parser.add_argument("--output-json", type=Path)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    report = collect_environment(args.profile, args.motion_effects)
    content = json.dumps(report, ensure_ascii=False, indent=2) + "\n"
    if args.output_json:
        output = args.output_json.expanduser().resolve()
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(content, encoding="utf-8")
    print(content, end="")
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
