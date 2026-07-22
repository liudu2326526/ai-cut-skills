#!/usr/bin/env python3

from __future__ import annotations

import json
import unittest
from pathlib import Path


SKILL_ROOT = Path(__file__).resolve().parents[1]


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

    def test_description_gate_documents_model_and_program_boundaries(self) -> None:
        skill = (SKILL_ROOT / "SKILL.md").read_text(encoding="utf-8")

        self.assertIn("程序门禁只校验 description 非空", skill)
        self.assertIn("中文准确性和语义完整性由执行模型", skill)

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


if __name__ == "__main__":
    unittest.main()
