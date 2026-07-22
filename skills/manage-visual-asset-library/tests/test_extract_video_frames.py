from __future__ import annotations

import importlib.util
import unittest
from pathlib import Path


SKILL_ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = SKILL_ROOT / "scripts" / "extract_video_frames.py"


def load_module():
    spec = importlib.util.spec_from_file_location("extract_visual_frames", MODULE_PATH)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Unable to load {MODULE_PATH}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class ExtractVideoFramesTests(unittest.TestCase):
    def setUp(self) -> None:
        self.module = load_module()

    def test_regular_video_uses_five_representative_points(self) -> None:
        self.assertEqual(
            self.module.representative_timestamps(20.0),
            [0.0, 5.0, 10.0, 15.0, 19.9],
        )

    def test_very_short_video_deduplicates_quantized_points(self) -> None:
        timestamps = self.module.representative_timestamps(0.002)
        self.assertEqual(timestamps, sorted(set(timestamps)))
        self.assertGreaterEqual(len(timestamps), 1)
        self.assertLess(len(timestamps), 5)


if __name__ == "__main__":
    unittest.main()
