#!/usr/bin/env python3
"""Synchronize image and video metadata into a workspace visual asset manifest."""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import subprocess
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


SCHEMA_VERSION = 1
DEFAULT_MANIFEST_NAME = "visual_assets_manifest.json"

VIDEO_EXTENSIONS = {".mp4", ".mov", ".m4v", ".mkv", ".webm", ".avi"}
IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp", ".bmp", ".gif", ".tif", ".tiff", ".svg"}
SUPPORTED_EXTENSIONS = VIDEO_EXTENSIONS | IMAGE_EXTENSIONS


class ManifestError(RuntimeError):
    pass


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def resolve_workspace_path(workspace: Path, value: Path | None) -> Path:
    if value is None:
        return workspace / DEFAULT_MANIFEST_NAME
    expanded = value.expanduser()
    return expanded.resolve() if expanded.is_absolute() else (workspace / expanded).resolve()


def ensure_inside_workspace(workspace: Path, path: Path) -> None:
    try:
        path.relative_to(workspace)
    except ValueError as exc:
        raise ManifestError(f"Manifest must be inside workspace: {workspace}") from exc


def file_kind(extension: str) -> str:
    if extension in VIDEO_EXTENSIONS:
        return "video"
    if extension in IMAGE_EXTENSIONS:
        return "image"
    return "unknown"


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def parse_fraction(value: str | None) -> float | None:
    if not value or value == "0/0":
        return None
    if "/" in value:
        numerator, denominator = value.split("/", 1)
        denominator_value = float(denominator)
        return float(numerator) / denominator_value if denominator_value else None
    return float(value)


