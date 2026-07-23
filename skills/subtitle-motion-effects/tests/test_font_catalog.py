from __future__ import annotations

import json
import subprocess
import tempfile
import unittest
from pathlib import Path


SKILL_ROOT = Path(__file__).resolve().parents[1]
RENDERER = SKILL_ROOT / "scripts" / "remotion" / "render.mjs"


class FontCatalogTests(unittest.TestCase):
    def validate_timeline(self, timeline: dict) -> subprocess.CompletedProcess[str]:
        with tempfile.TemporaryDirectory() as temp_dir:
            timeline_path = Path(temp_dir) / "timeline.json"
            timeline_path.write_text(
                json.dumps(timeline, ensure_ascii=False), encoding="utf-8"
            )
            return subprocess.run(
                [
                    "node",
                    str(RENDERER),
                    "validate",
                    "--timeline-json",
                    str(timeline_path),
                    "--asset-root",
                    str(SKILL_ROOT),
                ],
                check=False,
                capture_output=True,
                text=True,
            )

    def test_catalog_paths_exist_and_families_are_unique(self) -> None:
        catalog = json.loads(
            (SKILL_ROOT / "references" / "font-catalog.json").read_text(
                encoding="utf-8"
            )
        )
        fonts = catalog["fonts"]
        self.assertEqual(len(fonts), 8)
        self.assertEqual(len({font["family"] for font in fonts}), len(fonts))
        for font in fonts:
            with self.subTest(font=font["family"]):
                path = SKILL_ROOT / font["path"]
                self.assertTrue(path.is_file(), path)
                self.assertGreater(path.stat().st_size, 0)

    def test_default_templates_use_declared_font_paths(self) -> None:
        for filename in ("timeline-template.json", "preset-gallery.json"):
            with self.subTest(filename=filename):
                timeline = json.loads(
                    (SKILL_ROOT / "references" / filename).read_text(encoding="utf-8")
                )
                declared = {
                    font["family"]: font
                    for font in timeline["fonts"]
                }
                body_family = timeline["defaultStyle"]["fontFamily"]
                brand_family = timeline["branding"]["style"]["fontFamily"]
                self.assertIn(body_family, declared)
                self.assertIn(brand_family, declared)
                for family in (body_family, brand_family):
                    font = declared[family]
                    self.assertTrue(font.get("path"))
                    self.assertTrue((SKILL_ROOT / font["path"]).is_file())

    def test_renderer_rejects_declared_custom_font_without_path(self) -> None:
        result = self.validate_timeline(
            {
                "fonts": [{"family": "FZLanTingHeiS-DB1-GB"}],
                "defaultStyle": {"fontFamily": "FZLanTingHeiS-DB1-GB"},
                "subtitles": [{"start": 0, "end": 1, "text": "测试"}],
            }
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("fonts[0].path is required", result.stdout + result.stderr)

    def test_renderer_rejects_undeclared_custom_font(self) -> None:
        result = self.validate_timeline(
            {
                "defaultStyle": {"fontFamily": "FZLanTingHeiS-DB1-GB"},
                "subtitles": [{"start": 0, "end": 1, "text": "测试"}],
            }
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("has no matching fonts[] entry", result.stdout + result.stderr)

    def test_renderer_allows_system_font_without_path(self) -> None:
        result = self.validate_timeline(
            {
                "defaultStyle": {"fontFamily": "Arial, sans-serif"},
                "subtitles": [{"start": 0, "end": 1, "text": "test"}],
            }
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)


if __name__ == "__main__":
    unittest.main()
