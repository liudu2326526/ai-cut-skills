#!/usr/bin/env python3

from __future__ import annotations

import json
import unittest
from pathlib import Path


SKILL_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = SKILL_ROOT.parents[1]


class SkillConsistencyTests(unittest.TestCase):
    def test_input_time_docs_do_not_require_removed_range_remapping(self) -> None:
        skill = (SKILL_ROOT / "SKILL.md").read_text(encoding="utf-8")
        pause = (SKILL_ROOT / "references" / "pause-removal.md").read_text(
            encoding="utf-8"
        )

        self.assertNotIn("按去气口范围与最终倍速重映射", skill)
        self.assertNotIn("按删除区间和倍速重映射字幕、物料、音效和提示音", pause)
        self.assertIn("time_mode=input", pause)

    def test_motion_template_defers_to_effect_catalog_defaults(self) -> None:
        template = json.loads(
            (SKILL_ROOT / "references" / "timeline-template.json").read_text(
                encoding="utf-8"
            )
        )
        policy = template["motion_effects"]

        self.assertNotIn("effect_duration", policy)
        self.assertNotIn("samples", policy)

    def test_icon_default_position_is_caption_relative(self) -> None:
        template = json.loads(
            (SKILL_ROOT / "references" / "timeline-template.json").read_text(
                encoding="utf-8"
            )
        )
        policy = template["visual_policy"]["icon_caption_placement"]
        renderer = (SKILL_ROOT / "scripts" / "standalone_renderer.py").read_text(
            encoding="utf-8"
        )
        docs = "\n".join(
            (SKILL_ROOT / path).read_text(encoding="utf-8")
            for path in (
                "SKILL.md",
                "references/brand-rules.md",
                "references/workflow.md",
                "references/standalone-runtime.md",
            )
        )

        self.assertEqual(policy["mode"], "above_caption")
        self.assertEqual(policy["gap"], 72)
        self.assertIn("caption_relative_default", renderer)
        self.assertIn("resolved_placement", renderer)
        self.assertNotIn('material.get("y", 720)', renderer)
        self.assertIn("显式 `y`", docs)
        self.assertNotIn("图标默认 `y=720`", docs)

    def test_visual_understanding_is_delegated_to_generic_skill(self) -> None:
        skill = (SKILL_ROOT / "SKILL.md").read_text(encoding="utf-8")

        self.assertIn(
            "**REQUIRED SUB-SKILL:** Use manage-visual-asset-library",
            skill,
        )
        self.assertIn("只消费 `visual_assets_manifest.json` 与 `asset_candidates.json`", skill)
        self.assertNotIn("asset-content-understanding.md", skill)
        self.assertNotIn("asset-manifest.md", skill)

    def test_asset_sync_is_forwarded_and_generic_manifest_is_default(self) -> None:
        pipeline = (SKILL_ROOT / "scripts" / "soda_pipeline.py").read_text(
            encoding="utf-8"
        )
        self.assertFalse((SKILL_ROOT / "scripts" / "asset_manifest.py").exists())
        self.assertIn('DEFAULT_ASSET_MANIFEST_NAME = "visual_assets_manifest.json"', pipeline)
        self.assertIn("resolve_visual_asset_library_script", pipeline)
        self.assertIn("VISUAL_ASSET_LIBRARY_SKILL_DIR", pipeline)
        self.assertIn("legacy soda_assets_manifest.json remains accepted", pipeline)
        self.assertNotIn("stores asset categories only", pipeline)
        self.assertLess(
            pipeline.index("SKILL_ROOT.parent / VISUAL_ASSET_LIBRARY_SKILL_NAME"),
            pipeline.index('codex_home / "skills" / VISUAL_ASSET_LIBRARY_SKILL_NAME'),
        )

    def test_motion_docs_use_effective_region_for_collision_not_general_cropping(self) -> None:
        paths = [
            SKILL_ROOT / "SKILL.md",
            SKILL_ROOT / "references" / "motion-effects.md",
            SKILL_ROOT / "references" / "standalone-runtime.md",
            SKILL_ROOT / "references" / "workflow.md",
            SKILL_ROOT / "references" / "asset-requirements.md",
        ]
        combined = "\n".join(path.read_text(encoding="utf-8") for path in paths)

        self.assertNotIn("动效也按有效内容裁切和检查", combined)
        self.assertNotIn("Remotion 使用 effective_region 裁切实际内容", combined)
        self.assertNotIn("Remotion 动效从源素材 effective_region 裁切实际内容", combined)
        self.assertNotIn("Remotion 动效按 effective_region 裁切实际内容", combined)
        self.assertIn("只有 icon 裁切 effective_region", combined)

    def test_unspecified_channel_and_bgm_are_selected_without_user_prompt(self) -> None:
        skill = (SKILL_ROOT / "SKILL.md").read_text(encoding="utf-8")
        workflow = (SKILL_ROOT / "references" / "workflow.md").read_text(
            encoding="utf-8"
        )
        runtime = (SKILL_ROOT / "references" / "standalone-runtime.md").read_text(
            encoding="utf-8"
        )
        agent_prompt = (SKILL_ROOT / "agents" / "openai.yaml").read_text(
            encoding="utf-8"
        )
        combined = "\n".join((skill, workflow, runtime, agent_prompt))

        self.assertIn("用户未指定渠道时，执行模型必须自行选择", combined)
        self.assertIn("用户未指定 BGM 时，执行模型必须自行选择", combined)
        self.assertIn("不向用户追问渠道或 BGM", combined)
        self.assertIn("CLI 仍显式传入模型选定的", combined)
        self.assertNotIn("如果渠道没有确认，不要直接渲染", combined)
        self.assertNotIn("Manifest 的音频", combined)
        self.assertNotIn("Manifest 中真实存在、可解码", combined)

    def test_decimal_amounts_are_not_split_or_stripped_from_captions(self) -> None:
        skill = (SKILL_ROOT / "SKILL.md").read_text(encoding="utf-8")
        special = (SKILL_ROOT / "references" / "special-material-matches.md").read_text(
            encoding="utf-8"
        )
        pipeline = (SKILL_ROOT / "scripts" / "soda_pipeline.py").read_text(
            encoding="utf-8"
        )
        renderer = (SKILL_ROOT / "scripts" / "standalone_renderer.py").read_text(
            encoding="utf-8"
        )

        self.assertIn("数字内部小数点", skill)
        self.assertIn("不得在小数点处分成两个 caption", special)
        self.assertIn("preserve_numeric_decimal_points", pipeline)
        self.assertIn("numeric decimal points preserved", renderer)

    def test_caption_wrap_contract_is_consistent(self) -> None:
        template = json.loads(
            (SKILL_ROOT / "references" / "timeline-template.json").read_text(
                encoding="utf-8"
            )
        )
        style = template["font"]["caption_style"]
        docs = "\n".join(
            (SKILL_ROOT / path).read_text(encoding="utf-8")
            for path in (
                "SKILL.md",
                "references/brand-rules.md",
                "references/workflow.md",
                "references/standalone-runtime.md",
                "agents/openai.yaml",
            )
        )

        self.assertEqual(style["wrap_mode"], "balanced_explicit")
        self.assertEqual(style["minimum_horizontal_margin"], 96)
        self.assertEqual(style["width_safety_ratio"], 0.92)
        self.assertEqual(style["preferred_max_lines"], 2)
        self.assertEqual(style["max_lines"], 3)
        self.assertTrue((SKILL_ROOT / "scripts" / "caption_layout.py").exists())
        self.assertIn("96px", docs)
        self.assertIn("0.92", docs)
        self.assertIn("最多三行", docs)
        self.assertIn("不得缩小字号", docs)
        self.assertNotIn("三行时参考字号 15", docs)

    def test_readme_documents_workbuddy_sync_from_canonical_repo(self) -> None:
        readme_path = REPO_ROOT / "README.md"
        if not readme_path.exists():
            self.skipTest("repository-level README is not installed with the Skill")
        readme = readme_path.read_text(encoding="utf-8")

        self.assertIn(".workbuddy", readme)
        self.assertIn("rsync", readme)
        self.assertIn("同一份仓库内容", readme)


if __name__ == "__main__":
    unittest.main()
