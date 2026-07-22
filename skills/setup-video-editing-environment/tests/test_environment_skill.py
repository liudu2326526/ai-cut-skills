#!/usr/bin/env python3

from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest import mock


SKILL_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = SKILL_ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import check_environment  # noqa: E402
import discover_environments  # noqa: E402


def fake_run(command: list[str], timeout: int = 30) -> dict[str, object]:
    del timeout
    if command[-1] == "-filters":
        output = "subtitles loudnorm ebur128"
    elif command[-1] == "-encoders":
        output = "libx264 aac"
    elif "import whisper" in command[-1]:
        return {"ok": False, "output": "", "error": "missing"}
    else:
        output = "version ok"
    return {"ok": True, "output": output, "error": None}


def fake_which(name: str) -> str | None:
    return {
        "ffmpeg": "C:\\Tools\\ffmpeg.exe",
        "ffprobe": "C:\\Tools\\ffprobe.exe",
        "whisper": None,
        "node": None,
    }.get(name)


class EnvironmentSkillTests(unittest.TestCase):
    @mock.patch.object(check_environment, "run_capture", side_effect=fake_run)
    @mock.patch.object(check_environment.shutil, "which", side_effect=fake_which)
    def test_scripted_profile_blocks_without_whisper(self, _which: mock.Mock, _run: mock.Mock) -> None:
        report = check_environment.collect_environment("soda-scripted-render", "off")

        self.assertFalse(report["ok"])
        self.assertIn("whisper", report["errors"])
        self.assertTrue(report["environment_policy"]["capability_validation_required"])
        self.assertTrue(report["environment_policy"]["business_environment_may_be_reused_if_valid"])

    @mock.patch.object(check_environment.platform, "system", return_value="Windows")
    def test_windows_guidance_uses_powershell_setup(self, _system: mock.Mock) -> None:
        guidance = "\n".join(check_environment.platform_guidance())

        self.assertIn("setup_windows.ps1", guidance)
        self.assertIn("PowerShell", guidance)
        self.assertNotIn("apt-get", guidance)
        self.assertNotIn("brew install", guidance)

    def test_windows_script_contains_required_install_and_path_steps(self) -> None:
        script = (SCRIPTS / "setup_windows.ps1").read_text(encoding="utf-8")
        windows = (SKILL_ROOT / "references" / "windows.md").read_text(encoding="utf-8")
        combined = script + "\n" + windows

        self.assertIn("Python.Python.3.11", combined)
        self.assertIn("Gyan.FFmpeg", combined)
        self.assertIn("openai-whisper", combined)
        self.assertIn("load_model('tiny')", script)
        self.assertIn("sysconfig.get_path('scripts')", script)
        self.assertIn("discover_environments.py", script)
        self.assertIn('EnvironmentName = "ai-video-editing"', script)
        self.assertIn("Set-ExecutionPolicy -Scope Process", windows)
        self.assertIn("能力检查", windows)
        self.assertNotIn("smart-flow-agent", combined)

    def test_discovery_selects_first_capability_valid_candidate(self) -> None:
        candidates = [
            {"python_executable": "/envs/business/bin/python", "sources": ["conda"]},
            {"python_executable": "/envs/ai-video-editing/bin/python", "sources": ["unified"]},
        ]

        def validator(
            candidate: dict[str, object], profile: str, motion: str, timeout: int
        ) -> dict[str, object]:
            del profile, motion, timeout
            return {**candidate, "ok": "business" in str(candidate["python_executable"])}

        selected, evaluations = discover_environments.evaluate_candidates(
            candidates,
            "soda-scripted-render",
            "auto",
            5,
            validator=validator,
        )

        self.assertEqual(selected["python_executable"], "/envs/business/bin/python")
        self.assertEqual(len(evaluations), 1)

    def test_unified_name_is_only_install_fallback(self) -> None:
        self.assertEqual(discover_environments.UNIFIED_ENVIRONMENT_NAME, "ai-video-editing")
        self.assertEqual(
            discover_environments.default_environment_path(Path("/home/test")),
            Path("/home/test/.virtualenvs/ai-video-editing"),
        )

        skill = (SKILL_ROOT / "SKILL.md").read_text(encoding="utf-8")
        self.assertIn("按能力而不是环境名称判断", skill)
        self.assertIn("所有候选均不合格", skill)

    def test_skill_has_no_placeholder_sections(self) -> None:
        skill = (SKILL_ROOT / "SKILL.md").read_text(encoding="utf-8")

        self.assertNotIn("TODO", skill)
        self.assertIn("Windows 快速入口", skill)
        self.assertIn("macOS/Linux", skill)
        self.assertIn("discover_environments.py", skill)


if __name__ == "__main__":
    unittest.main()
