#!/usr/bin/env python3
"""Standalone Soda Music mixed-cut workflow helper.

The script keeps policy checks separate from rendering.  It can inspect assets,
find pause candidates, remove approved ranges, validate channel rules, call the
bundled FFmpeg renderer, and generate a technical QA report.
"""

from __future__ import annotations

import argparse
import difflib
import json
import math
import os
import re
import shutil
import subprocess
import sys
import statistics
import tempfile
import unicodedata
from pathlib import Path
from typing import Any, Iterable

from ass_fonts import AssFontError, validate_ass_font_config
from caption_layout import (
    CaptionLayoutError,
    count_caption_characters,
    derive_caption_character_budget,
    layout_caption_text,
)
from motion_effects_bridge import (
    MotionEffectsError,
    apply_motion_overrides,
    inspect_motion_skill,
    resolve_motion_policy,
)
from special_material_matches import special_match_metadata_errors
from timeline_handoffs import (
    TimelineHandoffError,
    validate_material_handoffs,
)


SKILL_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_RENDERER = SKILL_ROOT / "scripts" / "standalone_renderer.py"
VISUAL_ASSET_LIBRARY_SKILL_NAME = "manage-visual-asset-library"

CHANNELS = ("old-down", "new-high-mid", "free-listen", "coin-non-down", "general")
GLOBAL_BANNED_TERMS = ("红包", "花不完", "必听", "必点", "躺平", "emo")
LIVING_COST_TERMS = ("覆盖日常开销", "日常开销", "生活费", "买菜钱")
ARROW_CHARS = ("→", "←", "↑", "↓", "➜", "➡", "⇩", "⤵", "↘", "↙")
THIRD_PARTY_TERMS = ("抖音", "剪映")
DEFAULT_BGM_TARGET_LUFS = -28.0
DEFAULT_BGM_FINE_VOLUME = 1.0
DEFAULT_ASSET_MANIFEST_NAME = "visual_assets_manifest.json"

IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp", ".bmp", ".gif", ".tif", ".tiff", ".svg"}
VIDEO_EXTENSIONS = {".mp4", ".mov", ".m4v", ".mkv", ".webm", ".avi"}
VISUAL_EXTENSIONS = IMAGE_EXTENSIONS | VIDEO_EXTENSIONS


class PipelineError(RuntimeError):
    pass


def run_command(
    command: list[str],
    *,
    cwd: Path | None = None,
    capture: bool = True,
    check: bool = True,
) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(
        command,
        cwd=str(cwd) if cwd else None,
        text=True,
        stdout=subprocess.PIPE if capture else None,
        stderr=subprocess.PIPE if capture else None,
        check=False,
    )
    if check and result.returncode != 0:
        output = "\n".join(x for x in (result.stdout, result.stderr) if x)
        raise PipelineError(f"Command failed ({result.returncode}): {' '.join(command)}\n{output}")
    return result


def require_binary(name: str) -> str:
    value = shutil.which(name)
    if not value:
        raise PipelineError(f"Required binary not found: {name}")
    return value


def write_json(data: Any, output: Path | None) -> None:
    content = json.dumps(data, ensure_ascii=False, indent=2)
    if output:
        output.expanduser().resolve().parent.mkdir(parents=True, exist_ok=True)
        output.expanduser().resolve().write_text(content + "\n", encoding="utf-8")
    print(content)


def parse_fraction(value: str | None) -> float | None:
    if not value or value == "0/0":
        return None
    if "/" in value:
        numerator, denominator = value.split("/", 1)
        denominator_value = float(denominator)
        return float(numerator) / denominator_value if denominator_value else None
    return float(value)


def ffprobe(path: Path) -> dict[str, Any]:
    require_binary("ffprobe")
    resolved = path.expanduser().resolve()
    if not resolved.exists():
        raise PipelineError(f"Video not found: {resolved}")
    result = run_command(
        [
            "ffprobe",
            "-v",
            "error",
            "-show_entries",
            "format=duration,size,bit_rate:stream=index,codec_type,codec_name,width,height,r_frame_rate,avg_frame_rate,sample_rate,channels",
            "-of",
            "json",
            str(resolved),
        ]
    )
    data = json.loads(result.stdout)
    data["path"] = str(resolved)
    return data


def media_summary(path: Path) -> dict[str, Any]:
    data = ffprobe(path)
    video = next((s for s in data.get("streams", []) if s.get("codec_type") == "video"), {})
    audio = next((s for s in data.get("streams", []) if s.get("codec_type") == "audio"), {})
    fmt = data.get("format", {})
    return {
        "path": data["path"],
        "duration": float(fmt.get("duration") or 0.0),
        "size": int(fmt.get("size") or 0),
        "bit_rate": int(fmt.get("bit_rate") or 0),
        "video_codec": video.get("codec_name"),
        "width": video.get("width"),
        "height": video.get("height"),
        "fps": parse_fraction(video.get("avg_frame_rate") or video.get("r_frame_rate")),
        "audio_codec": audio.get("codec_name"),
        "sample_rate": int(audio.get("sample_rate") or 0) if audio else None,
        "channels": audio.get("channels"),
    }


def resolve_visual_policy(config: dict[str, Any]) -> dict[str, Any]:
    raw = config.get("visual_policy", {})
    if not isinstance(raw, dict):
        raise PipelineError("visual_policy must be an object")
    source_check = str(raw.get("source_black_bar_check", "error"))
    safe_area_raw = raw.get("material_safe_area", {})
    if not isinstance(safe_area_raw, dict):
        raise PipelineError("visual_policy.material_safe_area must be an object")
    try:
        safe_area = {
            "left": int(safe_area_raw.get("left", 48)),
            "right": int(safe_area_raw.get("right", 48)),
            "top": int(safe_area_raw.get("top", 320)),
            "bottom": int(safe_area_raw.get("bottom", 180)),
        }
    except (TypeError, ValueError) as exc:
        raise PipelineError("visual_policy.material_safe_area margins must be integers") from exc
    if any(value < 0 for value in safe_area.values()):
        raise PipelineError("visual_policy.material_safe_area margins must be non-negative")
    canvas_width = int(config.get("width", 1080))
    canvas_height = int(config.get("height", 1920))
    if (
        safe_area["left"] + safe_area["right"] >= canvas_width
        or safe_area["top"] + safe_area["bottom"] >= canvas_height
    ):
        raise PipelineError("visual_policy.material_safe_area leaves no usable material area")
    policy = {
        "forbid_generated_black_bars": bool(raw.get("forbid_generated_black_bars", True)),
        "forbid_caption_backplates": bool(raw.get("forbid_caption_backplates", True)),
        "caption_outline_policy": str(raw.get("caption_outline_policy", "thin_black_2_3px")),
        "forbid_material_backplates": bool(raw.get("forbid_material_backplates", True)),
        "require_logo_top_layer": bool(raw.get("require_logo_top_layer", True)),
        "require_warning_top_layer": bool(raw.get("require_warning_top_layer", True)),
        "enforce_material_safe_area": bool(raw.get("enforce_material_safe_area", True)),
        "preserve_material_size": bool(raw.get("preserve_material_size", True)),
        "reposition_before_scale": bool(raw.get("reposition_before_scale", True)),
        "match_materials_only_for_benefit_points": bool(
            raw.get("match_materials_only_for_benefit_points", True)
        ),
        "seamless_material_handoffs": bool(
            raw.get("seamless_material_handoffs", True)
        ),
        "align_material_cuts_to_caption_boundaries": bool(
            raw.get("align_material_cuts_to_caption_boundaries", True)
        ),
        "material_safe_area": safe_area,
        "source_black_bar_check": source_check,
    }
    if not all(
        policy[key]
        for key in (
            "forbid_generated_black_bars",
            "forbid_caption_backplates",
            "forbid_material_backplates",
            "require_logo_top_layer",
            "require_warning_top_layer",
            "enforce_material_safe_area",
            "preserve_material_size",
            "reposition_before_scale",
            "match_materials_only_for_benefit_points",
            "seamless_material_handoffs",
            "align_material_cuts_to_caption_boundaries",
        )
    ) or source_check != "error" or policy["caption_outline_policy"] != "thin_black_2_3px":
        raise PipelineError(
            "visual policy is mandatory: generated/caption/material backplates must be forbidden, caption_outline_policy must be thin_black_2_3px, logo and warning must be top layers, material matching must be limited to benefit points, material handoffs must be seamless and caption-aligned, material safe area must be enforced, material size must be preserved before fitting to the largest brand-safe size, and source_black_bar_check must be error"
        )
    return policy


