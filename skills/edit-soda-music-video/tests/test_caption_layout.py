#!/usr/bin/env python3

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path


SKILL_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = SKILL_ROOT / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

import caption_layout  # noqa: E402
import soda_pipeline  # noqa: E402
import standalone_renderer  # noqa: E402


CAPTION_STYLE = {
    "font_size": 70,
    "scale_x": 100,
    "scale_y": 100,
    "spacing": 0,
    "outline": 3,
    "shadow": 0,
    "alignment": 2,
    "margin_left": 96,
    "margin_right": 96,
    "margin_vertical": 330,
    "position_mode": "center_offset",
    "x": 0,
    "y": -500,
    "wrap_mode": "balanced_explicit",
    "minimum_horizontal_margin": 96,
    "width_safety_ratio": 0.92,
    "preferred_max_lines": 2,
    "max_lines": 3,
}


class CaptionLayoutTests(unittest.TestCase):
    def test_long_chinese_caption_is_balanced_inside_safe_width(self) -> None:
        layout = caption_layout.layout_caption_text(
            "快点击视频下方链接下载汽水音乐体验吧",
            CAPTION_STYLE,
            1080,
        )

        self.assertEqual(
            layout["lines"],
            ["快点击视频下方链接", "下载汽水音乐体验吧"],
        )
        self.assertEqual(layout["line_count"], 2)
        self.assertTrue(all(width <= layout["available_width"] for width in layout["line_widths"]))

    def test_semantic_units_are_never_split(self) -> None:
        layout = caption_layout.layout_caption_text(
            "现在满 0.3 元即可提现快来汽水音乐体验",
            CAPTION_STYLE,
            1080,
        )
        joined = "\n".join(layout["lines"])

        self.assertNotIn("0.\n3", joined)
        self.assertNotIn("汽水\n音乐", joined)
        self.assertIn("0.3 元", joined)
        self.assertIn("汽水音乐", joined)

    def test_more_than_three_lines_is_rejected(self) -> None:
        with self.assertRaisesRegex(caption_layout.CaptionLayoutError, "more than 3 lines"):
            caption_layout.layout_caption_text("测" * 40, CAPTION_STYLE, 1080)

    def test_ass_generation_inserts_explicit_line_break_before_brand_styling(self) -> None:
        config = {"font": {"caption_style": CAPTION_STYLE}}
        style = standalone_renderer.resolve_caption_style(config, 1080, 1920)
        with tempfile.TemporaryDirectory() as temp:
            output = Path(temp) / "captions.ass"
            standalone_renderer.generate_ass(
                [
                    {
                        "start": 0.0,
                        "end": 2.0,
                        "text": "快点击视频下方链接下载汽水音乐体验吧",
                    }
                ],
                output,
                width=1080,
                height=1920,
                body_family="Body",
                brand_family="Soda Font",
                body_color="#FFFFFF",
                brand_color="#3BFD42",
                caption_style=style,
            )
            ass = output.read_text(encoding="utf-8-sig")

        self.assertIn(r"快点击视频下方链接\N", ass)
        self.assertIn(r"{\fnSoda Font", ass)

    def test_ass_generation_rejects_comma_separated_font_fallbacks(self) -> None:
        config = {"font": {"caption_style": CAPTION_STYLE}}
        style = standalone_renderer.resolve_caption_style(config, 1080, 1920)
        with tempfile.TemporaryDirectory() as temp:
            output = Path(temp) / "captions.ass"
            with self.assertRaisesRegex(
                standalone_renderer.RenderError,
                "font.body_family.*fallback list",
            ):
                standalone_renderer.generate_ass(
                    [{"start": 0.0, "end": 2.0, "text": "是不是好奇"}],
                    output,
                    width=1080,
                    height=1920,
                    body_family="FZLanTingHeiS-R-GB,方正兰亭黑简体",
                    brand_family="Soda Font",
                    body_color="#FFFFFF",
                    brand_color="#3BFD42",
                    caption_style=style,
                )

    def test_character_budget_is_derived_from_the_active_style(self) -> None:
        regular = caption_layout.derive_caption_character_budget(
            CAPTION_STYLE,
            1080,
        )
        smaller_style = {**CAPTION_STYLE, "font_size": 50}
        smaller = caption_layout.derive_caption_character_budget(
            smaller_style,
            1080,
        )

        self.assertEqual(regular["max_characters_per_line"], 11)
        self.assertGreater(
            smaller["max_characters_per_line"],
            regular["max_characters_per_line"],
        )
        self.assertEqual(regular["calculation"], "derived_once_from_caption_style")

    def test_whisper_alignment_preserves_model_semantic_lines(self) -> None:
        spoken = "快点击视频下方链接下载汽水音乐体验吧"
        semantic_script = "快点击视频下方链接\n下载汽水音乐体验吧"
        words = [
            {"start": index * 0.1, "end": (index + 1) * 0.1, "word": char}
            for index, char in enumerate(spoken)
        ]

        captions, report = soda_pipeline.align_script_to_whisper_words(
            semantic_script,
            words,
            3.0,
            caption_style=CAPTION_STYLE,
            canvas_width=1080,
        )

        self.assertEqual(
            [caption["text"] for caption in captions],
            ["快点击视频下方链接", "下载汽水音乐体验吧"],
        )
        self.assertEqual((captions[0]["start"], captions[0]["end"]), (0.0, 0.9))
        self.assertEqual((captions[1]["start"], captions[1]["end"]), (0.9, 1.8))
        self.assertEqual(report["caption_segmentation_source"], "executor_model_semantic_lines")
        self.assertEqual(report["semantic_segment_count"], 2)
        self.assertEqual(report["automatic_width_split_count"], 0)

    def test_over_budget_script_requires_semantic_line_breaks(self) -> None:
        spoken = "每次给爸妈转钱他们都不收"
        words = [
            {"start": index * 0.1, "end": (index + 1) * 0.1, "word": char}
            for index, char in enumerate(spoken)
        ]

        with self.assertRaisesRegex(
            soda_pipeline.PipelineError,
            "requires model semantic line breaks",
        ):
            soda_pipeline.align_script_to_whisper_words(
                spoken,
                words,
                3.0,
                caption_style=CAPTION_STYLE,
                canvas_width=1080,
            )

        captions, _report = soda_pipeline.align_script_to_whisper_words(
            "每次给爸妈转钱\n他们都不收",
            words,
            3.0,
            caption_style=CAPTION_STYLE,
            canvas_width=1080,
        )
        self.assertEqual(
            [caption["text"] for caption in captions],
            ["每次给爸妈转钱", "他们都不收"],
        )

    def test_preflight_layout_report_contains_line_widths(self) -> None:
        config = {
            "width": 1080,
            "height": 1920,
            "font": {"caption_style": CAPTION_STYLE},
            "captions": [
                {
                    "start": 0.0,
                    "end": 2.0,
                    "text": "快点击视频下方链接下载汽水音乐体验吧",
                }
            ],
        }

        report = soda_pipeline.build_caption_layout_report(config)

        self.assertTrue(report["ok"])
        self.assertEqual(report["captions"][0]["line_count"], 2)
        self.assertEqual(report["captions"][0]["lines"][0], "快点击视频下方链接")
        self.assertGreater(report["captions"][0]["available_width"], 0)
        self.assertEqual(
            report["caption_character_budget"]["max_characters_per_line"],
            11,
        )

    def test_punctuation_is_normalized_before_layout(self) -> None:
        normalized = standalone_renderer.normalize_subtitle_text(
            "快点击视频下方链接，下载汽水音乐体验吧！"
        )
        layout = caption_layout.layout_caption_text(normalized, CAPTION_STYLE, 1080)

        self.assertEqual(
            layout["lines"],
            ["快点击视频下方链接", "下载汽水音乐体验吧"],
        )


if __name__ == "__main__":
    unittest.main()
