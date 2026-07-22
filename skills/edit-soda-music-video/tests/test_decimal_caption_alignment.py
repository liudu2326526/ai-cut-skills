#!/usr/bin/env python3

from __future__ import annotations

import sys
import unittest
from pathlib import Path


SKILL_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = SKILL_ROOT / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

import soda_pipeline  # noqa: E402
import standalone_renderer  # noqa: E402
from timeline_handoffs import validate_material_handoffs  # noqa: E402


class DecimalCaptionAlignmentTests(unittest.TestCase):
    def test_subtitle_normalization_preserves_numeric_decimal_points(self) -> None:
        source = "满 0.3 元即可提现，顶部余额 8．72 元，可选 0.30 元。"
        expected = "满 0.3 元即可提现 顶部余额 8.72 元 可选 0.30 元"

        self.assertEqual(soda_pipeline.normalize_subtitle_text(source), expected)
        self.assertEqual(standalone_renderer.normalize_subtitle_text(source), expected)

    def test_phrase_splitting_never_breaks_inside_decimal_amount(self) -> None:
        self.assertEqual(
            soda_pipeline.split_spoken_script_phrases(
                "满 0.3 元即可提现。\n顶部余额 8．72 元。"
            ),
            ["满 0.3 元即可提现", "顶部余额 8.72 元"],
        )

    def test_punctuation_does_not_override_model_semantic_lines(self) -> None:
        self.assertEqual(
            soda_pipeline.split_spoken_script_phrases(
                "每次给爸妈转钱，他们都不收"
            ),
            ["每次给爸妈转钱 他们都不收"],
        )

    def test_split_whisper_decimal_tokens_stay_in_one_caption(self) -> None:
        words = [
            {"start": 1.00, "end": 1.20, "word": "满"},
            {"start": 1.20, "end": 1.42, "word": "0"},
            {"start": 1.42, "end": 1.50, "word": "."},
            {"start": 1.50, "end": 1.72, "word": "3"},
            {"start": 1.72, "end": 1.92, "word": "元"},
            {"start": 1.92, "end": 2.18, "word": "即可"},
            {"start": 2.18, "end": 2.45, "word": "提现"},
        ]

        captions, _report = soda_pipeline.align_script_to_whisper_words(
            "满 0.3 元即可提现",
            words,
            3.0,
        )

        self.assertEqual(
            captions,
            [
                {
                    "start": 1.0,
                    "end": 2.45,
                    "text": "满 0.3 元即可提现",
                    "time_mode": "input",
                    "timing_source": "whisper_word_timestamps",
                }
            ],
        )

    def test_common_whisper_decimal_token_shapes_cover_full_benefit_span(self) -> None:
        token_variants = (
            [(1.20, 1.72, "0.3")],
            [(1.20, 1.42, "0"), (1.42, 1.50, "."), (1.50, 1.72, "3")],
            [(1.20, 1.50, "0."), (1.50, 1.72, "3")],
        )
        for amount_tokens in token_variants:
            with self.subTest(amount_tokens=amount_tokens):
                words = [
                    {"start": 1.00, "end": 1.20, "word": "满"},
                    *[
                        {"start": start, "end": end, "word": word}
                        for start, end, word in amount_tokens
                    ],
                    {"start": 1.72, "end": 1.92, "word": "元"},
                    {"start": 1.92, "end": 2.18, "word": "即可"},
                    {"start": 2.18, "end": 2.45, "word": "提现"},
                ]
                captions, _report = soda_pipeline.align_script_to_whisper_words(
                    "满 0.3 元即可提现",
                    words,
                    3.0,
                )
                self.assertEqual(len(captions), 1)
                caption = captions[0]
                self.assertEqual((caption["start"], caption["end"]), (1.0, 2.45))
                self.assertEqual(caption["text"], "满 0.3 元即可提现")

                timeline = {
                    "time_mode": "input",
                    "speed": 1.1,
                    "captions": captions,
                    "materials": [
                        {
                            "name": "满三毛提现页",
                            "time_mode": "input",
                            "sequence_id": "withdraw-benefit",
                            "start": caption["start"],
                            "end": caption["end"],
                        }
                    ],
                }
                report = validate_material_handoffs(timeline)
                self.assertTrue(report["ok"])
                self.assertTrue(report["caption_aligned"])


if __name__ == "__main__":
    unittest.main()
