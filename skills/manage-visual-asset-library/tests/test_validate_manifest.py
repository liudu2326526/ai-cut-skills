from __future__ import annotations

import importlib.util
import json
import tempfile
import unittest
from pathlib import Path


SKILL_ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = SKILL_ROOT / "scripts" / "validate_manifest.py"


def load_module():
    spec = importlib.util.spec_from_file_location("validate_visual_manifest", MODULE_PATH)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Unable to load {MODULE_PATH}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class ValidateManifestTests(unittest.TestCase):
    def setUp(self) -> None:
        self.module = load_module()

    def write_manifest(self, root: Path, record: dict) -> Path:
        manifest_path = root.parent / "visual_assets_manifest.json"
        manifest_path.write_text(
            json.dumps(
                {
                    "schema_version": 1,
                    "asset_root": str(root.resolve()),
                    "assets": [record],
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        return manifest_path

    def valid_record(self) -> dict:
        return {
            "relative_path": "screen.png",
            "kind": "image",
            "media": {"probe_ok": True, "width": 100, "height": 200},
            "description": "完整的手机设置页面，显示两个可选按钮。",
            "effective_region": {
                "x": 10,
                "y": 20,
                "width": 80,
                "height": 160,
                "coordinate_space": "source_pixels",
            },
        }

    def test_accepts_complete_visual_manifest_and_ignores_legacy_audio_records(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir) / "assets"
            root.mkdir()
            (root / "screen.png").write_bytes(b"image")
            record = self.valid_record()
            manifest_path = self.write_manifest(root, record)
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            manifest["assets"].append(
                {"relative_path": "music.mp3", "kind": "audio", "category": "background_music"}
            )
            manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

            report = self.module.validate_manifest(manifest_path, root)

            self.assertTrue(report["ok"], report)
            self.assertEqual(report["visual_asset_count"], 1)

    def test_rejects_missing_description_and_out_of_bounds_region(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir) / "assets"
            root.mkdir()
            (root / "screen.png").write_bytes(b"image")
            record = self.valid_record()
            record["description"] = ""
            record["effective_region"]["width"] = 200
            manifest_path = self.write_manifest(root, record)

            report = self.module.validate_manifest(manifest_path, root)

            self.assertFalse(report["ok"])
            self.assertEqual(report["missing_descriptions"], ["screen.png"])
            self.assertEqual(report["invalid_effective_regions"], ["screen.png"])

    def test_rejects_untracked_visual_files(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir) / "assets"
            root.mkdir()
            (root / "screen.png").write_bytes(b"image")
            (root / "extra.mp4").write_bytes(b"video")
            manifest_path = self.write_manifest(root, self.valid_record())

            report = self.module.validate_manifest(manifest_path, root)

            self.assertFalse(report["ok"])
            self.assertEqual(report["untracked_visual_files"], ["extra.mp4"])

    def test_rejects_non_numeric_media_dimensions_without_crashing(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir) / "assets"
            root.mkdir()
            (root / "screen.png").write_bytes(b"image")
            record = self.valid_record()
            record["media"]["width"] = "wide"
            manifest_path = self.write_manifest(root, record)

            report = self.module.validate_manifest(manifest_path, root)

            self.assertFalse(report["ok"])
            self.assertEqual(report["invalid_media_metadata"], ["screen.png"])


if __name__ == "__main__":
    unittest.main()
