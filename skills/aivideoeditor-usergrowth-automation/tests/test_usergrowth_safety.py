from __future__ import annotations

from dataclasses import replace
from pathlib import Path
import sys
import unittest


SKILL_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = SKILL_ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))

import usergrowth_upload  # noqa: E402
from usergrowth_automation.usergrowth_browser import card_defaults_for_item  # noqa: E402
from usergrowth_automation.usergrowth_models import UserGrowthVideoItem  # noqa: E402
from usergrowth_automation.usergrowth_planner import group_usergrowth_items  # noqa: E402


class UserGrowthSafetyTests(unittest.TestCase):
    def test_manifest_cannot_enable_live_mode(self) -> None:
        args = usergrowth_upload.parse_args([])
        manifest = {
            "video_folder": "videos",
            "backfill_excel": "backfill.xlsx",
            "song_excel": "songs.xlsx",
            "output_root": "outputs",
            "order_id": "order-1",
            "live": True,
            "confirm_live": True,
            "dry_run": False,
        }

        config = usergrowth_upload._config_from_args(args, manifest, Path("/tmp"))

        self.assertTrue(config.dry_run)

    def test_live_mode_requires_both_current_cli_flags(self) -> None:
        dry_args = usergrowth_upload.parse_args([])
        config = usergrowth_upload._config_from_args(
            dry_args,
            {
                "video_folder": "videos",
                "backfill_excel": "backfill.xlsx",
                "song_excel": "songs.xlsx",
                "output_root": "outputs",
                "order_id": "order-1",
            },
            Path("/tmp"),
        )
        live_config = replace(config, dry_run=False)

        with self.assertRaisesRegex(RuntimeError, "--live --confirm-live"):
            usergrowth_upload._validate_live_mode(
                usergrowth_upload.parse_args(["--live"]),
                live_config,
            )

        usergrowth_upload._validate_live_mode(
            usergrowth_upload.parse_args(["--live", "--confirm-live"]),
            live_config,
        )

    def test_grouping_splits_distinct_card_default_profiles(self) -> None:
        shared = {
            "path": Path("/tmp/a.mp4"),
            "file_name": "a.mp4",
            "material_type": "音乐",
            "song_name": "歌名",
            "order_id": "order-1",
        }
        first = UserGrowthVideoItem(
            **shared,
            classification_path=["音乐", "类型A"],
            custom_tags=["26年7月dxqs", "song-1"],
        )
        second = UserGrowthVideoItem(
            **{**shared, "path": Path("/tmp/b.mp4"), "file_name": "b.mp4"},
            classification_path=["音乐", "类型A"],
            custom_tags=["26年7月dxqs", "song-1"],
        )
        different = UserGrowthVideoItem(
            **{**shared, "path": Path("/tmp/c.mp4"), "file_name": "c.mp4"},
            classification_path=["音乐", "类型B"],
            custom_tags=["26年8月dxqs", "song-2"],
        )

        plans = group_usergrowth_items([first, second, different])

        self.assertEqual([len(plan.items) for plan in plans], [2, 1])
        self.assertEqual({plan.order_id for plan in plans}, {"order-1"})

    def test_card_defaults_use_planned_values_without_recomputation(self) -> None:
        item = UserGrowthVideoItem(
            path=Path("/tmp/not-rule-shaped-name.mp4"),
            file_name="not-rule-shaped-name.mp4",
            material_type="音乐",
            song_name="歌名",
            classification_path=["规划分类", "规划子类"],
            custom_tags=["自定义月份", "自定义歌曲ID"],
        )

        classification, tags = card_defaults_for_item(item)

        self.assertEqual(classification, ["LUNA功能卖点", "规划分类", "规划子类"])
        self.assertEqual(tags, ["自定义月份", "自定义歌曲ID"])
        self.assertIsNot(tags, item.custom_tags)


if __name__ == "__main__":
    unittest.main()
