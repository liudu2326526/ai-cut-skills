from __future__ import annotations

import sys
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "scripts"))

import ci_security_scan  # noqa: E402


class SecurityScanTests(unittest.TestCase):
    def test_added_secret_is_detected_without_echoing_value(self) -> None:
        fake_key = "sk-" + "abcdefghijklmnopqrstuvwxyz123456"
        diff = "\n".join(
            [
                "+++ b/example.py",
                "@@ -0,0 +1 @@",
                f"+TOKEN = '{fake_key}'",
            ]
        )
        findings = ci_security_scan.scan_added_lines(ci_security_scan.parse_added_lines(diff))
        self.assertEqual(findings, ["example.py:1: possible OpenAI-style API key"])
        self.assertNotIn("abcdefghijklmnopqrstuvwxyz", findings[0])

    def test_sensitive_filename_is_blocked(self) -> None:
        findings = ci_security_scan.validate_changed_paths(["skills/demo/.env"])
        self.assertEqual(len(findings), 1)

    def test_regular_added_line_is_allowed(self) -> None:
        lines = [ci_security_scan.AddedLine("README.md", 4, "No credentials here")]
        self.assertEqual(ci_security_scan.scan_added_lines(lines), [])


if __name__ == "__main__":
    unittest.main()
