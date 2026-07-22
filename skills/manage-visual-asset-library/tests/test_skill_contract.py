from __future__ import annotations

import json
import unittest
from pathlib import Path


SKILL_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = SKILL_ROOT.parents[1]
SODA_ROOT = REPO_ROOT / "skills" / "edit-soda-music-video"


class SkillContractTests(unittest.TestCase):
    def test_skill_requires_read_based_understanding_and_multiframe_video_review(self) -> None:
        skill = (SKILL_ROOT / "SKILL.md").read_text(encoding="utf-8")
        understanding = (SKILL_ROOT / "references" / "content-understanding.md").read_text(
            encoding="utf-8"
        )
        combined = skill + "\n" + understanding
        self.assertIn("Read", combined)
        self.assertIn("代表帧", combined)
        self.assertIn("description", combined)
        self.assertIn("effective_region", combined)
        self.assertIn("不能只看文件名", combined)

    def test_candidate_contract_has_reasons_but_no_final_selection_or_timeline(self) -> None:
        contract = (SKILL_ROOT / "references" / "semantic-matching.md").read_text(
            encoding="utf-8"
        )
        self.assertIn('"candidates"', contract)
        self.assertIn('"match_level"', contract)
        self.assertIn('"reason"', contract)
        self.assertIn("不选择最终素材", contract)
        self.assertIn("不修改调用方时间轴", contract)
        self.assertNotIn('"selected"', contract)
        self.assertNotIn('"start"', contract)
        self.assertNotIn('"end"', contract)

    def test_manifest_contract_omits_semantic_indexes_and_project_categories(self) -> None:
        contract = (SKILL_ROOT / "references" / "manifest-contract.md").read_text(
            encoding="utf-8"
        )
        self.assertIn("visual_assets_manifest.json", contract)
        self.assertIn("不根据文件名或目录名推断", contract)
        self.assertNotIn('"keywords"', contract)
        self.assertNotIn('"recommended_usage"', contract)
        self.assertNotIn('"category"', contract)

    def test_soda_depends_on_generic_skill_and_keeps_special_rules(self) -> None:
        soda_skill = (SODA_ROOT / "SKILL.md").read_text(encoding="utf-8")
        special = (SODA_ROOT / "references" / "special-material-matches.md").read_text(
            encoding="utf-8"
        )
        self.assertIn(
            "**REQUIRED SUB-SKILL:** Use manage-visual-asset-library",
            soda_skill,
        )
        self.assertIn("withdraw_0_3", special)
        self.assertIn("特殊素材匹配", special)


if __name__ == "__main__":
    unittest.main()
