from __future__ import annotations

import json
from pathlib import Path
import random
import shutil
import subprocess
import sys
import tempfile
import unittest


SKILL_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SKILL_ROOT / "scripts"))

import frame_variation  # noqa: E402


FFMPEG = shutil.which("ffmpeg")
FFPROBE = shutil.which("ffprobe")


@unittest.skipUnless(FFMPEG and FFPROBE, "ffmpeg and ffprobe are required")
class FrameVariationSyncTests(unittest.TestCase):
    def test_deleted_frame_selection_preserves_first_and_last_frames(self) -> None:
        for seed in range(20):
            deleted = frame_variation.choose_deleted_frames_per_second(
                30.0,
                90,
                2,
                random.Random(seed),
            )
            self.assertNotIn(0, deleted)
            self.assertNotIn(89, deleted)

    def test_cover_delay_keeps_audio_and_video_in_sync(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            source = root / "source.mp4"
            output = root / "variant.mp4"
            subprocess.run(
                [
                    str(FFMPEG),
                    "-y",
                    "-f",
                    "lavfi",
                    "-i",
                    "testsrc2=size=320x480:rate=30:duration=2",
                    "-f",
                    "lavfi",
                    "-i",
                    "sine=frequency=880:sample_rate=48000:duration=2",
                    "-c:v",
                    "libx264",
                    "-pix_fmt",
                    "yuv420p",
                    "-c:a",
                    "aac",
                    "-shortest",
                    str(source),
                ],
                check=True,
                capture_output=True,
            )

            frame_variation.render_frame_drop_variant_with_cover(
                source,
                output,
                [10, 35],
                0.5,
                0.4,
                320,
                480,
                "original",
                str(FFMPEG),
                has_audio=True,
            )

            probe = subprocess.run(
                [
                    str(FFPROBE),
                    "-v",
                    "error",
                    "-show_entries",
                    "stream=codec_type,duration",
                    "-show_entries",
                    "format=duration",
                    "-of",
                    "json",
                    str(output),
                ],
                check=True,
                capture_output=True,
                text=True,
            )
            payload = json.loads(probe.stdout)
            stream_durations = {
                stream["codec_type"]: float(stream["duration"])
                for stream in payload["streams"]
                if stream.get("duration")
            }
            video_duration = stream_durations["video"]
            audio_duration = stream_durations["audio"]

            self.assertLessEqual(abs(video_duration - audio_duration), 0.08)
            self.assertAlmostEqual(float(payload["format"]["duration"]), 2.4, delta=0.10)


if __name__ == "__main__":
    unittest.main()