def detect_embedded_black_bars(path: Path) -> dict[str, Any]:
    summary = media_summary(path)
    width = int(summary.get("width") or 0)
    height = int(summary.get("height") or 0)
    duration = float(summary.get("duration") or 0.0)
    if width <= 0 or height <= 0 or duration <= 0:
        return {
            "ok": True,
            "status": "not_applicable",
            "reason": "missing video dimensions or duration",
        }

    scan_duration = min(max(duration, 0.75), 4.0)
    result = run_command(
        [
            "ffmpeg",
            "-hide_banner",
            "-nostats",
            "-i",
            str(path),
            "-vf",
            "fps=4,cropdetect=24:16:0",
            "-t",
            f"{scan_duration:.3f}",
            "-f",
            "null",
            "-",
        ],
        check=False,
    )
    log = (result.stderr or "") + "\n" + (result.stdout or "")
    crops = [
        tuple(int(value) for value in match)
        for match in re.findall(r"crop=(\d+):(\d+):(\d+):(\d+)", log)
    ]
    if not crops:
        return {
            "ok": True,
            "status": "inconclusive",
            "sample_count": 0,
            "reason": "cropdetect returned no samples",
        }

    counts: dict[tuple[int, int, int, int], int] = {}
    for crop in crops:
        counts[crop] = counts.get(crop, 0) + 1
    stable_crop, stable_count = max(counts.items(), key=lambda item: item[1])
    crop_width, crop_height, crop_x, crop_y = stable_crop
    required_count = max(2, math.ceil(len(crops) * 0.6))
    lost_width = max(0, width - crop_width)
    lost_height = max(0, height - crop_height)
    fixed_bars = (
        stable_count >= required_count
        and (lost_width >= 8 or lost_height >= 8)
        and crop_width * crop_height < width * height * 0.99
    )
    return {
        "ok": not fixed_bars,
        "status": "fixed_black_bars_detected" if fixed_bars else "clear",
        "source_size": [width, height],
        "stable_crop": [crop_width, crop_height, crop_x, crop_y],
        "stable_count": stable_count,
        "sample_count": len(crops),
    }


def load_timeline_config(path: Path) -> dict[str, Any]:
    resolved = path.expanduser().resolve()
    if not resolved.exists():
        raise PipelineError(f"Timeline JSON not found: {resolved}")
    config = json.loads(resolved.read_text(encoding="utf-8"))
    for field in ("font", "logo", "tail", "materials", "captions"):
        if field not in config:
            raise PipelineError(f"Timeline JSON is missing required field: {field}")
    placeholders: list[str] = []

    def find_placeholders(value: Any, location: str) -> None:
        if isinstance(value, dict):
            for key, item in value.items():
                find_placeholders(item, f"{location}.{key}")
        elif isinstance(value, list):
            for index, item in enumerate(value):
                find_placeholders(item, f"{location}[{index}]")
        elif isinstance(value, str) and value.strip().startswith("<") and value.strip().endswith(">"):
            placeholders.append(location)

    find_placeholders(config, "timeline")
    if placeholders:
        raise PipelineError(
            "Timeline JSON contains unresolved placeholders: " + ", ".join(placeholders)
        )
    try:
        validate_ass_font_config(config.get("font", {}))
    except AssFontError as exc:
        raise PipelineError(str(exc)) from exc
    policy = resolve_visual_policy(config)
    for index, material in enumerate(config.get("materials", [])):
        if not isinstance(material, dict):
            raise PipelineError(f"materials[{index}] must be an object")
        if str(material.get("semantic_role", "")) != "benefit_point":
            raise PipelineError(
                f"materials[{index}] must use semantic_role=benefit_point; non-benefit narration must not match supplemental materials"
            )
        if not str(material.get("matched_benefit_text", "")).strip():
            raise PipelineError(
                f"materials[{index}] must record matched_benefit_text from the benefit-point narration"
            )
    special_match_errors = special_match_metadata_errors(config.get("materials", []))
    if special_match_errors:
        raise PipelineError("; ".join(special_match_errors))
    style = config.get("font", {}).get("caption_style", {})
    if not isinstance(style, dict):
        raise PipelineError("font.caption_style must be an object")
    try:
        outline = float(style.get("outline", 3))
        shadow = float(style.get("shadow", 0))
    except (TypeError, ValueError) as exc:
        raise PipelineError("font.caption_style outline and shadow must be numbers") from exc
    if not 2 <= outline <= 3 or shadow != 0:
        raise PipelineError(
            "caption policy requires a 2-3px black outline and shadow=0"
        )
    caption_layout = build_caption_layout_report(config)
    if not caption_layout["ok"]:
        raise PipelineError("; ".join(str(error) for error in caption_layout["errors"]))
    try:
        resolve_motion_policy(config)
    except MotionEffectsError as exc:
        raise PipelineError(str(exc)) from exc
    return config


def build_caption_layout_report(config: dict[str, Any]) -> dict[str, Any]:
    style = config.get("font", {}).get("caption_style", {})
    if not isinstance(style, dict):
        raise PipelineError("font.caption_style must be an object")
    width = int(config.get("width", 1080))
    try:
        character_budget = derive_caption_character_budget(style, width)
    except CaptionLayoutError as exc:
        raise PipelineError(f"Unable to derive caption character budget: {exc}") from exc
    entries: list[dict[str, Any]] = []
    errors: list[str] = []
    for index, caption in enumerate(config.get("captions", [])):
        text = normalize_subtitle_text(str(caption.get("text", "")))
        try:
            layout = layout_caption_text(text, style, width)
        except CaptionLayoutError as exc:
            errors.append(f"captions[{index}] cannot fit the caption safe area: {exc}")
            continue
        entries.append(
            {
                "index": index,
                "text": text,
                **layout,
            }
        )
    return {
        "ok": not errors,
        "caption_character_budget": character_budget,
        "caption_count": len(entries),
        "captions": entries,
        "errors": errors,
    }


