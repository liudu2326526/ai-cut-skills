from __future__ import annotations

import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = REPO_ROOT / "scripts" / "sync_skills.py"
SPEC = importlib.util.spec_from_file_location("sync_skills", MODULE_PATH)
assert SPEC and SPEC.loader
sync_skills = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = sync_skills
SPEC.loader.exec_module(sync_skills)


class CatalogTests(unittest.TestCase):
    def test_repository_catalog_matches_skill_directories(self) -> None:
        catalog = sync_skills.load_catalog(REPO_ROOT / "skill-catalog.yaml")
        sync_skills.validate_catalog(catalog, REPO_ROOT / "skills")
        self.assertEqual(len(catalog["categories"]), 7)
        self.assertEqual(len(catalog["skills"]), 16)

    def test_optional_routing_metadata_is_validated(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            skills_dir = Path(temporary_directory) / "skills"
            (skills_dir / "example").mkdir(parents=True)
            (skills_dir / "example" / "SKILL.md").write_text("---\nname: example\n---\n", encoding="utf-8")
            catalog = {
                "schema_version": 1,
                "categories": {"test": {"label": "Test"}},
                "sync": {"exclude_names": [], "exclude_suffixes": []},
                "skills": {
                    "example": {
                        "category": "test",
                        "summary": "Example",
                        "capability_path": ["Video", "Edit"],
                        "tags": ["字幕"],
                        "when_to_use": ["需要生成字幕动效"],
                        "when_not_use": ["只需要字幕文本"],
                        "inputs": ["subtitle_json"],
                        "outputs": ["mp4"],
                        "quality": {"confidence": 0.9, "success_rate": 0.8},
                        "requires": [],
                        "optional": [],
                        "next_stage": [],
                    }
                },
            }
            sync_skills.validate_catalog(catalog, skills_dir)

    def test_readme_names_every_catalogued_skill(self) -> None:
        catalog = sync_skills.load_catalog(REPO_ROOT / "skill-catalog.yaml")
        readme = (REPO_ROOT / "README.md").read_text(encoding="utf-8")
        missing = [skill_name for skill_name in catalog["skills"] if f"`{skill_name}`" not in readme]
        self.assertEqual(missing, [])

    def test_selection_uses_category_and_skill_intersection_with_required_dependencies(self) -> None:
        catalog = sync_skills.load_catalog(REPO_ROOT / "skill-catalog.yaml")
        selected = sync_skills.choose_skills(
            catalog,
            ["edit-soda-music-video", "video-motion-effects"],
            ["production"],
        )
        self.assertEqual(
            selected,
            [
                "setup-video-editing-environment",
                "manage-visual-asset-library",
                "edit-soda-music-video",
            ],
        )

    def test_mogong_selection_includes_douyin_toolkit(self) -> None:
        catalog = sync_skills.load_catalog(REPO_ROOT / "skill-catalog.yaml")
        selected = sync_skills.choose_skills(catalog, ["mogong-gid-retrieval"], [])
        self.assertEqual(selected, ["douyin-video-toolkit", "mogong-gid-retrieval"])

    def test_unknown_catalog_dependency_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            skills_dir = Path(temporary_directory) / "skills"
            (skills_dir / "example").mkdir(parents=True)
            (skills_dir / "example" / "SKILL.md").write_text("---\\nname: example\\n---\\n", encoding="utf-8")
            catalog = {
                "schema_version": 1,
                "categories": {"test": {"label": "Test"}},
                "sync": {"exclude_names": [], "exclude_suffixes": []},
                "skills": {
                    "example": {
                        "category": "test",
                        "summary": "Example",
                        "requires": ["missing"],
                        "optional": [],
                        "next_stage": [],
                    }
                },
            }
            with self.assertRaises(sync_skills.CatalogError):
                sync_skills.validate_catalog(catalog, skills_dir)

    def test_route_prefers_subtitle_motion_for_effect_intent(self) -> None:
        catalog = sync_skills.load_catalog(REPO_ROOT / "skill-catalog.yaml")
        candidates = sync_skills.route_skills(catalog, "做一个类似剪映字幕", top=3)
        self.assertGreaterEqual(len(candidates), 1)
        self.assertEqual(candidates[0].skill_name, "subtitle-motion-effects")

    def test_route_prefers_mogong_for_gid_query(self) -> None:
        catalog = sync_skills.load_catalog(REPO_ROOT / "skill-catalog.yaml")
        candidates = sync_skills.route_skills(catalog, "查询魔工 gid 并导出 excel", top=3)
        self.assertGreaterEqual(len(candidates), 1)
        self.assertEqual(candidates[0].skill_name, "mogong-gid-retrieval")

    def test_route_avoids_generic_video_only_matches(self) -> None:
        catalog = sync_skills.load_catalog(REPO_ROOT / "skill-catalog.yaml")
        candidates = sync_skills.route_skills(catalog, "抖音视频下载", top=3)
        self.assertEqual([candidate.skill_name for candidate in candidates], ["douyin-video-toolkit"])

    def test_route_prefers_adxray_for_hot_playlet_download(self) -> None:
        catalog = sync_skills.load_catalog(REPO_ROOT / "skill-catalog.yaml")
        candidates = sync_skills.route_skills(catalog, "下载 AdXRay 抖音热播短剧素材", top=3)
        self.assertGreaterEqual(len(candidates), 1)
        self.assertEqual(candidates[0].skill_name, "adxray-playlet-crawler")

    def test_route_prefers_visual_moderation_for_review_intent(self) -> None:
        catalog = sync_skills.load_catalog(REPO_ROOT / "skill-catalog.yaml")
        candidates = sync_skills.route_skills(catalog, "审核短剧视频里的证件和 NSFW 风险", top=3)
        self.assertGreaterEqual(len(candidates), 1)
        self.assertEqual(candidates[0].skill_name, "aivideoeditor-visual-moderation")

    def test_route_includes_download_review_and_packaging_for_full_flow(self) -> None:
        catalog = sync_skills.load_catalog(REPO_ROOT / "skill-catalog.yaml")
        candidates = sync_skills.route_skills(catalog, "跑一个短剧从下载审核到包装的全流程", top=5)
        self.assertEqual(
            {candidate.skill_name for candidate in candidates},
            {
                "adxray-playlet-crawler",
                "aivideoeditor-visual-moderation",
                "edit-short-drama-packaging",
            },
        )

    def test_route_when_not_use_demotes_neighboring_skill(self) -> None:
        catalog = {
            "categories": {"render": {"label": "渲染", "description": "字幕能力"}},
            "skills": {
                "subtitle-motion": {
                    "category": "render",
                    "summary": "生成字幕动效",
                    "capability_path": ["Video", "Edit", "Subtitle"],
                    "tags": ["字幕", "字幕动效"],
                    "when_to_use": ["需要生成字幕动效"],
                    "when_not_use": ["只需要字幕文本提取"],
                },
                "subtitle-extract": {
                    "category": "render",
                    "summary": "提取字幕文本",
                    "capability_path": ["Video", "Analyze", "SubtitleExtract"],
                    "tags": ["字幕", "提取", "字幕文本"],
                    "when_to_use": ["只需要字幕文本提取"],
                    "when_not_use": ["需要生成字幕动效"],
                },
            },
        }
        candidates = sync_skills.route_skills(catalog, "只需要字幕文本提取", top=2)
        self.assertEqual(candidates[0].skill_name, "subtitle-extract")
        self.assertNotIn("subtitle-motion", [candidate.skill_name for candidate in candidates])


class SyncTreeTests(unittest.TestCase):
    def setUp(self) -> None:
        self.excluded_names = {"node_modules", "__pycache__", ".DS_Store"}
        self.excluded_suffixes = (".pyc", ".pyo")

    def test_sync_copies_source_deletes_stale_and_preserves_excluded_runtime_files(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            temporary_root = Path(temporary_directory)
            source = temporary_root / "source"
            destination = temporary_root / "destination"
            (source / "scripts" / "remotion").mkdir(parents=True)
            (source / "SKILL.md").write_text("new skill", encoding="utf-8")
            (source / "scripts" / "main.py").write_text("print('new')", encoding="utf-8")
            (source / "__pycache__").mkdir()
            (source / "__pycache__" / "ignored.pyc").write_bytes(b"ignored")

            (destination / "scripts" / "remotion" / "node_modules").mkdir(parents=True)
            (destination / "scripts" / "remotion" / "node_modules" / "installed.js").write_text(
                "keep",
                encoding="utf-8",
            )
            (destination / "stale.txt").write_text("delete", encoding="utf-8")

            stats = sync_skills.sync_tree(
                source,
                destination,
                excluded_names=self.excluded_names,
                excluded_suffixes=self.excluded_suffixes,
                delete=True,
                dry_run=False,
            )

            self.assertEqual((destination / "SKILL.md").read_text(encoding="utf-8"), "new skill")
            self.assertTrue((destination / "scripts" / "main.py").is_file())
            self.assertFalse((destination / "stale.txt").exists())
            self.assertFalse((destination / "__pycache__").exists())
            self.assertTrue(
                (destination / "scripts" / "remotion" / "node_modules" / "installed.js").is_file()
            )
            self.assertEqual(stats.copied, 2)
            self.assertGreaterEqual(stats.deleted, 1)

    def test_dry_run_does_not_modify_destination(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            temporary_root = Path(temporary_directory)
            source = temporary_root / "source"
            destination = temporary_root / "destination"
            source.mkdir()
            destination.mkdir()
            (source / "SKILL.md").write_text("new", encoding="utf-8")
            stale = destination / "stale.txt"
            stale.write_text("keep during dry run", encoding="utf-8")

            stats = sync_skills.sync_tree(
                source,
                destination,
                excluded_names=self.excluded_names,
                excluded_suffixes=self.excluded_suffixes,
                delete=True,
                dry_run=True,
            )

            self.assertTrue(stale.is_file())
            self.assertFalse((destination / "SKILL.md").exists())
            self.assertEqual(stats.copied, 1)
            self.assertEqual(stats.deleted, 1)

    def test_catalog_is_json_compatible_yaml(self) -> None:
        content = (REPO_ROOT / "skill-catalog.yaml").read_text(encoding="utf-8")
        parsed = json.loads(content)
        self.assertEqual(parsed["schema_version"], 1)


if __name__ == "__main__":
    unittest.main()