def probe_media(path: Path) -> dict[str, Any]:
    ffprobe = shutil.which("ffprobe")
    if not ffprobe:
        return {"probe_ok": False, "probe_error": "ffprobe not found"}
    result = subprocess.run(
        [
            ffprobe,
            "-v",
            "error",
            "-show_entries",
            "format=duration,format_name,bit_rate:stream=codec_type,codec_name,width,height,avg_frame_rate,r_frame_rate",
            "-of",
            "json",
            str(path),
        ],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    if result.returncode != 0:
        return {
            "probe_ok": False,
            "probe_error": (result.stderr or "ffprobe failed").strip(),
        }
    data = json.loads(result.stdout or "{}")
    format_data = data.get("format", {})
    video = next(
        (stream for stream in data.get("streams", []) if stream.get("codec_type") == "video"),
        {},
    )
    duration = format_data.get("duration")
    bit_rate = format_data.get("bit_rate")
    return {
        "probe_ok": bool(video),
        "duration_seconds": round(float(duration), 3) if duration else None,
        "format_name": format_data.get("format_name"),
        "bit_rate": int(bit_rate) if bit_rate else None,
        "video_codec": video.get("codec_name"),
        "width": video.get("width"),
        "height": video.get("height"),
        "fps": parse_fraction(video.get("avg_frame_rate") or video.get("r_frame_rate")),
    }


def discover_files(asset_root: Path, checksum: bool) -> tuple[list[dict[str, Any]], list[str]]:
    identities: list[dict[str, Any]] = []
    errors: list[str] = []
    for path in sorted(asset_root.rglob("*"), key=lambda item: item.as_posix().casefold()):
        try:
            if path.is_symlink() or not path.is_file():
                continue
            extension = path.suffix.casefold()
            if extension not in SUPPORTED_EXTENSIONS:
                continue
            stat = path.stat()
            identity: dict[str, Any] = {
                "relative_path": path.relative_to(asset_root).as_posix(),
                "extension": extension,
                "kind": file_kind(extension),
                "size_bytes": stat.st_size,
                "mtime_ns": stat.st_mtime_ns,
            }
            if checksum:
                identity["sha256"] = sha256_file(path)
            identities.append(identity)
        except (OSError, ValueError) as exc:
            errors.append(f"{path}: {exc}")
    return identities, errors


def fingerprint(identities: list[dict[str, Any]], checksum: bool) -> str:
    fields = ("relative_path", "extension", "kind", "size_bytes", "mtime_ns")
    records = [
        {
            **{field: item[field] for field in fields},
            **({"sha256": item.get("sha256")} if checksum else {}),
        }
        for item in identities
    ]
    payload = json.dumps(records, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def load_existing(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return value if isinstance(value, dict) else None


def identity_matches(current: dict[str, Any], previous: dict[str, Any], checksum: bool) -> bool:
    fields = ("relative_path", "extension", "kind", "size_bytes", "mtime_ns")
    if any(current.get(field) != previous.get(field) for field in fields):
        return False
    return not checksum or current.get("sha256") == previous.get("sha256")


def build_asset_record(
    identity: dict[str, Any],
    asset_root: Path,
    previous: dict[str, Any] | None,
    *,
    quick: bool,
    checksum: bool,
) -> tuple[dict[str, Any], bool]:
    if previous and identity_matches(identity, previous, checksum):
        record = dict(previous)
        record.pop("category", None)
        record.pop("category_source", None)
        if not checksum:
            record.pop("sha256", None)
        record.update(identity)
        return record, True

    record = dict(identity)
    record["file_name"] = Path(identity["relative_path"]).name
    if not quick:
        record["media"] = probe_media(asset_root / identity["relative_path"])
    return record, False


def summarize(assets: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "total": len(assets),
        "total_size_bytes": sum(int(item.get("size_bytes") or 0) for item in assets),
        "by_kind": dict(sorted(Counter(item["kind"] for item in assets).items())),
    }


def atomic_write_json(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = path.with_name(path.name + ".tmp")
    temp_path.write_text(
        json.dumps(data, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    temp_path.replace(path)


def sync_manifest(args: argparse.Namespace) -> dict[str, Any]:
    workspace = args.workspace.expanduser().resolve()
    asset_root = args.asset_root.expanduser().resolve()
    if not workspace.is_dir():
        raise ManifestError(f"Workspace directory not found: {workspace}")
    if not asset_root.is_dir():
        raise ManifestError(f"Asset root directory not found: {asset_root}")

    manifest_path = resolve_workspace_path(workspace, args.manifest)
    ensure_inside_workspace(workspace, manifest_path)
    identities, scan_errors = discover_files(asset_root, args.checksum)
    current_fingerprint = fingerprint(identities, args.checksum)
    existing = load_existing(manifest_path)
    fingerprint_mode = "sha256" if args.checksum else "path-size-mtime"
    metadata_mode = "quick" if args.quick else "ffprobe"

    compatible_existing = bool(
        existing
        and existing.get("schema_version") == SCHEMA_VERSION
        and existing.get("asset_root") == str(asset_root)
        and existing.get("fingerprint_mode") == fingerprint_mode
        and existing.get("metadata_mode") == metadata_mode
    )
    if compatible_existing and not args.force and existing.get("fingerprint") == current_fingerprint:
        return {
            "ok": True,
            "status": "unchanged",
            "manifest": str(manifest_path),
            "asset_root": str(asset_root),
            "fingerprint": current_fingerprint,
            "summary": existing.get("summary", {}),
            "file_rewritten": False,
        }

    previous_assets = {
        item.get("relative_path"): item
        for item in (existing or {}).get("assets", [])
        if isinstance(item, dict)
        and item.get("relative_path")
        and str(item.get("kind", "")).lower() in {"image", "video"}
    }
    current_paths = {item["relative_path"] for item in identities}
    previous_paths = set(previous_assets)
    added = sorted(current_paths - previous_paths)
    removed = sorted(previous_paths - current_paths)
    modified: list[str] = []
    assets: list[dict[str, Any]] = []
    reused_count = 0

    for identity in identities:
        previous = previous_assets.get(identity["relative_path"])
        record, reused = build_asset_record(
            identity,
            asset_root,
            previous if compatible_existing else None,
            quick=args.quick,
            checksum=args.checksum,
        )
        assets.append(record)
        reused_count += int(reused)
        if previous and not identity_matches(identity, previous, args.checksum):
            modified.append(identity["relative_path"])

    status = "created" if existing is None else "updated"
    manifest = {
        "schema_version": SCHEMA_VERSION,
        "generated_at": utc_now(),
        "workspace": str(workspace),
        "asset_root": str(asset_root),
        "fingerprint_mode": fingerprint_mode,
        "metadata_mode": metadata_mode,
        "fingerprint": current_fingerprint,
        "summary": summarize(assets),
        "changes": {
            "status": status,
            "added": added,
            "removed": removed,
            "modified": sorted(modified),
            "reused_metadata_count": reused_count,
        },
        "scan_errors": scan_errors,
        "assets": assets,
    }
    atomic_write_json(manifest_path, manifest)
    return {
        "ok": not scan_errors,
        "status": status,
        "manifest": str(manifest_path),
        "asset_root": str(asset_root),
        "fingerprint": current_fingerprint,
        "summary": manifest["summary"],
        "changes": manifest["changes"],
        "scan_errors": scan_errors,
        "file_rewritten": True,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workspace", type=Path, required=True)
    parser.add_argument("--asset-root", type=Path, required=True)
    parser.add_argument(
        "--manifest",
        type=Path,
        help=f"Workspace-relative or absolute manifest path; default: <workspace>/{DEFAULT_MANIFEST_NAME}",
    )
    parser.add_argument("--quick", action="store_true", help="Skip ffprobe metadata extraction")
    parser.add_argument("--checksum", action="store_true", help="Use SHA-256 only for change detection")
    parser.add_argument("--force", action="store_true", help="Rewrite even when the fingerprint matches")
    return parser.parse_args()


def main() -> int:
    try:
        result = sync_manifest(parse_args())
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0 if result["ok"] else 2
    except (ManifestError, OSError, ValueError, json.JSONDecodeError) as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False, indent=2), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