def cmd_caption_budget(args: argparse.Namespace) -> int:
    timeline_path = args.timeline_json.expanduser().resolve()
    if not timeline_path.exists():
        raise PipelineError(f"Timeline JSON not found: {timeline_path}")
    try:
        config = json.loads(timeline_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise PipelineError(f"Unable to read timeline JSON: {timeline_path}: {exc}") from exc
    style = config.get("font", {}).get("caption_style", {})
    if not isinstance(style, dict):
        raise PipelineError("font.caption_style must be an object")
    try:
        budget = derive_caption_character_budget(
            style,
            int(config.get("width", 1080)),
        )
    except CaptionLayoutError as exc:
        raise PipelineError(f"Unable to derive caption character budget: {exc}") from exc
    report = {
        "ok": True,
        "timeline_json": str(timeline_path),
        "caption_character_budget": budget,
        "instruction": (
            "Use max_characters_per_line for model semantic segmentation; "
            "insert semantic line breaks without changing the spoken wording."
        ),
    }
    write_json(report, args.output_json)
    return 0


def resolve_timeline_asset(asset_root: Path, value: str) -> Path:
    path = Path(value).expanduser()
    return path.resolve() if path.is_absolute() else (asset_root / path).resolve()


def timeline_asset_paths(config: dict[str, Any], asset_root: Path, logo_variant: str) -> dict[str, Path]:
    logo_key = "white_path" if logo_variant == "white" else "black_path"
    result = {
        "font": resolve_timeline_asset(asset_root, str(config["font"]["body_path"])),
        "brand_font": resolve_timeline_asset(asset_root, str(config["font"]["brand_path"])),
        "logo": resolve_timeline_asset(asset_root, str(config["logo"][logo_key])),
        "tail": resolve_timeline_asset(asset_root, str(config["tail"]["path"])),
    }
    for index, item in enumerate(config["materials"]):
        result[f"material_{index}_{item.get('name', 'unnamed')}"] = resolve_timeline_asset(
            asset_root, str(item["path"])
        )
    return result


def validate_speed(value: float | None) -> float:
    speed = 1.1 if value is None else float(value)
    if not 0.5 <= speed <= 2.0:
        raise PipelineError("speed must be between 0.5 and 2.0 for FFmpeg atempo")
    return speed


def validate_bgm_settings(target_lufs: float, fine_volume: float) -> tuple[float, float]:
    target = float(target_lufs)
    volume = float(fine_volume)
    if not -40.0 <= target <= -18.0:
        raise PipelineError("bgm-target-lufs must be between -40 and -18 LUFS")
    if not 0.5 <= volume <= 1.5:
        raise PipelineError(
            "bgm-volume is a post-normalization fine gain and must be between 0.5 and 1.5; use bgm-target-lufs for the main level"
        )
    return target, volume


def estimate_render_duration(
    input_path: Path, timeline_path: Path, asset_root: Path, speed_override: float | None = None
) -> float:
    config = load_timeline_config(timeline_path)
    input_duration = float(media_summary(input_path)["duration"])
    speed = validate_speed(speed_override if speed_override is not None else config.get("speed", 1.1))
    tail_duration = config.get("tail_duration")
    if tail_duration is None:
        tail_path = resolve_timeline_asset(asset_root, str(config["tail"]["path"]))
        tail_duration = media_summary(tail_path)["duration"]
    return input_duration / speed + float(tail_duration)


def resolve_asset_manifest_path(timeline_path: Path, value: Path | None) -> Path:
    if value is not None:
        return value.expanduser().resolve()
    return timeline_path.expanduser().resolve().parent / DEFAULT_ASSET_MANIFEST_NAME


def resolve_visual_asset_library_script() -> Path:
    candidates: list[Path] = []
    configured = os.environ.get("VISUAL_ASSET_LIBRARY_SKILL_DIR")
    if configured:
        candidates.append(Path(configured).expanduser())
    candidates.append(SKILL_ROOT.parent / VISUAL_ASSET_LIBRARY_SKILL_NAME)
    codex_home = Path(os.environ.get("CODEX_HOME", Path.home() / ".codex")).expanduser()
    candidates.append(codex_home / "skills" / VISUAL_ASSET_LIBRARY_SKILL_NAME)

    checked: list[str] = []
    for root in candidates:
        script = root.resolve() / "scripts" / "asset_manifest.py"
        if str(script) in checked:
            continue
        checked.append(str(script))
        if script.is_file():
            return script
    raise PipelineError(
        "Required Skill manage-visual-asset-library was not found. "
        "Install it beside edit-soda-music-video or set VISUAL_ASSET_LIBRARY_SKILL_DIR. "
        "Checked: "
        + ", ".join(checked)
    )


def validate_asset_understanding(
    manifest_path: Path,
    asset_root: Path,
    config: dict[str, Any],
) -> dict[str, Any]:
    """Gate rendering on a synced manifest whose visual assets have descriptions."""
    report: dict[str, Any] = {
        "manifest": str(manifest_path),
        "asset_root": str(asset_root),
        "ok": False,
        "status": "missing",
        "visual_asset_count": 0,
        "missing_descriptions": [],
        "missing_effective_regions": [],
        "invalid_effective_regions": [],
        "untracked_timeline_visual_assets": [],
        "errors": [],
    }
    if not manifest_path.exists():
        report["errors"].append(
            "视觉素材 Manifest 不存在；先使用 manage-visual-asset-library 完成同步、Read 理解和校验。"
        )
        return report
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        report["errors"].append(f"素材 Manifest 无法读取：{exc}")
        return report
    if not isinstance(manifest, dict):
        report["errors"].append("素材 Manifest 顶层必须是 JSON 对象。")
        return report

    manifest_root = Path(str(manifest.get("asset_root", ""))).expanduser().resolve()
    if manifest_root != asset_root.expanduser().resolve():
        report["errors"].append(
            f"素材 Manifest 的 asset_root 与当前 --asset-root 不一致：{manifest_root} != {asset_root}。"
        )
    assets = manifest.get("assets", [])
    if not isinstance(assets, list):
        report["errors"].append("素材 Manifest 的 assets 必须是数组。")
        return report

    visual_assets = [
        item
        for item in assets
        if isinstance(item, dict) and str(item.get("kind", "")).lower() in {"image", "video"}
    ]
    report["visual_asset_count"] = len(visual_assets)
    missing_descriptions = sorted(
        str(item.get("relative_path", ""))
        for item in visual_assets
        if not str(item.get("description", "")).strip()
    )
    report["missing_descriptions"] = missing_descriptions
    if missing_descriptions:
        report["errors"].append(
            "素材理解未完成，以下图片/视频缺少 description：" + ", ".join(missing_descriptions)
        )

    missing_effective_regions: list[str] = []
    invalid_effective_regions: list[str] = []
    for item in visual_assets:
        relative_path = str(item.get("relative_path", ""))
        region = item.get("effective_region")
        if not isinstance(region, dict):
            missing_effective_regions.append(relative_path)
            continue
        try:
            x = float(region["x"])
            y = float(region["y"])
            width = float(region["width"])
            height = float(region["height"])
        except (KeyError, TypeError, ValueError):
            invalid_effective_regions.append(relative_path)
            continue
        media = item.get("media", {}) if isinstance(item.get("media"), dict) else {}
        source_width = float(media.get("width") or 0)
        source_height = float(media.get("height") or 0)
        coordinate_space = str(region.get("coordinate_space", "source_pixels"))
        invalid = (
            coordinate_space != "source_pixels"
            or x < 0
            or y < 0
            or width <= 0
            or height <= 0
            or (source_width > 0 and x + width > source_width + 1)
            or (source_height > 0 and y + height > source_height + 1)
        )
        if invalid:
            invalid_effective_regions.append(relative_path)
    report["missing_effective_regions"] = sorted(missing_effective_regions)
    report["invalid_effective_regions"] = sorted(invalid_effective_regions)
    if missing_effective_regions:
        report["errors"].append(
            "素材有效区域理解未完成，以下图片/视频缺少 effective_region："
            + ", ".join(sorted(missing_effective_regions))
        )
    if invalid_effective_regions:
        report["errors"].append(
            "以下素材的 effective_region 不是有效的 source_pixels 边界："
            + ", ".join(sorted(invalid_effective_regions))
        )

    by_relative_path = {
        str(item.get("relative_path")): item
        for item in visual_assets
        if item.get("relative_path")
    }
    timeline_visual_refs: list[tuple[str, Path]] = []
    for index, item in enumerate(config.get("materials", [])):
        if not isinstance(item, dict) or not item.get("path"):
            continue
        timeline_visual_refs.append((f"materials[{index}].path", resolve_timeline_asset(asset_root, str(item["path"]))))
    for key in ("white_path", "black_path"):
        value = config.get("logo", {}).get(key)
        if value:
            timeline_visual_refs.append((f"logo.{key}", resolve_timeline_asset(asset_root, str(value))))
    tail_value = config.get("tail", {}).get("path")
    if tail_value:
        timeline_visual_refs.append(("tail.path", resolve_timeline_asset(asset_root, str(tail_value))))

    untracked: list[str] = []
    for location, path in timeline_visual_refs:
        if path.suffix.casefold() not in VISUAL_EXTENSIONS:
            continue
        try:
            relative = path.relative_to(asset_root).as_posix()
        except ValueError:
            untracked.append(f"{location} -> {path}")
            continue
        record = by_relative_path.get(relative)
        if record is None:
            untracked.append(f"{location} -> {relative}")
    report["untracked_timeline_visual_assets"] = sorted(untracked)
    if untracked:
        report["errors"].append(
            "时间轴引用了未出现在 Manifest 的视觉素材：" + ", ".join(sorted(untracked))
        )

    report["status"] = "complete" if not report["errors"] else "incomplete"
    report["ok"] = not report["errors"]
    return report


def preflight_report(args: argparse.Namespace) -> dict[str, Any]:
    asset_root = args.asset_root.expanduser().resolve()
    bgm = args.bgm.expanduser().resolve() if args.bgm else None
    input_path = args.input.expanduser().resolve() if args.input else None
    timeline_path = args.timeline_json.expanduser().resolve()
    manifest_path = resolve_asset_manifest_path(
        timeline_path,
        getattr(args, "asset_manifest", None),
    )
    renderer = DEFAULT_RENDERER.resolve()
    logo_variant = args.logo_variant

    checks: list[dict[str, Any]] = []
    visual_checks: list[dict[str, Any]] = []
    visual_errors: list[str] = []
    visual_warnings: list[str] = []
    visual_policy: dict[str, Any] | None = None
    motion_effects: dict[str, Any] | None = None
    asset_understanding: dict[str, Any] | None = None
    material_timeline: dict[str, Any] | None = None
    caption_layout: dict[str, Any] | None = None

    def check(name: str, path: Path, required: bool = True) -> None:
        checks.append(
            {
                "name": name,
                "path": str(path),
                "required": required,
                "exists": path.exists(),
                "size": path.stat().st_size if path.exists() and path.is_file() else None,
            }
        )

    check("renderer", renderer)
    check("asset_root", asset_root)
    check("asset_manifest", manifest_path)
    check("timeline_json", timeline_path)
    if input_path:
        check("input", input_path)
    if bgm:
        check("bgm", bgm)
    if timeline_path.exists():
        config = load_timeline_config(timeline_path)
        try:
            config = apply_motion_overrides(
                config,
                getattr(args, "motion_effects", None),
                getattr(args, "motion_seed", None),
            )
            motion_effects = inspect_motion_skill(config)
        except MotionEffectsError as exc:
            visual_errors.append(str(exc))
            motion_effects = {"ready": False, "error": str(exc)}
        speed_override = getattr(args, "speed", None)
        if speed_override is not None:
            config["speed"] = validate_speed(speed_override)
        try:
            material_timeline = validate_material_handoffs(config)
        except TimelineHandoffError as exc:
            visual_errors.append(f"Material timeline validation failed: {exc}")
            material_timeline = {"ok": False, "error": str(exc)}
        visual_policy = resolve_visual_policy(config)
        caption_layout = build_caption_layout_report(config)
        if not caption_layout["ok"]:
            visual_errors.extend(str(item) for item in caption_layout["errors"])
        asset_understanding = validate_asset_understanding(manifest_path, asset_root, config)
        if not asset_understanding["ok"]:
            visual_errors.extend(str(item) for item in asset_understanding["errors"])
        for name, path in timeline_asset_paths(config, asset_root, logo_variant).items():
            check(name, path)
        if visual_policy["source_black_bar_check"] != "off" and shutil.which("ffmpeg"):
            for index, item in enumerate(config["materials"]):
                if str(item.get("kind", "")).lower() != "video":
                    continue
                path = resolve_timeline_asset(asset_root, str(item["path"]))
                if not path.exists():
                    continue
                result = detect_embedded_black_bars(path)
                result.update(
                    {
                        "name": f"material_{index}_{item.get('name', 'unnamed')}",
                        "path": str(path),
                    }
                )
                visual_checks.append(result)
                if not result["ok"]:
                    message = (
                        f"素材检测到跨多帧稳定的固定黑边：{path}，"
                        f"source={result.get('source_size')} crop={result.get('stable_crop')}"
                    )
                    if visual_policy["source_black_bar_check"] == "error":
                        visual_errors.append(message)
                    else:
                        visual_warnings.append(message)
        if motion_effects:
            required = motion_effects.get("mode") == "required"
            check(
                "video_motion_effects_skill",
                Path(str(motion_effects.get("skill_root", ""))),
                required=required,
            )
            if required and not motion_effects.get("ready"):
                visual_errors.append(
                    "video-motion-effects is required but not ready: "
                    + ", ".join(str(item) for item in motion_effects.get("missing", []))
                )
            elif motion_effects.get("mode") == "auto" and not motion_effects.get("ready"):
                visual_warnings.append(
                    "video-motion-effects is unavailable; rendering will use static material overlays"
                )

    binaries = {name: shutil.which(name) for name in ("ffmpeg", "ffprobe")}
    missing = [item for item in checks if item["required"] and not item["exists"]]
    missing_binaries = [name for name, value in binaries.items() if not value]
    return {
        "ok": not missing and not missing_binaries and not visual_errors,
        "asset_root": str(asset_root),
        "asset_manifest": str(manifest_path),
        "asset_understanding": asset_understanding,
        "material_timeline": material_timeline,
        "caption_layout": caption_layout,
        "timeline_json": str(timeline_path),
        "renderer": str(renderer),
        "binaries": binaries,
        "checks": checks,
        "missing": missing,
        "missing_binaries": missing_binaries,
        "visual_policy": visual_policy,
        "visual_checks": visual_checks,
        "visual_errors": visual_errors,
        "visual_warnings": visual_warnings,
        "motion_effects": motion_effects,
        "notes": [
            "The base renderer uses Python standard library, ffmpeg, and ffprobe; installed video-motion-effects adds optional Remotion alpha overlays.",
            "The visual Manifest stores image/video metadata and model-written understanding only; pass task-specific --asset-root, --bgm, and --timeline-json values.",
            "Internal asset labels and file names must not bypass final visual, subtitle, or speech compliance checks.",
            "Caption backplates are forbidden; captions require a 2-3px black outline, shadow=0, and a layer above all materials.",
            "Caption preflight reports explicit balanced lines and weighted line widths; text that needs more than three safe lines is blocked instead of shrinking the font.",
            "Material size is preserved by default; the renderer repositions first and, only when required, scales to the largest size that fits outside the logo and warning protection regions without a fixed scale threshold.",
            "Rendering is blocked until every image/video in the synced Manifest has a model-written description and source-pixel effective_region, and all timeline visual assets are tracked by that Manifest.",
            "Every supplemental material must be tied to explicit benefit-point narration through semantic_role=benefit_point and matched_benefit_text.",
            "Materials use half-open [start,end) intervals. Inside one sequence_id, every end must exactly equal the next start, and every handoff must equal a caption start; use a different sequence_id only for an intentional digital-human gap.",
        ],
    }


def cmd_preflight(args: argparse.Namespace) -> int:
    report = preflight_report(args)
    write_json(report, args.output_json)
    return 0 if report["ok"] else 2


def cmd_sync_assets(args: argparse.Namespace) -> int:
    manifest_script = resolve_visual_asset_library_script()
    command = [
        sys.executable,
        str(manifest_script),
        "--workspace",
        str(args.workspace.expanduser().resolve()),
        "--asset-root",
        str(args.asset_root.expanduser().resolve()),
    ]
    if args.manifest:
        command.extend(("--manifest", str(args.manifest)))
    if args.quick:
        command.append("--quick")
    if args.checksum:
        command.append("--checksum")
    if args.force:
        command.append("--force")
    result = run_command(command, capture=False, check=False)
    return result.returncode


def parse_noise_levels(raw: str) -> list[str]:
    levels = [item.strip() for item in raw.split(",") if item.strip()]
    if not levels:
        raise PipelineError("At least one noise threshold is required")
    return list(dict.fromkeys(levels))


def parse_silence_ranges(log: str) -> list[dict[str, float]]:
    starts = [float(x) for x in re.findall(r"silence_start:\s*([0-9.]+)", log)]
    ends = [
        (float(end), float(duration))
        for end, duration in re.findall(
            r"silence_end:\s*([0-9.]+)\s*\|\s*silence_duration:\s*([0-9.]+)", log
        )
    ]
    detected: list[dict[str, float]] = []
    for index, start in enumerate(starts):
        if index >= len(ends):
            break
        end, duration = ends[index]
        detected.append({"start": start, "end": end, "duration": duration})
    return detected


def run_silence_detect(source: Path, noise: str, minimum: float) -> list[dict[str, float]]:
    result = run_command(
        [
            "ffmpeg",
            "-hide_banner",
            "-nostats",
            "-i",
            str(source),
            "-af",
            f"silencedetect=noise={noise}:d={minimum}",
            "-f",
            "null",
            "-",
        ],
        check=False,
    )
    return parse_silence_ranges((result.stderr or "") + "\n" + (result.stdout or ""))


def whisper_word_timestamps(
    source: Path,
    model: str,
    language: str,
    *,
    required: bool = False,
) -> tuple[list[dict[str, Any]], str | None]:
    """Run the local Whisper CLI and return its actual word-level timings."""
    executable = shutil.which("whisper")
    if not executable:
        message = "Whisper CLI not found; word-level timestamps are required for caller-supplied scripts."
        if required:
            raise PipelineError(message)
        return [], "Whisper CLI not found; word-level pause candidates were skipped."
    with tempfile.TemporaryDirectory(prefix="soda_whisper_") as temp_dir:
        result = run_command(
            [
                executable,
                str(source),
                "--model",
                model,
                "--language",
                language,
                "--task",
                "transcribe",
                "--output_dir",
                temp_dir,
                "--output_format",
                "json",
                "--word_timestamps",
                "True",
                "--fp16",
                "False",
                "--verbose",
                "False",
            ],
            check=False,
        )
        json_files = sorted(Path(temp_dir).glob("*.json"))
        if result.returncode != 0 or not json_files:
            detail = (result.stderr or result.stdout or "unknown error").strip()
            message = f"Whisper word timestamps failed: {detail[:240]}"
            if required:
                raise PipelineError(message)
            return [], f"{message}; continuing without them."
        try:
            data = json.loads(json_files[0].read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            message = f"Whisper JSON could not be read: {exc}"
            if required:
                raise PipelineError(message)
            return [], f"{message}; continuing without it."

    words: list[dict[str, float | str]] = []
    for segment in data.get("segments", []):
        for word in segment.get("words", []):
            if word.get("start") is None or word.get("end") is None:
                continue
            words.append(
                {
                    "start": float(word["start"]),
                    "end": float(word["end"]),
                    "word": str(word.get("word", "")).strip(),
                }
            )
    if not words:
        message = "Whisper returned no word-level timestamps."
        if required:
            raise PipelineError(message)
        return [], f"{message}; continuing without them."
    return words, None


def whisper_word_gaps(
    source: Path,
    model: str,
    language: str,
    minimum: float,
    maximum: float,
) -> tuple[list[dict[str, Any]], str | None]:
    words, warning = whisper_word_timestamps(source, model, language)
    if warning:
        return [], warning
    gaps: list[dict[str, Any]] = []
    for previous, current in zip(words, words[1:]):
        gap = float(current["start"]) - float(previous["end"])
        if minimum <= gap <= maximum:
            gaps.append(
                {
                    "start": float(previous["end"]),
                    "end": float(current["start"]),
                    "duration": gap,
                    "previous_word": previous["word"],
                    "next_word": current["word"],
                    "source": "whisper",
                }
            )
    return gaps, None


def cluster_pause_candidates(
    threshold_ranges: list[dict[str, Any]],
    word_gaps: list[dict[str, Any]],
    keep_pause: float,
    tolerance: float,
    min_remove: float,
) -> list[dict[str, Any]]:
    raw = threshold_ranges + word_gaps
    raw.sort(key=lambda item: (float(item["start"]) + float(item["end"])) / 2.0)
    clusters: list[list[dict[str, Any]]] = []
    for item in raw:
        center = (float(item["start"]) + float(item["end"])) / 2.0
        if not clusters:
            clusters.append([item])
            continue
        previous = clusters[-1][-1]
        previous_center = (float(previous["start"]) + float(previous["end"])) / 2.0
        if center - previous_center <= tolerance:
            clusters[-1].append(item)
        else:
            clusters.append([item])

    stable: list[dict[str, Any]] = []
    for cluster in clusters:
        threshold_items = [item for item in cluster if item.get("source", "").startswith("threshold:")]
        whisper_items = [item for item in cluster if item.get("source") == "whisper"]
        threshold_names = sorted({str(item["source"]) for item in threshold_items})
        if len(threshold_names) < 2 and not (threshold_names and whisper_items):
            continue
        start = statistics.median([float(item["start"]) for item in cluster])
        end = statistics.median([float(item["end"]) for item in cluster])
        duration = max(0.0, end - start)
        preserved = min(keep_pause, duration)
        remove_start = start + preserved / 2.0
        remove_end = end - preserved / 2.0
        removable = remove_end - remove_start >= min_remove
        stable.append(
            {
                "start": round(start, 4),
                "end": round(end, 4),
                "duration": round(duration, 4),
                "threshold_agreement": len(threshold_names),
                "whisper_agreement": bool(whisper_items),
                "sources": threshold_names + (["whisper"] if whisper_items else []),
                "recommended_for_removal": removable,
                "remove_range": [round(remove_start, 4), round(remove_end, 4)] if removable else None,
            }
        )
    return stable


def cmd_detect_pauses(args: argparse.Namespace) -> int:
    require_binary("ffmpeg")
    source = args.input.expanduser().resolve()
    if not source.exists():
        raise PipelineError(f"Input not found: {source}")
    keep_pause = float(args.keep_pause)
    if not 0.12 <= keep_pause <= 0.20:
        raise PipelineError("keep-pause must be between 0.12 and 0.20 seconds")
    thresholds = parse_noise_levels(args.thresholds)
    threshold_reports: list[dict[str, Any]] = []
    threshold_ranges: list[dict[str, Any]] = []
    for index, noise in enumerate(thresholds):
        minimum = args.min_silence if index == 0 else args.dynamic_min_silence
        ranges = run_silence_detect(source, noise, minimum)
        threshold_reports.append(
            {
                "noise": noise,
                "minimum_silence_seconds": minimum,
                "detected_silences": ranges,
            }
        )
        threshold_ranges.extend({**item, "source": f"threshold:{noise}"} for item in ranges)

    word_gaps: list[dict[str, Any]] = []
    warnings: list[str] = []
    whisper_used = False
    if not args.no_whisper:
        word_gaps, whisper_warning = whisper_word_gaps(
            source,
            args.whisper_model,
            args.whisper_language,
            args.word_gap_min,
            args.word_gap_max,
        )
        if whisper_warning:
            warnings.append(whisper_warning)
        else:
            whisper_used = True
    stable = cluster_pause_candidates(
        threshold_ranges,
        word_gaps,
        keep_pause,
        args.cluster_tolerance,
        args.min_remove,
    )
    report = {
        "input": str(source),
        "detection_mode": "multi-threshold-cross-check",
        "thresholds": threshold_reports,
        "word_timestamp_tool": "whisper" if whisper_used else None,
        "whisper_model": args.whisper_model if whisper_used else None,
        "whisper_language": args.whisper_language if whisper_used else None,
        "word_gap_min_seconds": args.word_gap_min,
        "word_gap_max_seconds": args.word_gap_max,
        "word_timestamp_gaps": word_gaps,
        "cluster_tolerance_seconds": args.cluster_tolerance,
        "minimum_removal_seconds": args.min_remove,
        "preserved_pause_seconds": keep_pause,
        "stable_candidates": stable,
        "stable_candidate_count": len(stable),
        "remove_ranges": [item["remove_range"] for item in stable if item["remove_range"]],
        "recommended_removal_count": sum(1 for item in stable if item["remove_range"]),
        "review_required": True,
        "warnings": warnings,
        "warning": "Candidates require human review of wording, waveform, breaths, consonants, mouth movement, and gesture continuity before trimming.",
    }
    write_json(report, args.output_json)
    return 0


def normalize_ranges(raw: Any) -> list[tuple[float, float]]:
    values = raw.get("remove_ranges", []) if isinstance(raw, dict) else raw
    if not isinstance(values, list):
        raise PipelineError("Ranges JSON must be a list or an object containing remove_ranges")
    parsed: list[tuple[float, float]] = []
    for value in values:
        if isinstance(value, dict):
            start, end = value.get("start"), value.get("end")
        else:
            start, end = value
        start_value, end_value = float(start), float(end)
        if end_value <= start_value:
            continue
        parsed.append((max(0.0, start_value), end_value))
    parsed.sort()
    merged: list[tuple[float, float]] = []
    for start, end in parsed:
        if not merged or start > merged[-1][1]:
            merged.append((start, end))
        else:
            merged[-1] = (merged[-1][0], max(merged[-1][1], end))
    return merged


def keep_ranges(duration: float, removed: Iterable[tuple[float, float]]) -> list[tuple[float, float]]:
    cursor = 0.0
    result: list[tuple[float, float]] = []
    for start, end in removed:
        start = min(max(0.0, start), duration)
        end = min(max(0.0, end), duration)
        if start - cursor > 0.02:
            result.append((cursor, start))
        cursor = max(cursor, end)
    if duration - cursor > 0.02:
        result.append((cursor, duration))
    return result


def cmd_trim_pauses(args: argparse.Namespace) -> int:
    require_binary("ffmpeg")
    source = args.input.expanduser().resolve()
    output = args.output.expanduser().resolve()
    ranges_path = args.ranges_json.expanduser().resolve()
    if not ranges_path.exists():
        raise PipelineError(f"Ranges JSON not found: {ranges_path}")
    removed = normalize_ranges(json.loads(ranges_path.read_text(encoding="utf-8")))
    summary = media_summary(source)
    duration = float(summary["duration"])
    kept = keep_ranges(duration, removed)
    if not kept:
        raise PipelineError("No video remains after applying ranges")

    filters: list[str] = []
    concat_inputs: list[str] = []
    for index, (start, end) in enumerate(kept):
        filters.append(
            f"[0:v]trim=start={start:.6f}:end={end:.6f},setpts=PTS-STARTPTS[v{index}]"
        )
        filters.append(
            f"[0:a]atrim=start={start:.6f}:end={end:.6f},asetpts=PTS-STARTPTS[a{index}]"
        )
        concat_inputs.extend((f"[v{index}]", f"[a{index}]"))
    filters.append(
        "".join(concat_inputs) + f"concat=n={len(kept)}:v=1:a=1[vout][aout]"
    )
    output.parent.mkdir(parents=True, exist_ok=True)
    command = [
        "ffmpeg",
        "-hide_banner",
        "-y",
        "-i",
        str(source),
        "-filter_complex",
        ";".join(filters),
        "-map",
        "[vout]",
        "-map",
        "[aout]",
        "-c:v",
        "libx264",
        "-preset",
        "medium",
        "-crf",
        "18",
        "-pix_fmt",
        "yuv420p",
        "-c:a",
        "aac",
        "-b:a",
        "192k",
        "-movflags",
        "+faststart",
        str(output),
    ]
    if args.dry_run:
        write_json(
            {
                "input": str(source),
                "output": str(output),
                "removed_ranges": removed,
                "keep_ranges": kept,
                "command": command,
            },
            args.output_json,
        )
        return 0
    run_command(command, capture=False)
    report = {
        "input": str(source),
        "output": str(output),
        "removed_ranges": removed,
        "keep_ranges": kept,
        "before": summary,
        "after": media_summary(output),
    }
    write_json(report, args.output_json)
    return 0


def read_script_text(paths: list[Path] | None, inline_text: list[str] | None) -> str:
    parts: list[str] = []
    for path in paths or []:
        resolved = path.expanduser().resolve()
        if not resolved.exists():
            raise PipelineError(f"Script file not found: {resolved}")
        parts.append(resolved.read_text(encoding="utf-8", errors="ignore"))
    parts.extend(inline_text or [])
    return "\n".join(parts).strip()


DECIMAL_POINT_CHARS = {".", "．"}


def is_numeric_decimal_point(text: str, index: int) -> bool:
    """Return True for a decimal point surrounded by decimal digits."""
    return (
        0 < index < len(text) - 1
        and text[index] in DECIMAL_POINT_CHARS
        and text[index - 1].isdigit()
        and text[index + 1].isdigit()
    )


def normalize_subtitle_text(text: str) -> str:
    """Remove prose punctuation while preserving semantic decimal points."""
    normalized_lines: list[str] = []
    for raw_line in str(text).replace("\r\n", "\n").replace("\r", "\n").split("\n"):
        chars: list[str] = []
        for index, char in enumerate(raw_line):
            if is_numeric_decimal_point(raw_line, index):
                chars.append(".")
            elif unicodedata.category(char).startswith("P"):
                chars.append(" ")
            else:
                chars.append(char)
        line = re.sub(r"[ \t]+", " ", "".join(chars)).strip()
        if line:
            normalized_lines.append(line)
    return "\n".join(normalized_lines)


def _alignment_units(text: str) -> list[str]:
    """Split Chinese into characters while keeping latin/number runs intact."""
    units: list[str] = []
    buffer: list[str] = []

    def flush() -> None:
        if buffer:
            units.append("".join(buffer).casefold())
            buffer.clear()

    for char in str(text):
        category = unicodedata.category(char)
        if char.isspace() or category.startswith("P"):
            flush()
            continue
        is_cjk = "\u3400" <= char <= "\u9fff" or "\uf900" <= char <= "\ufaff"
        if is_cjk:
            flush()
            units.append(char.casefold())
        elif char.isalnum() or char == "_":
            buffer.append(char)
        else:
            flush()
            units.append(char.casefold())
    flush()
    return units


def split_spoken_script_phrases(text: str) -> list[str]:
    """Treat model-inserted line breaks as authoritative caption event boundaries."""

    return [
        value
        for raw_line in str(text).replace("\r\n", "\n").replace("\r", "\n").split("\n")
        if (value := normalize_subtitle_text(raw_line))
    ]


def align_script_to_whisper_words(
    script_text: str,
    words: list[dict[str, Any]],
    source_duration: float,
    *,
    caption_style: dict[str, Any] | None = None,
    canvas_width: int = 1080,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Map model-provided semantic caption lines to actual Whisper word times."""
    phrases = split_spoken_script_phrases(script_text)
    style = caption_style or {}
    try:
        character_budget = derive_caption_character_budget(style, canvas_width)
    except CaptionLayoutError as exc:
        raise PipelineError(f"Unable to derive caption character budget: {exc}") from exc
    maximum_characters = int(character_budget["max_characters_per_line"])
    segment_character_counts = [count_caption_characters(phrase) for phrase in phrases]
    oversized = [
        (index, phrase, count)
        for index, (phrase, count) in enumerate(zip(phrases, segment_character_counts))
        if count > maximum_characters
    ]
    if oversized:
        detail = "; ".join(
            f"segment {index} has {count} characters: {phrase!r}"
            for index, phrase, count in oversized
        )
        raise PipelineError(
            "Spoken script requires model semantic line breaks before Whisper mapping; "
            f"the task-level limit is {maximum_characters} characters per line. {detail}. "
            "Insert line breaks at complete semantic boundaries without changing the wording."
        )
    phrase_units = [_alignment_units(phrase) for phrase in phrases]
    script_units = [unit for group in phrase_units for unit in group]
    if not script_units:
        raise PipelineError("The supplied spoken script is empty after punctuation normalization")
    if not words:
        raise PipelineError("Whisper returned no word-level timestamps for the supplied script")

    whisper_units: list[str] = []
    whisper_unit_word_indices: list[int] = []
    whisper_unit_ranges: list[tuple[float, float]] = []
    for word_index, word in enumerate(words):
        units = _alignment_units(str(word.get("word", "")))
        word_start = float(word["start"])
        word_end = float(word["end"])
        word_duration = max(0.0, word_end - word_start)
        for unit_index, unit in enumerate(units):
            whisper_units.append(unit)
            whisper_unit_word_indices.append(word_index)
            unit_start = word_start + word_duration * unit_index / max(1, len(units))
            unit_end = word_start + word_duration * (unit_index + 1) / max(1, len(units))
            whisper_unit_ranges.append((unit_start, unit_end))
    if not whisper_units:
        raise PipelineError("Whisper returned word timestamps without usable word text")

    script_times: list[tuple[float, float] | None] = [None] * len(script_units)
    matcher = difflib.SequenceMatcher(None, script_units, whisper_units, autojunk=False)
    fallback_duration = min(0.24, max(0.08, source_duration / max(1, len(words)) * 1.5))
    exact_match_units = 0

    def assign_range(script_start: int, script_end: int, whisper_start: int, whisper_end: int) -> None:
        if script_start >= script_end:
            return
        whisper_ranges = whisper_unit_ranges[whisper_start:whisper_end]
        if whisper_ranges:
            for offset, script_index in enumerate(range(script_start, script_end)):
                mapped_offset = min(
                    len(whisper_ranges) - 1,
                    math.floor(offset * len(whisper_ranges) / max(1, script_end - script_start)),
                )
                script_times[script_index] = whisper_ranges[mapped_offset]
            return

        previous_range = whisper_unit_ranges[whisper_start - 1] if whisper_start > 0 else None
        next_range = whisper_unit_ranges[whisper_start] if whisper_start < len(whisper_unit_ranges) else None
        if previous_range is not None and next_range is not None:
            start = previous_range[1]
            end = next_range[0]
            if end <= start:
                start, end = previous_range
        elif previous_range is not None:
            start = previous_range[1]
            end = start + fallback_duration
        elif next_range is not None:
            end = next_range[0]
            start = max(0.0, end - fallback_duration)
        else:
            start, end = 0.0, fallback_duration
        for script_index in range(script_start, script_end):
            script_times[script_index] = (start, end)

    for tag, script_start, script_end, whisper_start, whisper_end in matcher.get_opcodes():
        if tag == "equal":
            exact_match_units += script_end - script_start
        if tag in {"equal", "replace", "delete"}:
            assign_range(script_start, script_end, whisper_start, whisper_end)

    # Fill any residual unmatched units from the nearest actual Whisper slot.
    for index, value in enumerate(script_times):
        if value is not None:
            continue
        previous = next((script_times[pos] for pos in range(index - 1, -1, -1) if script_times[pos]), None)
        following = next((script_times[pos] for pos in range(index + 1, len(script_times)) if script_times[pos]), None)
        if previous and following:
            script_times[index] = (previous[1], following[0]) if following[0] > previous[1] else previous
        elif previous:
            script_times[index] = (previous[1], previous[1] + fallback_duration)
        elif following:
            script_times[index] = (max(0.0, following[0] - fallback_duration), following[0])
        else:
            script_times[index] = (0.0, fallback_duration)

    captions: list[dict[str, Any]] = []
    cursor = 0
    previous_end = 0.0
    for phrase, units in zip(phrases, phrase_units):
        count = len(units)
        if not count:
            continue
        normalized_phrase = normalize_subtitle_text(phrase)
        chunks = [normalized_phrase]
        chunk_counts = [count]
        phrase_cursor = cursor
        cursor += count
        for chunk, chunk_count in zip(chunks, chunk_counts):
            ranges = [
                script_times[phrase_cursor + offset]
                for offset in range(chunk_count)
            ]
            phrase_cursor += chunk_count
            actual_ranges = [item for item in ranges if item is not None]
            if not actual_ranges:
                continue
            start = max(0.0, min(item[0] for item in actual_ranges))
            end = min(source_duration, max(item[1] for item in actual_ranges))
            if end <= start:
                end = min(source_duration, start + fallback_duration)
            if start < previous_end:
                start = previous_end
                end = max(end, start + fallback_duration)
            end = min(max(start, end), source_duration)
            if end <= start:
                continue
            captions.append(
                {
                    "start": round(start, 4),
                    "end": round(end, 4),
                    "text": chunk,
                    "time_mode": "input",
                    "timing_source": "whisper_word_timestamps",
                }
            )
            previous_end = end

    if not captions:
        raise PipelineError("Whisper word timestamps could not be mapped to the supplied script")
    report = {
        "timing_source": "whisper_word_timestamps",
        "whisper_word_count": len(words),
        "whisper_unit_count": len(whisper_units),
        "script_unit_count": len(script_units),
        "exactly_matched_script_unit_count": exact_match_units,
        "alignment_ratio": round(exact_match_units / max(1, len(script_units)), 4),
        "caption_count": len(captions),
        "caption_time_mode": "input",
        "caption_segmentation_source": "executor_model_semantic_lines",
        "semantic_segment_count": len(phrases),
        "semantic_segments": [
            {
                "text": phrase,
                "character_count": count,
            }
            for phrase, count in zip(phrases, segment_character_counts)
        ],
        "caption_character_budget": character_budget,
        "automatic_width_split_count": 0,
        "caption_visual_timing_policy": "one model semantic line maps to one actual Whisper-timed caption event",
    }
    return captions, report


def repair_timeline_captions(
    config: dict[str, Any],
    script_text: str,
    *,
    input_path: Path,
    whisper_model: str = "tiny",
    whisper_language: str = "zh",
) -> tuple[dict[str, Any], dict[str, Any]]:
    captions = config.get("captions", [])
    if not isinstance(captions, list):
        raise PipelineError("Timeline captions must be a list")
    source = input_path.expanduser().resolve()
    if not source.exists():
        raise PipelineError(f"Input not found for Whisper subtitle timing: {source}")
    source_duration = float(media_summary(source)["duration"])
    words, _warning = whisper_word_timestamps(
        source,
        whisper_model,
        whisper_language,
        required=True,
    )
    generated_captions, alignment_report = align_script_to_whisper_words(
        script_text,
        words,
        source_duration,
        caption_style=config.get("font", {}).get("caption_style", {}),
        canvas_width=int(config.get("width", 1080)),
    )
    repaired_config = dict(config)
    repaired_config["time_mode"] = "input"
    repaired_config["captions"] = generated_captions
    report = {
        "source": "caller_spoken_script",
        "input": str(source),
        "whisper_model": whisper_model,
        "whisper_language": whisper_language,
        "whisper_word_timestamps": True,
        "word_timestamps": words,
        "subtitle_timing_policy": "fill_caller_script_into_actual_whisper_word_timestamps",
        "timeline_time_mode": "input",
        "material_timing_policy": "retime every material directly to Whisper input caption boundaries before render",
        "material_retiming_required": bool(config.get("materials")),
        "subtitle_punctuation_policy": "remove_prose_punctuation_preserve_numeric_decimal_points",
        "original_caption_count": len(captions),
        "normalized_script": "\n".join(split_spoken_script_phrases(script_text)),
        **alignment_report,
    }
    return repaired_config, report


def prepare_repaired_timeline(args: argparse.Namespace) -> dict[str, Any] | None:
    """Use caller narration as text, but take all caption timing from Whisper on the render input."""
    if not getattr(args, "script_file", None) and not getattr(args, "text", None):
        return None
    script_text = read_script_text(args.script_file, args.text)
    if not script_text:
        return None
    source_timeline = load_timeline_config(args.timeline_json)
    repaired_config, report = repair_timeline_captions(
        source_timeline,
        script_text,
        input_path=args.input,
        whisper_model=getattr(args, "whisper_model", "tiny"),
        whisper_language=getattr(args, "whisper_language", "zh"),
    )
    output_path = args.output.expanduser().resolve()
    repaired_path = getattr(args, "repaired_timeline_json", None)
    if repaired_path is None:
        repaired_path = output_path.with_name(output_path.stem + "_repaired_timeline.json")
    repair_report_path = getattr(args, "subtitle_repair_report", None)
    if repair_report_path is None:
        repair_report_path = output_path.with_name(output_path.stem + "_subtitle_repair.json")
    write_json(repaired_config, repaired_path)
    report["source_timeline"] = str(args.timeline_json.expanduser().resolve())
    report["repaired_timeline"] = str(Path(repaired_path).expanduser().resolve())
    write_json(report, repair_report_path)
    args.timeline_json = Path(repaired_path)
    return report


def cmd_repair_captions(args: argparse.Namespace) -> int:
    script_text = read_script_text(args.script_file, args.text)
    if not script_text:
        raise PipelineError("repair-captions requires --script-file or --text")
    config = load_timeline_config(args.timeline_json)
    repaired_config, report = repair_timeline_captions(
        config,
        script_text,
        input_path=args.input,
        whisper_model=args.whisper_model,
        whisper_language=args.whisper_language,
    )
    report["source_timeline"] = str(args.timeline_json.expanduser().resolve())
    report["repaired_timeline"] = str(args.output_timeline_json.expanduser().resolve())
    write_json(repaired_config, args.output_timeline_json)
    write_json(report, args.output_json)
    return 0


def validate_rules(args: argparse.Namespace) -> dict[str, Any]:
    text = read_script_text(args.script_file, args.text)
    duration: float | None = args.duration
    if args.video:
        duration = media_summary(args.video)["duration"]

    errors: list[str] = []
    warnings: list[str] = []
    passed: list[str] = []

    if duration is not None:
        passed.append(f"成片时长 {duration:.3f}s 由实际数字人口播决定，不设置最低时长。")

    if not text:
        warnings.append("未提供脚本/字幕文本，禁词和利益点规则未完成扫描。")
    else:
        lowered = text.lower()
        for term in GLOBAL_BANNED_TERMS:
            if term == "emo":
                matched = bool(re.search(r"(?<![A-Za-z])emo(?![A-Za-z])", lowered))
            else:
                matched = term.lower() in lowered
            if matched:
                errors.append(f"脚本包含禁用词：{term}")
        for term in LIVING_COST_TERMS:
            if term in text:
                errors.append(f"脚本包含禁止的生活成本承诺：{term}")
        if "箭头" in text or any(value in text for value in ARROW_CHARS):
            errors.append("脚本/画面说明包含箭头表达；成片禁止使用箭头图标。")
        third_party_hits = [term for term in THIRD_PARTY_TERMS if term in text]
        if third_party_hits and not args.allow_third_party:
            errors.append(
                "出现未经授权的第三方名称：" + "、".join(third_party_hits)
            )
        elif third_party_hits:
            warnings.append(
                "第三方名称已通过显式允许开关：" + "、".join(third_party_hits) + "；仍需保留书面审查记录。"
            )

        if args.channel == "new-high-mid" and "听歌赚钱" in text:
            errors.append("金币音乐新/high/mid 禁止出现“听歌赚钱”。")
        if args.channel == "free-listen" and any(term in text for term in ("赚钱", "赚金币")):
            errors.append("免费听类型禁止出现赚钱、赚金币等利益点。")

    if args.has_playlist and not args.song_review_passed:
        errors.append("包含歌单但未确认禁投审查通过。")
    if not args.has_playlist and args.song_review_passed:
        warnings.append("已标记歌曲审查通过，但当前未标记歌单段落。")

    amount = args.amount_yuan
    if args.channel == "old-down" and amount is not None:
        if 10 < amount < 100:
            passed.append("金币音乐旧/下沉金额处于大于 10 元且小于 100 元的范围。")
        elif args.small_amount_context and 0 <= amount <= 10:
            warnings.append("旧/下沉使用小额截图，仅限下载前或三毛、五毛等明确小额语境。")
        else:
            errors.append("金币音乐旧/下沉默认金额必须大于 10 元且小于 100 元。")
    elif args.channel == "new-high-mid" and amount is not None and amount >= 10:
        errors.append("金币音乐新/high/mid 必须使用小于 10 元的小额截图。")
    elif args.channel == "coin-non-down":
        if amount is not None and amount >= 10:
            errors.append("金币非下沉不能出现大额。")
        if args.has_playlist:
            errors.append("金币非下沉不用加歌单。")

    if args.coin_amount is not None and args.coin_amount >= 50000:
        errors.append("金币到账描述必须小于 5 万金币。")

    if args.channel == "general":
        warnings.append("general 仅用于无法归类时的预检；正式制作前仍必须确定渠道类型。")

    if not errors:
        passed.append("当前提供的信息未触发已编码的文案和渠道红线。")
    return {
        "ok": not errors,
        "channel": args.channel,
        "duration": duration,
        "duration_policy": "source-driven-no-minimum",
        "has_playlist": args.has_playlist,
        "song_review_passed": args.song_review_passed,
        "allow_third_party": args.allow_third_party,
        "amount_yuan": amount,
        "coin_amount": args.coin_amount,
        "errors": errors,
        "warnings": warnings,
        "passed": passed,
    }


def cmd_validate_rules(args: argparse.Namespace) -> int:
    report = validate_rules(args)
    write_json(report, args.output_json)
    return 0 if report["ok"] else 2


def cmd_render(args: argparse.Namespace) -> int:
    # Resolve the manifest before prepare_repaired_timeline changes the timeline path
    # to an output-directory copy.
    args.asset_manifest = resolve_asset_manifest_path(
        args.timeline_json,
        getattr(args, "asset_manifest", None),
    )
    subtitle_repair = prepare_repaired_timeline(args)
    if subtitle_repair:
        print(json.dumps({"subtitle_repair": subtitle_repair}, ensure_ascii=False, indent=2))
    args.speed = validate_speed(args.speed)
    args.bgm_target_lufs, args.bgm_volume = validate_bgm_settings(
        args.bgm_target_lufs, args.bgm_volume
    )
    if args.duration is None and args.video is None:
        args.duration = estimate_render_duration(
            args.input, args.timeline_json, args.asset_root, speed_override=args.speed
        )
    compliance = validate_rules(args)
    if not compliance["ok"]:
        write_json(compliance, args.compliance_report)
        return 2
    if args.compliance_report:
        args.compliance_report.expanduser().resolve().parent.mkdir(parents=True, exist_ok=True)
        args.compliance_report.expanduser().resolve().write_text(
            json.dumps(compliance, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )

    preflight = preflight_report(args)
    if not preflight["ok"]:
        write_json(preflight, args.preflight_report)
        return 2
    if args.preflight_report:
        args.preflight_report.expanduser().resolve().parent.mkdir(parents=True, exist_ok=True)
        args.preflight_report.expanduser().resolve().write_text(
            json.dumps(preflight, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )

    renderer = DEFAULT_RENDERER.resolve()
    input_path = args.input.expanduser().resolve()
    bgm_path = args.bgm.expanduser().resolve()
    output_path = args.output.expanduser().resolve()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    command = [
        sys.executable,
        str(renderer),
        "--input",
        str(input_path),
        "--asset-root",
        str(args.asset_root.expanduser().resolve()),
        "--asset-manifest",
        str(args.asset_manifest.expanduser().resolve()),
        "--bgm",
        str(bgm_path),
        "--timeline-json",
        str(args.timeline_json.expanduser().resolve()),
        "--output",
        str(output_path),
        "--bgm-target-lufs",
        str(args.bgm_target_lufs),
        "--bgm-volume",
        str(args.bgm_volume),
        "--logo-variant",
        args.logo_variant,
        "--speed",
        str(args.speed),
    ]
    if args.channel in ("old-down", "new-high-mid", "coin-non-down"):
        command.append("--show-warning")
    if args.dry_run:
        command.append("--dry-run")
    if args.motion_effects is not None:
        command.extend(["--motion-effects", args.motion_effects])
    if args.motion_seed is not None:
        command.extend(["--motion-seed", str(args.motion_seed)])
    print(json.dumps({"render_command": command}, ensure_ascii=False, indent=2))
    result = run_command(command, capture=False, check=False)
    if result.returncode != 0:
        return result.returncode
    if args.dry_run:
        return 0

    qa_args = argparse.Namespace(
        input=output_path,
        output_json=args.qa_report,
        expected_width=1080,
        expected_height=1920,
        expected_fps=30.0,
        quick=args.quick_qa,
    )
    return cmd_qa(qa_args)


def measure_loudness(path: Path) -> dict[str, float | None]:
    result = run_command(
        [
            "ffmpeg",
            "-hide_banner",
            "-nostats",
            "-i",
            str(path),
            "-filter_complex",
            "ebur128=peak=true",
            "-f",
            "null",
            "-",
        ],
        check=False,
    )
    log = (result.stderr or "") + "\n" + (result.stdout or "")
    integrated_values = re.findall(r"\bI:\s*(-?[0-9.]+)\s*LUFS", log)
    peak_values = re.findall(r"\bPeak:\s*(-?[0-9.]+)\s*dBFS", log)
    return {
        "integrated_lufs": float(integrated_values[-1]) if integrated_values else None,
        "true_peak_dbfs": float(peak_values[-1]) if peak_values else None,
    }


def cmd_qa(args: argparse.Namespace) -> int:
    require_binary("ffmpeg")
    source = args.input.expanduser().resolve()
    summary = media_summary(source)
    errors: list[str] = []
    warnings: list[str] = []

    if summary["width"] != args.expected_width or summary["height"] != args.expected_height:
        errors.append(
            f"分辨率为 {summary['width']}×{summary['height']}，期望 {args.expected_width}×{args.expected_height}。"
        )
    fps = float(summary["fps"] or 0.0)
    if not math.isclose(fps, args.expected_fps, rel_tol=0.0, abs_tol=0.05):
        errors.append(f"帧率为 {fps:.3f}，期望 {args.expected_fps:.3f}。")
    if summary["video_codec"] != "h264":
        errors.append(f"视频编码为 {summary['video_codec']}，期望 h264。")
    if summary["audio_codec"] != "aac":
        errors.append(f"音频编码为 {summary['audio_codec']}，期望 aac。")
    decode_ok: bool | None = None
    loudness: dict[str, float | None] | None = None
    if args.quick:
        warnings.append("quick QA 未执行完整解码和响度扫描。")
    else:
        decode = run_command(
            ["ffmpeg", "-v", "error", "-i", str(source), "-map", "0:v:0", "-map", "0:a:0?", "-f", "null", "-"],
            check=False,
        )
        decode_ok = decode.returncode == 0 and not (decode.stderr or "").strip()
        if not decode_ok:
            errors.append("完整解码检查失败：" + (decode.stderr or "unknown error").strip())
        loudness = measure_loudness(source)
        integrated = loudness.get("integrated_lufs")
        peak = loudness.get("true_peak_dbfs")
        if integrated is None:
            warnings.append("未能解析综合响度。")
        elif not -17.0 <= integrated <= -15.0:
            warnings.append(f"综合响度 {integrated:.2f} LUFS 超出建议的 -16±1 LUFS。")
        if peak is None:
            warnings.append("未能解析峰值。")
        elif peak > -1.0:
            warnings.append(f"峰值 {peak:.2f} dBFS 高于建议的 -1.0 dBFS。")

    report = {
        "ok": not errors,
        "file": str(source),
        "summary": summary,
        "decode_ok": decode_ok,
        "loudness": loudness,
        "errors": errors,
        "warnings": warnings,
        "manual_checks_required": [
            "逐帧确认无黑屏、绿屏、冻帧、残帧和多 logo 叠加。",
            "确认字幕、安全区、警示语、歌曲审查和素材合规。",
            "确认素材没有进入左上 logo 区域和底部警示语区域；字幕位于所有素材上方，logo 位于素材、字幕和 CTA 上方，警示语为最终最高层；字幕黑色细描边为 2-3px、阴影为 0，且不存在背景黑条、黑框或半透明黑色承托层。",
            "使用耳机和手机扬声器复听，确认 BGM 不过小且不盖住人声。",
        ],
    }
    write_json(report, args.output_json)
    return 0 if report["ok"] else 2


def add_common_rule_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--channel", choices=CHANNELS, required=True)
    parser.add_argument(
        "--script-file",
        type=Path,
        action="append",
        help="Model-segmented subtitle text with one semantic caption per line; render maps each line to mandatory Whisper word timestamps",
    )
    parser.add_argument("--text", action="append")
    parser.add_argument("--video", type=Path)
    parser.add_argument("--duration", type=float)
    parser.add_argument("--minimum-duration", type=float, help=argparse.SUPPRESS)
    parser.add_argument("--allow-short-demo", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--has-playlist", action="store_true")
    parser.add_argument("--song-review-passed", action="store_true")
    parser.add_argument("--allow-third-party", action="store_true")
    parser.add_argument("--amount-yuan", type=float)
    parser.add_argument("--coin-amount", type=float)
    parser.add_argument("--small-amount-context", action="store_true")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    sync_assets = sub.add_parser(
        "sync-assets",
        aliases=("load-assets",),
        help="Compatibility forwarder to manage-visual-asset-library asset synchronization",
    )
    sync_assets.add_argument("--workspace", type=Path, required=True)
    sync_assets.add_argument("--asset-root", type=Path, required=True)
    sync_assets.add_argument("--manifest", type=Path)
    sync_assets.add_argument("--quick", action="store_true")
    sync_assets.add_argument("--checksum", action="store_true")
    sync_assets.add_argument("--force", action="store_true")
    sync_assets.set_defaults(func=cmd_sync_assets)

    caption_budget = sub.add_parser(
        "caption-budget",
        help="Calculate one task-level semantic caption character limit from the active style",
    )
    caption_budget.add_argument("--timeline-json", type=Path, required=True)
    caption_budget.add_argument("--output-json", type=Path)
    caption_budget.set_defaults(func=cmd_caption_budget)

    preflight = sub.add_parser("preflight", help="Check FFmpeg, timeline, BGM, and required assets")
    preflight.add_argument("--asset-root", type=Path, required=True)
    preflight.add_argument(
        "--asset-manifest",
        type=Path,
        help="Synced visual_assets_manifest.json; legacy soda_assets_manifest.json remains accepted when passed explicitly",
    )
    preflight.add_argument("--bgm", type=Path, required=True)
    preflight.add_argument("--input", type=Path)
    preflight.add_argument("--timeline-json", type=Path, required=True)
    preflight.add_argument("--logo-variant", choices=("white", "black"), default="white")
    preflight.add_argument("--motion-effects", choices=("auto", "off", "required"))
    preflight.add_argument("--motion-seed")
    preflight.add_argument("--output-json", type=Path)
    preflight.set_defaults(func=cmd_preflight)

    detect = sub.add_parser(
        "detect-pauses",
        help="Cross-check multi-threshold silence and optional Whisper word gaps; never trims automatically",
    )
    detect.add_argument("--input", type=Path, required=True)
    detect.add_argument(
        "--thresholds",
        default="-35dB,-30dB,-25dB",
        help="Comma-separated strict-to-sensitive silencedetect thresholds",
    )
    detect.add_argument("--min-silence", type=float, default=0.35)
    detect.add_argument("--dynamic-min-silence", type=float, default=0.18)
    detect.add_argument("--keep-pause", type=float, default=0.16)
    detect.add_argument("--min-remove", type=float, default=0.08)
    detect.add_argument("--cluster-tolerance", type=float, default=0.30)
    detect.add_argument("--word-gap-min", type=float, default=0.18)
    detect.add_argument("--word-gap-max", type=float, default=1.80)
    detect.add_argument("--whisper-model", default="tiny")
    detect.add_argument("--whisper-language", default="zh")
    detect.add_argument("--no-whisper", action="store_true")
    detect.add_argument("--output-json", type=Path)
    detect.set_defaults(func=cmd_detect_pauses)

    trim = sub.add_parser("trim-pauses", help="Remove human-approved pause ranges")
    trim.add_argument("--input", type=Path, required=True)
    trim.add_argument("--ranges-json", type=Path, required=True)
    trim.add_argument("--output", type=Path, required=True)
    trim.add_argument("--output-json", type=Path)
    trim.add_argument("--dry-run", action="store_true")
    trim.set_defaults(func=cmd_trim_pauses)

    repair = sub.add_parser(
        "repair-captions",
        help="Map model-provided semantic caption lines to actual Whisper word timestamps",
    )
    repair.add_argument("--timeline-json", type=Path, required=True)
    repair.add_argument("--input", type=Path, required=True)
    repair.add_argument("--script-file", type=Path, action="append")
    repair.add_argument("--text", action="append")
    repair.add_argument("--whisper-model", default="tiny")
    repair.add_argument("--whisper-language", default="zh")
    repair.add_argument("--output-timeline-json", type=Path, required=True)
    repair.add_argument("--output-json", type=Path)
    repair.set_defaults(func=cmd_repair_captions)

    rules = sub.add_parser("validate-rules", help="Validate channel, wording, amount, and playlist rules")
    add_common_rule_arguments(rules)
    rules.add_argument("--output-json", type=Path)
    rules.set_defaults(func=cmd_validate_rules)

    render = sub.add_parser("render", help="Validate and call the bundled standalone FFmpeg renderer")
    add_common_rule_arguments(render)
    render.add_argument("--asset-root", type=Path, required=True)
    render.add_argument(
        "--asset-manifest",
        type=Path,
        help="Synced visual_assets_manifest.json; legacy soda_assets_manifest.json remains accepted when passed explicitly",
    )
    render.add_argument("--timeline-json", type=Path, required=True)
    render.add_argument("--logo-variant", choices=("white", "black"), default="white")
    render.add_argument("--input", type=Path, required=True)
    render.add_argument("--bgm", type=Path, required=True)
    render.add_argument("--output", type=Path, required=True)
    render.add_argument(
        "--speed",
        type=float,
        default=1.1,
        help="Playback speed applied after pause trimming; defaults to 1.1 and overrides timeline speed",
    )
    render.add_argument(
        "--bgm-target-lufs",
        type=float,
        default=DEFAULT_BGM_TARGET_LUFS,
        help="Target integrated loudness for BGM before fine gain; defaults to -28 LUFS",
    )
    render.add_argument(
        "--bgm-volume",
        type=float,
        default=DEFAULT_BGM_FINE_VOLUME,
        help="Post-normalization BGM fine gain, normally 1.0; valid range 0.5-1.5",
    )
    render.add_argument("--compliance-report", type=Path)
    render.add_argument("--preflight-report", type=Path)
    render.add_argument("--qa-report", type=Path)
    render.add_argument("--quick-qa", action="store_true")
    render.add_argument("--motion-effects", choices=("auto", "off", "required"))
    render.add_argument("--motion-seed")
    render.add_argument(
        "--whisper-model",
        default="tiny",
        help="Whisper model used for mandatory script timing; defaults to tiny",
    )
    render.add_argument(
        "--whisper-language",
        default="zh",
        help="Whisper language used for mandatory script timing; defaults to zh",
    )
    render.add_argument("--repaired-timeline-json", type=Path)
    render.add_argument("--subtitle-repair-report", type=Path)
    render.add_argument("--dry-run", action="store_true")
    render.set_defaults(func=cmd_render)

    qa = sub.add_parser("qa", help="Probe, decode, and loudness-check an output video")
    qa.add_argument("--input", type=Path, required=True)
    qa.add_argument("--output-json", type=Path)
    qa.add_argument("--expected-width", type=int, default=1080)
    qa.add_argument("--expected-height", type=int, default=1920)
    qa.add_argument("--expected-fps", type=float, default=30.0)
    qa.add_argument("--minimum-duration", type=float, help=argparse.SUPPRESS)
    qa.add_argument("--allow-short-demo", action="store_true", help=argparse.SUPPRESS)
    qa.add_argument("--quick", action="store_true")
    qa.set_defaults(func=cmd_qa)
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    try:
        return int(args.func(args))
    except (PipelineError, OSError, ValueError, json.JSONDecodeError) as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False, indent=2), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
