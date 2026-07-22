#!/usr/bin/env python3
"""Validate a visual asset manifest before Read-based semantic retrieval."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any


IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp", ".bmp", ".gif", ".tif", ".tiff", ".svg"}
VIDEO_EXTENSIONS = {".mp4", ".mov", ".m4v", ".mkv", ".webm", ".avi"}
VISUAL_EXTENSIONS = IMAGE_EXTENSIONS | VIDEO_EXTENSIONS


def discover_visual_paths(asset_root: Path) -> set[str]:
    return {
        path.relative_to(asset_root).as_posix()
        for path in asset_root.rglob("*")
        if path.is_file() and not path.is_symlink() and path.suffix.casefold() in VISUAL_EXTENSIONS
    }


def validate_region(record: dict[str, Any]) -> bool:
    region = record.get("effective_region")
    media = record.get("media") if isinstance(record.get("media"), dict) else {}
    if not isinstance(region, dict):
        return False
    try:
        x = float(region["x"])
        y = float(region["y"])
        width = float(region["width"])
        height = float(region["height"])
        source_width = float(media.get("width") or 0)
        source_height = float(media.get("height") or 0)
    except (KeyError, TypeError, ValueError):
        return False
    return not (
        str(region.get("coordinate_space", "source_pixels")) != "source_pixels"
        or source_width <= 0
        or source_height <= 0
        or x < 0
        or y < 0
        or width <= 0
        or height <= 0
        or x + width > source_width + 1
        or y + height > source_height + 1
    )


def has_valid_media_dimensions(record: dict[str, Any]) -> bool:
    media = record.get("media") if isinstance(record.get("media"), dict) else {}
    try:
        width = float(media.get("width") or 0)
        height = float(media.get("height") or 0)
    except (TypeError, ValueError):
        return False
    return media.get("probe_ok") is not False and width > 0 and height > 0


def validate_manifest(manifest_path: Path, asset_root: Path) -> dict[str, Any]:
    manifest_path = manifest_path.expanduser().resolve()
    asset_root = asset_root.expanduser().resolve()
    report: dict[str, Any] = {
        "ok": False,
        "status": "error",
        "manifest": str(manifest_path),
        "asset_root": str(asset_root),
        "visual_asset_count": 0,
        "missing_descriptions": [],
        "missing_effective_regions": [],
        "invalid_effective_regions": [],
        "invalid_media_metadata": [],
        "missing_visual_files": [],
        "untracked_visual_files": [],
        "duplicate_relative_paths": [],
        "errors": [],
    }
    if not asset_root.is_dir():
        report["errors"].append(f"Asset root directory not found: {asset_root}")
        return report
    if not manifest_path.is_file():
        report["errors"].append(f"Visual asset manifest not found: {manifest_path}")
        return report
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        report["errors"].append(f"Visual asset manifest is unreadable: {exc}")
        return report
    if not isinstance(manifest, dict):
        report["errors"].append("Visual asset manifest must be a JSON object")
        return report
    manifest_root = Path(str(manifest.get("asset_root", ""))).expanduser().resolve()
    if manifest_root != asset_root:
        report["errors"].append(
            f"Manifest asset_root does not match: {manifest_root} != {asset_root}"
        )
    assets = manifest.get("assets")
    if not isinstance(assets, list):
        report["errors"].append("Manifest assets must be an array")
        return report

    visual_records = [
        item
        for item in assets
        if isinstance(item, dict) and str(item.get("kind", "")).lower() in {"image", "video"}
    ]
    report["visual_asset_count"] = len(visual_records)
    seen: set[str] = set()
    duplicates: set[str] = set()
    tracked: set[str] = set()
    missing_descriptions: list[str] = []
    missing_regions: list[str] = []
    invalid_regions: list[str] = []
    invalid_media: list[str] = []
    missing_files: list[str] = []

    for record in visual_records:
        relative = str(record.get("relative_path", "")).strip()
        if not relative:
            report["errors"].append("Visual asset record is missing relative_path")
            continue
        if relative in seen:
            duplicates.add(relative)
        seen.add(relative)
        tracked.add(relative)
        path = asset_root / relative
        try:
            path.resolve().relative_to(asset_root)
        except ValueError:
            report["errors"].append(f"Visual asset path escapes asset_root: {relative}")
            continue
        if not path.is_file():
            missing_files.append(relative)
        if not str(record.get("description", "")).strip():
            missing_descriptions.append(relative)
        if not isinstance(record.get("effective_region"), dict):
            missing_regions.append(relative)
        elif not validate_region(record):
            invalid_regions.append(relative)
        if not has_valid_media_dimensions(record):
            invalid_media.append(relative)

    discovered = discover_visual_paths(asset_root)
    report["missing_descriptions"] = sorted(missing_descriptions)
    report["missing_effective_regions"] = sorted(missing_regions)
    report["invalid_effective_regions"] = sorted(invalid_regions)
    report["invalid_media_metadata"] = sorted(invalid_media)
    report["missing_visual_files"] = sorted(missing_files)
    report["untracked_visual_files"] = sorted(discovered - tracked)
    report["duplicate_relative_paths"] = sorted(duplicates)

    for key, message in (
        ("missing_descriptions", "Visual assets missing description"),
        ("missing_effective_regions", "Visual assets missing effective_region"),
        ("invalid_effective_regions", "Visual assets with invalid effective_region"),
        ("invalid_media_metadata", "Visual assets with invalid media dimensions"),
        ("missing_visual_files", "Manifest records whose files are missing"),
        ("untracked_visual_files", "Visual files not tracked by the manifest"),
        ("duplicate_relative_paths", "Duplicate manifest relative_path values"),
    ):
        if report[key]:
            report["errors"].append(f"{message}: " + ", ".join(report[key]))

    report["ok"] = not report["errors"]
    report["status"] = "complete" if report["ok"] else "needs_understanding"
    return report


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--asset-root", type=Path, required=True)
    parser.add_argument("--output-json", type=Path)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    report = validate_manifest(args.manifest, args.asset_root)
    content = json.dumps(report, ensure_ascii=False, indent=2) + "\n"
    if args.output_json:
        output = args.output_json.expanduser().resolve()
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(content, encoding="utf-8")
    print(content, end="")
    return 0 if report["ok"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
