#!/usr/bin/env python3
"""Scan and validate caller-provided pre-roll assets.

The script is intentionally deterministic. It records file metadata and media
metadata, but it does not "understand" visual content. The executing model must
open images / representative video frames, then write description and
effective_region back into the manifest before rendering.
"""

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
DEFAULT_MANIFEST_NAME = "pre_roll_assets_manifest.json"

VIDEO_EXTENSIONS = {".mp4", ".mov", ".m4v", ".mkv", ".webm", ".avi"}
AUDIO_EXTENSIONS = {".mp3", ".wav", ".m4a", ".aac", ".flac", ".ogg"}
IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp", ".bmp", ".gif", ".tif", ".tiff", ".svg"}
FONT_EXTENSIONS = {".ttf", ".otf", ".ttc", ".woff", ".woff2"}
SUBTITLE_EXTENSIONS = {".srt", ".ass", ".vtt", ".lrc"}
SUPPORTED_EXTENSIONS = (
    VIDEO_EXTENSIONS
    | AUDIO_EXTENSIONS
    | IMAGE_EXTENSIONS
    | FONT_EXTENSIONS
    | SUBTITLE_EXTENSIONS
)

VISUAL_KINDS = {"image", "video"}

# These rules only create a rough category from paths. They are not semantic
# understanding and must not replace the model's Read/view step.
ROLE_RULES: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("brand_logo", ("logo", "brand", "品牌", "标识", "汽水")),
    ("background_visual", ("background", "背景", "底图", "底片", "解压", "风景", "scenery")),
    ("benefit_visual", ("benefit", "福利", "金币", "到账", "收益", "提现", "免费听", "余额")),
    ("cta_visual", ("cta", "领取", "下载", "按钮", "call-to-action")),
    ("overlay_visual", ("overlay", "贴片", "贴纸", "物料", "素材", "弹窗", "截图")),
    ("background_music", ("bgm", "背景音乐", "music", "soundtrack")),
    ("voiceover", ("voice", "voiceover", "口播", "配音", "人声")),
)


