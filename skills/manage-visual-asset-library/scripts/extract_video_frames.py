#!/usr/bin/env python3
"""Export deterministic representative frames from one video for model Read review."""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from pathlib import Path


class FrameExtractionError(RuntimeError):
    pass


def require_binary(name: str) -> str:
    value = shutil.which(name)
    if not value:
        raise FrameExtractionError(f"Required binary not found: {name}")
    return value


def probe_duration(path: Path) -> float:
    ffprobe = require_binary("ffprobe")
    result = subprocess.run(
        [
            ffprobe,
            "-v",
            "error",
            "-show_entries",
            "format=duration",
            "-of",
            "default=noprint_wrappers=1:nokey=1",
            str(path),
        ],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    if result.returncode != 0:
        raise FrameExtractionError(
            f"Unable to probe video duration for {path}: {(result.stderr or 'ffprobe failed').strip()}"
        )
    try:
        duration = float(result.stdout.strip())
    except ValueError as exc:
        raise FrameExtractionError(f"Invalid video duration for {path}: {result.stdout!r}") from exc
    if duration <= 0:
        raise FrameExtractionError(f"Video duration must be positive: {path}")
    return duration


def representative_timestamps(duration: float) -> list[float]:
    if duration <= 0:
        raise ValueError("duration must be positive")
    # Stay before the container duration because the final encoded frame often
    # ends one frame earlier than format.duration.  Cap the inset at 100 ms so
    # long videos still sample close to their end.
    near_end = max(0.0, duration - min(0.1, duration * 0.05))
    raw = (0.0, duration * 0.25, duration * 0.5, duration * 0.75, near_end)
    result: list[float] = []
    seen_milliseconds: set[int] = set()
    for value in raw:
        milliseconds = max(0, int(value * 1000))
        if milliseconds in seen_milliseconds:
            continue
        seen_milliseconds.add(milliseconds)
        result.append(round(milliseconds / 1000, 3))
    return result


def extract_frames(input_path: Path, output_dir: Path) -> dict:
    input_path = input_path.expanduser().resolve()
    output_dir = output_dir.expanduser().resolve()
    if not input_path.is_file():
        raise FrameExtractionError(f"Video file not found: {input_path}")
    ffmpeg = require_binary("ffmpeg")
    duration = probe_duration(input_path)
    timestamps = representative_timestamps(duration)
    output_dir.mkdir(parents=True, exist_ok=True)
    frames: list[dict[str, object]] = []
    for index, timestamp in enumerate(timestamps, start=1):
        output = output_dir / f"frame_{index:02d}_{int(round(timestamp * 1000)):08d}ms.png"
        result = subprocess.run(
            [
                ffmpeg,
                "-hide_banner",
                "-loglevel",
                "error",
                "-ss",
                f"{timestamp:.3f}",
                "-i",
                str(input_path),
                "-frames:v",
                "1",
                "-y",
                str(output),
            ],
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )
        if result.returncode != 0 or not output.is_file():
            raise FrameExtractionError(
                f"Unable to extract representative frame at {timestamp:.3f}s from {input_path}: "
                + (result.stderr or "ffmpeg failed").strip()
            )
        frames.append({"timestamp": timestamp, "path": str(output)})
    return {
        "ok": True,
        "input": str(input_path),
        "duration_seconds": round(duration, 3),
        "frames": frames,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--output-json", type=Path)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        report = extract_frames(args.input, args.output_dir)
        content = json.dumps(report, ensure_ascii=False, indent=2) + "\n"
        if args.output_json:
            output = args.output_json.expanduser().resolve()
            output.parent.mkdir(parents=True, exist_ok=True)
            output.write_text(content, encoding="utf-8")
        print(content, end="")
        return 0
    except (FrameExtractionError, OSError, ValueError) as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False, indent=2), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
