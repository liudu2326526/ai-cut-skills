from __future__ import annotations

import importlib.util
import json
import os
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace


SKILL_ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = SKILL_ROOT / "scripts" / "asset_manifest.py"


def load_module():
    spec = importlib.util.spec_from_file_location("visual_asset_manifest", MODULE_PATH)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Unable to load {MODULE_PATH}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class AssetManifestTests(unittest.TestCase):
    def setUp(self) -> None:
        self.module = load_module()

    def test_discovers_only_images_and_videos_without_inferred_categories(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            for name in ("screen.png", "clip.mp4", "music.mp3", "font.ttf", "notes.txt"):
                (root / name).write_bytes(name.encode("utf-8"))

            identities, errors = self.module.discover_files(root, checksum=False)

            self.assertEqual(errors, [])
            self.assertEqual(
                {item["relative_path"] for item in identities},
                {"screen.png", "clip.mp4"},
            )
            self.assertTrue(all("category" not in item for item in identities))

    def test_unchanged_assets_keep_understanding_and_modified_assets_clear_it(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = Path(temp_dir) / "workspace"
            assets = Path(temp_dir) / "assets"
            workspace.mkdir()
            assets.mkdir()
            image = assets / "screen.png"
            image.write_bytes(b"first")
            args = SimpleNamespace(
                workspace=workspace,
                asset_root=assets,
                manifest=None,
                quick=True,
                checksum=False,
                force=False,
            )

            created = self.module.sync_manifest(args)
            manifest_path = Path(created["manifest"])
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            manifest["assets"][0]["description"] = "一张测试图片。"
            manifest["assets"][0]["effective_region"] = {
                "x": 0,
                "y": 0,
                "width": 1,
                "height": 1,
                "coordinate_space": "source_pixels",
            }
            self.module.atomic_write_json(manifest_path, manifest)

            unchanged = self.module.sync_manifest(args)
            self.assertEqual(unchanged["status"], "unchanged")
            persisted = json.loads(manifest_path.read_text(encoding="utf-8"))
            self.assertEqual(persisted["assets"][0]["description"], "一张测试图片。")

            image.write_bytes(b"changed-content")
            os.utime(image, None)
            updated = self.module.sync_manifest(args)
            self.assertEqual(updated["status"], "updated")
            refreshed = json.loads(manifest_path.read_text(encoding="utf-8"))
            self.assertNotIn("description", refreshed["assets"][0])
            self.assertNotIn("effective_region", refreshed["assets"][0])
            self.assertNotIn("category", refreshed["assets"][0])

    def test_default_manifest_name_is_generic(self) -> None:
        self.assertEqual(self.module.DEFAULT_MANIFEST_NAME, "visual_assets_manifest.json")


if __name__ == "__main__":
    unittest.main()