class ManifestError(RuntimeError):
    pass


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def print_json(data: dict[str, Any], *, stream: Any = None) -> None:
    print(json.dumps(data, ensure_ascii=False, indent=2), file=stream or sys.stdout)


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def write_json(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = path.with_name(path.name + ".tmp")
    temp_path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temp_path.replace(path)


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
    if extension in AUDIO_EXTENSIONS:
        return "audio"
    if extension in IMAGE_EXTENSIONS:
        return "image"
    if extension in FONT_EXTENSIONS:
        return "font"
    if extension in SUBTITLE_EXTENSIONS:
        return "subtitle"
    return "unknown"


def infer_category(relative_path: str, kind: str) -> str:
    if kind == "font":
        return "font"
    if kind == "subtitle":
        return "subtitle"
    lowered = relative_path.casefold()
    for category, keywords in ROLE_RULES:
        if any(keyword.casefold() in lowered for keyword in keywords):
            return category
    return {
        "video": "video_material",
        "audio": "audio_material",
        "image": "image_material",
    }.get(kind, "other_material")


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


def resolve_binary(name: str, explicit_path: str | None = None) -> str | None:
    if explicit_path:
        path = Path(explicit_path).expanduser()
        return str(path.resolve()) if path.exists() else explicit_path
    return shutil.which(name)


def probe_media(path: Path, *, ffprobe: str | None = None) -> dict[str, Any]:
    ffprobe_bin = resolve_binary("ffprobe", ffprobe)
    if not ffprobe_bin:
        return {"probe_ok": False, "probe_error": "ffprobe not found"}
    result = subprocess.run(
        [
            ffprobe_bin,
            "-v",
            "error",
            "-show_entries",
            "format=duration,format_name,bit_rate:stream=codec_type,codec_name,width,height,avg_frame_rate,r_frame_rate,sample_rate,channels",
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
    audio = next(
        (stream for stream in data.get("streams", []) if stream.get("codec_type") == "audio"),
        {},
    )
    duration = format_data.get("duration")
    bit_rate = format_data.get("bit_rate")
    return {
        "probe_ok": True,
        "duration_seconds": round(float(duration), 3) if duration else None,
        "format_name": format_data.get("format_name"),
        "bit_rate": int(bit_rate) if bit_rate else None,
        "video_codec": video.get("codec_name"),
        "width": video.get("width"),
        "height": video.get("height"),
        "fps": parse_fraction(video.get("avg_frame_rate") or video.get("r_frame_rate")),
        "audio_codec": audio.get("codec_name"),
        "sample_rate": int(audio["sample_rate"]) if audio.get("sample_rate") else None,
        "channels": audio.get("channels"),
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
        value = load_json(path)
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
    ffprobe: str | None,
) -> tuple[dict[str, Any], bool]:
    if previous and identity_matches(identity, previous, checksum):
        record = dict(previous)
        record.update(identity)
        return record, True

    record = dict(identity)
    record["file_name"] = Path(identity["relative_path"]).name
    record["category"] = infer_category(identity["relative_path"], identity["kind"])
    record["category_source"] = "path_inferred"
    record["understanding_status"] = "pending" if identity["kind"] in VISUAL_KINDS else "not_required"
    if not quick and identity["kind"] in {"video", "audio", "image"}:
        record["media"] = probe_media(asset_root / identity["relative_path"], ffprobe=ffprobe)
    return record, False


def summarize(assets: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "total": len(assets),
        "total_size_bytes": sum(int(item.get("size_bytes") or 0) for item in assets),
        "by_kind": dict(sorted(Counter(item["kind"] for item in assets).items())),
        "by_category": dict(sorted(Counter(item["category"] for item in assets).items())),
    }


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
        if isinstance(item, dict) and item.get("relative_path")
    }
    current_paths = {item["relative_path"] for item in identities}
    previous_paths = set(previous_assets)
    assets: list[dict[str, Any]] = []
    reused_count = 0
    modified: list[str] = []

    for identity in identities:
        previous = previous_assets.get(identity["relative_path"])
        record, reused = build_asset_record(
            identity,
            asset_root,
            previous if compatible_existing else None,
            quick=args.quick,
            checksum=args.checksum,
            ffprobe=args.ffprobe,
        )
        assets.append(record)
        reused_count += int(reused)
        if previous and not identity_matches(identity, previous, args.checksum):
            modified.append(identity["relative_path"])

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
            "status": "created" if existing is None else "updated",
            "added": sorted(current_paths - previous_paths),
            "removed": sorted(previous_paths - current_paths),
            "modified": sorted(modified),
            "reused_metadata_count": reused_count,
        },
        "scan_errors": scan_errors,
        "assets": assets,
    }
    write_json(manifest_path, manifest)
    return {
        "ok": not scan_errors,
        "status": manifest["changes"]["status"],
        "manifest": str(manifest_path),
        "asset_root": str(asset_root),
        "fingerprint": current_fingerprint,
        "summary": manifest["summary"],
        "changes": manifest["changes"],
        "scan_errors": scan_errors,
        "file_rewritten": True,
    }


def is_remote_reference(value: str) -> bool:
    return value.startswith(("http://", "https://"))


def manifest_asset_index(asset_root: Path, manifest: dict[str, Any]) -> dict[str, dict[str, Any]]:
    index: dict[str, dict[str, Any]] = {}
    for asset in manifest.get("assets", []):
        if not isinstance(asset, dict) or not asset.get("relative_path"):
            continue
        absolute = (asset_root / str(asset["relative_path"])).resolve()
        index[str(absolute)] = asset
    return index


def resolve_local_reference(value: str, asset_root: Path) -> Path:
    raw = Path(value).expanduser()
    if raw.is_absolute():
        return raw.resolve()
    root_candidate = (asset_root / raw).resolve()
    if root_candidate.exists():
        return root_candidate
    return (Path.cwd() / raw).resolve()


