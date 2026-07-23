from __future__ import annotations

import importlib.util
import sys
import unittest
from pathlib import Path


SKILL_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = Path(__file__).resolve().parents[3]
SCRIPTS_DIR = SKILL_ROOT / "scripts"

sys.path.insert(0, str(SCRIPTS_DIR))
spec = importlib.util.spec_from_file_location(
    "run_pre_roll_standalone",
    SCRIPTS_DIR / "run_pre_roll_standalone.py",
)
assert spec and spec.loader
runner = importlib.util.module_from_spec(spec)
spec.loader.exec_module(runner)


class BundledAssetRemovalTests(unittest.TestCase):
    def test_readme_uses_canonical_repository(self) -> None:
        readme = (REPO_ROOT / "README.md").read_text(encoding="utf-8")
        self.assertIn(
            "git clone git@github.com:liudu2326526/ai-cut-skills.git",
            readme,
        )
        self.assertNotIn("git@github.com:014-code/ai-cut-skills.git", readme)

    def test_runner_no_longer_exposes_bundled_asset_options(self) -> None:
        parser = runner.build_parser()
        option_strings = {
            option
            for action in parser._actions
            for option in action.option_strings
        }
        self.assertNotIn("--use-bundled-assets", option_strings)
        self.assertNotIn("--no-bundled-assets", option_strings)
        self.assertFalse(hasattr(parser.parse_args([]), "use_bundled_assets"))

    def test_skill_has_no_stale_bundled_material_contract(self) -> None:
        paths = [
            SKILL_ROOT / "SKILL.md",
            SKILL_ROOT / "references" / "asset-requirements.md",
            SKILL_ROOT / "references" / "troubleshooting.md",
            SCRIPTS_DIR / "run_pre_roll_standalone.py",
        ]
        content = "\n".join(path.read_text(encoding="utf-8") for path in paths)
        for stale_value in (
            "BUNDLED_MATERIAL_ROOT",
            "useBundledAssets",
            "use_bundled_assets",
            "--use-bundled-assets",
            "--no-bundled-assets",
            "bundledMaterialRoot",
            "汽水物料-新",
        ):
            with self.subTest(stale_value=stale_value):
                self.assertNotIn(stale_value, content)

    def test_production_render_requires_explicit_font_files(self) -> None:
        with self.assertRaisesRegex(
            runner.RunnerError,
            "requires valid --body-font-path and --brand-font-path",
        ):
            runner.validate_font_path_requirements(
                body_font_path=None,
                brand_font_path=None,
                enforce=True,
            )

        dry_run_report = runner.validate_font_path_requirements(
            body_font_path=None,
            brand_font_path=None,
            enforce=False,
        )
        self.assertFalse(dry_run_report["ok"])
        self.assertEqual(
            dry_run_report["missing"],
            ["bodyFontPath", "brandFontPath"],
        )

    def test_verified_shared_font_paths_satisfy_render_contract(self) -> None:
        font_root = REPO_ROOT / "skills" / "subtitle-motion-effects" / "assets" / "fonts"
        report = runner.validate_font_path_requirements(
            body_font_path=font_root / "FZLanTingHei-Medium.ttf",
            brand_font_path=font_root / "SodaFont-Regular.otf",
            enforce=True,
        )
        self.assertTrue(report["ok"])


if __name__ == "__main__":
    unittest.main()