def numeric(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    try:
        return float(str(value))
    except (TypeError, ValueError):
        return None


def validate_effective_region(asset: dict[str, Any]) -> str | None:
    region = asset.get("effective_region")
    if not isinstance(region, dict):
        return "missing effective_region"
    x = numeric(region.get("x"))
    y = numeric(region.get("y"))
    width = numeric(region.get("width"))
    height = numeric(region.get("height"))
    if x is None or y is None or width is None or height is None:
        return "effective_region must contain numeric x/y/width/height"
    if x < 0 or y < 0 or width <= 0 or height <= 0:
        return "effective_region must be positive and inside source pixels"
    coordinate_space = region.get("coordinate_space", "source_pixels")
    if coordinate_space != "source_pixels":
        return "effective_region.coordinate_space must be source_pixels"
    media = asset.get("media") if isinstance(asset.get("media"), dict) else {}
    media_width = numeric(media.get("width"))
    media_height = numeric(media.get("height"))
    if media_width and x + width > media_width + 1:
        return "effective_region exceeds source width"
    if media_height and y + height > media_height + 1:
        return "effective_region exceeds source height"
    return None


def extract_selection_items(value: Any) -> list[dict[str, Any]]:
    if isinstance(value, list):
        return [item for item in value if isinstance(item, dict)]
    if not isinstance(value, dict):
        return []
    items: list[dict[str, Any]] = []
    for key in ("materials", "materialSelections", "overlays", "visualMaterials"):
        candidate = value.get(key)
        if isinstance(candidate, list):
            items.extend(item for item in candidate if isinstance(item, dict))
    return items


def validate_manifest_data(
    *,
    asset_root: Path,
    manifest: dict[str, Any],
    required_paths: list[str] | None = None,
    selection_data: Any = None,
) -> dict[str, Any]:
    expected_root = str(asset_root.resolve())
    actual_root = manifest.get("asset_root")
    root_matches = actual_root == expected_root
    assets = [item for item in manifest.get("assets", []) if isinstance(item, dict)]
    visual_assets = [item for item in assets if item.get("kind") in VISUAL_KINDS]

    missing_descriptions: list[str] = []
    missing_effective_regions: list[str] = []
    invalid_effective_regions: list[dict[str, str]] = []

    for asset in visual_assets:
        relative_path = str(asset.get("relative_path") or "")
        if not str(asset.get("description") or "").strip():
            missing_descriptions.append(relative_path)
        region_error = validate_effective_region(asset)
        if region_error:
            if region_error == "missing effective_region":
                missing_effective_regions.append(relative_path)
            else:
                invalid_effective_regions.append({"path": relative_path, "error": region_error})

    index = manifest_asset_index(asset_root, manifest)
    untracked_required_paths: list[str] = []
    remote_required_paths: list[str] = []
    for value in required_paths or []:
        if not value:
            continue
        if is_remote_reference(value):
            remote_required_paths.append(value)
            continue
        resolved = resolve_local_reference(value, asset_root)
        if str(resolved) not in index:
            untracked_required_paths.append(str(resolved))

    selection_items = extract_selection_items(selection_data)
    untracked_selection_paths: list[str] = []
    missing_selection_semantics: list[dict[str, str]] = []
    for item in selection_items:
        raw_path = item.get("path") or item.get("sourcePath") or item.get("filePath")
        if not raw_path or is_remote_reference(str(raw_path)):
            continue
        resolved = resolve_local_reference(str(raw_path), asset_root)
        tracked = index.get(str(resolved))
        if not tracked:
            untracked_selection_paths.append(str(resolved))
            continue
        if tracked.get("kind") in VISUAL_KINDS:
            semantic_role = str(item.get("semantic_role") or item.get("semanticRole") or "")
            matched_text = str(item.get("matched_benefit_text") or item.get("matchedBenefitText") or "")
            if semantic_role != "benefit_point" or not matched_text.strip():
                missing_selection_semantics.append(
                    {
                        "path": str(resolved),
                        "required": "semantic_role=benefit_point and matched_benefit_text",
                    }
                )

    ok = all(
        [
            root_matches,
            not missing_descriptions,
            not missing_effective_regions,
            not invalid_effective_regions,
            not untracked_required_paths,
            not untracked_selection_paths,
            not missing_selection_semantics,
        ]
    )
    return {
        "ok": ok,
        "asset_root": expected_root,
        "manifest_asset_root": actual_root,
        "root_matches": root_matches,
        "summary": manifest.get("summary", {}),
        "asset_understanding": {
            "ok": not (missing_descriptions or missing_effective_regions or invalid_effective_regions),
            "visual_asset_count": len(visual_assets),
            "missing_descriptions": missing_descriptions,
            "missing_effective_regions": missing_effective_regions,
            "invalid_effective_regions": invalid_effective_regions,
        },
        "required_paths": {
            "checked_count": len(required_paths or []),
            "remote_unchecked": remote_required_paths,
            "untracked": untracked_required_paths,
        },
        "material_selection": {
            "checked_count": len(selection_items),
            "untracked": untracked_selection_paths,
            "missing_semantics": missing_selection_semantics,
        },
    }


def validate_manifest_for_paths(
    *,
    asset_root: Path | str,
    asset_manifest: Path | str,
    required_paths: list[str] | None = None,
    selection_json: Path | str | None = None,
) -> dict[str, Any]:
    root = Path(asset_root).expanduser().resolve()
    manifest_path = Path(asset_manifest).expanduser().resolve()
    if not root.is_dir():
        raise ManifestError(f"Asset root directory not found: {root}")
    if not manifest_path.exists():
        raise ManifestError(f"Asset manifest not found: {manifest_path}")
    manifest = load_json(manifest_path)
    if not isinstance(manifest, dict):
        raise ManifestError("Asset manifest root must be a JSON object")
    if manifest.get("schema_version") != SCHEMA_VERSION:
        raise ManifestError(f"Unsupported manifest schema_version: {manifest.get('schema_version')}")
    selection_data = load_json(Path(selection_json).expanduser().resolve()) if selection_json else None
    result = validate_manifest_data(
        asset_root=root,
        manifest=manifest,
        required_paths=required_paths,
        selection_data=selection_data,
    )
    result["manifest"] = str(manifest_path)
    return result


def validate_command(args: argparse.Namespace) -> dict[str, Any]:
    result = validate_manifest_for_paths(
        asset_root=args.asset_root,
        asset_manifest=args.asset_manifest,
        required_paths=args.required_path or [],
        selection_json=args.selection_json,
    )
    if args.output_json:
        write_json(Path(args.output_json).expanduser().resolve(), result)
    return result


def ffprobe_duration(path: Path, *, ffprobe: str | None = None) -> float | None:
    ffprobe_bin = resolve_binary("ffprobe", ffprobe)
    if not ffprobe_bin:
        return None
    result = subprocess.run(
        [
            ffprobe_bin,
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
        return None
    try:
        return float(result.stdout.strip())
    except ValueError:
        return None


def needs_visual_understanding(asset: dict[str, Any]) -> bool:
    if asset.get("kind") not in VISUAL_KINDS:
        return False
    if not str(asset.get("description") or "").strip():
        return True
    return validate_effective_region(asset) is not None


def safe_frame_stem(relative_path: str) -> str:
    path = Path(relative_path)
    parts = [part for part in path.with_suffix("").parts if part not in {"", ".", ".."}]
    return "__".join(parts) or "video"


def extract_frames_command(args: argparse.Namespace) -> dict[str, Any]:
    ffmpeg_bin = resolve_binary("ffmpeg", args.ffmpeg)
    if not ffmpeg_bin:
        raise ManifestError("ffmpeg not found")
    root = args.asset_root.expanduser().resolve()
    manifest_path = args.asset_manifest.expanduser().resolve()
    manifest = load_json(manifest_path)
    output_dir = args.output_dir.expanduser().resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    frames: list[dict[str, Any]] = []
    errors: list[dict[str, str]] = []
    for asset in manifest.get("assets", []):
        if not isinstance(asset, dict) or asset.get("kind") != "video":
            continue
        if args.only_missing and not needs_visual_understanding(asset):
            continue
        relative_path = str(asset.get("relative_path") or "")
        source = (root / relative_path).resolve()
        duration = (
            numeric((asset.get("media") or {}).get("duration_seconds"))
            if isinstance(asset.get("media"), dict)
            else None
        ) or ffprobe_duration(source, ffprobe=args.ffprobe) or 1.0
        times = [0.1, duration * 0.25, duration * 0.5, duration * 0.75, max(0.1, duration - 0.2)]
        unique_times = sorted({round(max(0.0, min(duration - 0.05, item)), 3) for item in times})
        for index, timestamp in enumerate(unique_times):
            frame_path = output_dir / f"{safe_frame_stem(relative_path)}__{index:02d}_{timestamp:.3f}s.jpg"
            command = [
                ffmpeg_bin,
                "-hide_banner",
                "-y",
                "-ss",
                f"{timestamp:.3f}",
                "-i",
                str(source),
                "-frames:v",
                "1",
                "-q:v",
                "2",
                str(frame_path),
            ]
            result = subprocess.run(command, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False)
            if result.returncode == 0 and frame_path.exists():
                frames.append({"source": str(source), "relative_path": relative_path, "time": timestamp, "frame": str(frame_path)})
            else:
                errors.append({"source": str(source), "error": (result.stderr or "ffmpeg failed").strip()})
    output = {"ok": not errors, "output_dir": str(output_dir), "frames": frames, "errors": errors}
    if args.output_json:
        write_json(Path(args.output_json).expanduser().resolve(), output)
    return output


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    sync = subparsers.add_parser("sync", help="Scan assets and write/update a manifest")
    sync.add_argument("--workspace", type=Path, required=True)
    sync.add_argument("--asset-root", type=Path, required=True)
    sync.add_argument("--manifest", type=Path, help=f"Default: <workspace>/{DEFAULT_MANIFEST_NAME}")
    sync.add_argument("--quick", action="store_true", help="Skip FFprobe metadata extraction")
    sync.add_argument("--checksum", action="store_true", help="Use SHA-256 content hashes")
    sync.add_argument("--force", action="store_true", help="Rewrite even when fingerprint is unchanged")
    sync.add_argument("--ffprobe", default=None)
    sync.set_defaults(func=sync_manifest)

    validate = subparsers.add_parser("validate", help="Validate manifest understanding and referenced visual assets")
    validate.add_argument("--asset-root", type=Path, required=True)
    validate.add_argument("--asset-manifest", type=Path, required=True)
    validate.add_argument("--required-path", action="append", default=[], help="Local visual path that must be tracked. Repeatable.")
    validate.add_argument("--selection-json", type=Path, default=None, help="Optional JSON containing materials/materialSelections")
    validate.add_argument("--output-json", type=Path, default=None)
    validate.set_defaults(func=validate_command)

    frames = subparsers.add_parser("extract-frames", help="Extract representative frames for model visual review")
    frames.add_argument("--asset-root", type=Path, required=True)
    frames.add_argument("--asset-manifest", type=Path, required=True)
    frames.add_argument("--output-dir", type=Path, required=True)
    frames.add_argument("--only-missing", action="store_true", help="Only export frames for videos still missing understanding")
    frames.add_argument("--ffmpeg", default=None)
    frames.add_argument("--ffprobe", default=None)
    frames.add_argument("--output-json", type=Path, default=None)
    frames.set_defaults(func=extract_frames_command)

    return parser


def main() -> int:
    try:
        args = build_parser().parse_args()
        result = args.func(args)
        print_json(result)
        return 0 if result.get("ok", False) else 2
    except (ManifestError, OSError, ValueError, json.JSONDecodeError) as exc:
        print_json({"ok": False, "error": str(exc)}, stream=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
