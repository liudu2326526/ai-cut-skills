#!/usr/bin/env python3
"""Standalone FFmpeg renderer for the Soda Music mixed-cut skill.

Requires only Python's standard library, ffmpeg, ffprobe, an input video, a
caller-supplied BGM file, asset directory, understood asset manifest, and timeline JSON file.
"""

from __future__ import annotations

import argparse
import json
import math
import re
import shutil
import subprocess
import sys
import tempfile
import unicodedata
from pathlib import Path
from typing import Any, Iterable

from motion_effects_bridge import (
    MotionEffectsError,
    apply_motion_overrides,
    plan_motion_effects,
    render_motion_effects,
)
from special_material_matches import special_match_metadata_errors


class RenderError(RuntimeError):
    pass


DEFAULT_BGM_TARGET_LUFS = -28.0
DEFAULT_BGM_FINE_VOLUME = 1.0


def validate_bgm_settings(target_lufs: float, fine_volume: float) -> tuple[float, float]:
    target = float(target_lufs)
    volume = float(fine_volume)
    if not -40.0 <= target <= -18.0:
        raise RenderError("bgm-target-lufs must be between -40 and -18 LUFS")
    if not 0.5 <= volume <= 1.5:
        raise RenderError(
            "bgm-volume is a post-normalization fine gain and must be between 0.5 and 1.5; use bgm-target-lufs for the main level"
        )
    return target, volume


def resolve_visual_policy(config: dict[str, Any]) -> dict[str, Any]:
    raw = config.get("visual_policy", {})
    if not isinstance(raw, dict):
        raise RenderError("visual_policy must be an object")
    source_check = str(raw.get("source_black_bar_check", "error"))
    safe_area_raw = raw.get("material_safe_area", {})
    if not isinstance(safe_area_raw, dict):
        raise RenderError("visual_policy.material_safe_area must be an object")
    try:
        safe_area = {
            "left": int(safe_area_raw.get("left", 48)),
            "right": int(safe_area_raw.get("right", 48)),
            "top": int(safe_area_raw.get("top", 320)),
            "bottom": int(safe_area_raw.get("bottom", 180)),
        }
    except (TypeError, ValueError) as exc:
        raise RenderError("visual_policy.material_safe_area margins must be integers") from exc
    if any(value < 0 for value in safe_area.values()):
        raise RenderError("visual_policy.material_safe_area margins must be non-negative")
    canvas_width = int(config.get("width", 1080))
    canvas_height = int(config.get("height", 1920))
    if (
        safe_area["left"] + safe_area["right"] >= canvas_width
        or safe_area["top"] + safe_area["bottom"] >= canvas_height
    ):
        raise RenderError("visual_policy.material_safe_area leaves no usable material area")
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
        )
    ) or source_check != "error" or policy["caption_outline_policy"] != "thin_black_2_3px":
        raise RenderError(
            "visual policy is mandatory: generated/caption/material backplates must be forbidden, caption_outline_policy must be thin_black_2_3px, logo and warning must be top layers, material matching must be limited to benefit points, material safe area must be enforced, material size must be preserved before fitting to the largest brand-safe size, and source_black_bar_check must be error"
        )
    return policy


def require_binary(name: str) -> str:
    value = shutil.which(name)
    if not value:
        raise RenderError(f"Required binary not found: {name}")
    return value


def run(command: list[str], *, label: str) -> None:
    print(f"[{label}] {' '.join(command)}")
    result = subprocess.run(command, text=True, capture_output=True, check=False)
    if result.returncode != 0:
        output = "\n".join(x for x in (result.stdout, result.stderr) if x)
        raise RenderError(f"{label} failed ({result.returncode}):\n{output}")


def ffprobe(path: Path) -> dict[str, Any]:
    require_binary("ffprobe")
    result = subprocess.run(
        [
            "ffprobe",
            "-v",
            "error",
            "-show_entries",
            "format=duration,size,bit_rate:stream=codec_type,codec_name,width,height,pix_fmt,avg_frame_rate,sample_rate,channels",
            "-of",
            "json",
            str(path),
        ],
        text=True,
        capture_output=True,
        check=False,
    )
    if result.returncode != 0:
        raise RenderError(f"ffprobe failed for {path}: {result.stderr}")
    return json.loads(result.stdout)


def parse_fraction(value: str | None) -> float | None:
    if not value or value == "0/0":
        return None
    if "/" in value:
        left, right = value.split("/", 1)
        denominator = float(right)
        return float(left) / denominator if denominator else None
    return float(value)


def media_summary(path: Path) -> dict[str, Any]:
    data = ffprobe(path)
    fmt = data.get("format", {})
    video = next((s for s in data.get("streams", []) if s.get("codec_type") == "video"), {})
    audio = next((s for s in data.get("streams", []) if s.get("codec_type") == "audio"), {})
    return {
        "path": str(path),
        "duration": float(fmt.get("duration") or 0.0),
        "size": int(fmt.get("size") or 0),
        "bit_rate": int(fmt.get("bit_rate") or 0),
        "width": video.get("width"),
        "height": video.get("height"),
        "pix_fmt": video.get("pix_fmt"),
        "fps": parse_fraction(video.get("avg_frame_rate")),
        "video_codec": video.get("codec_name"),
        "audio_codec": audio.get("codec_name"),
        "sample_rate": int(audio.get("sample_rate") or 0) if audio else None,
        "channels": audio.get("channels"),
        "has_audio": bool(audio),
    }


def load_timeline(path: Path) -> dict[str, Any]:
    resolved = path.expanduser().resolve()
    if not resolved.exists():
        raise RenderError(f"Timeline JSON not found: {resolved}")
    data = json.loads(resolved.read_text(encoding="utf-8"))
    for field in ("captions", "materials", "font", "logo", "tail"):
        if field not in data:
            raise RenderError(f"Timeline JSON is missing required field: {field}")
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

    find_placeholders(data, "timeline")
    if placeholders:
        raise RenderError(
            "Timeline JSON contains unresolved placeholders: " + ", ".join(placeholders)
        )
    speed = float(data.get("speed", 1.1))
    if not 0.5 <= speed <= 2.0:
        raise RenderError("speed must be between 0.5 and 2.0 for FFmpeg atempo")
    policy = resolve_visual_policy(data)
    for index, material in enumerate(data.get("materials", [])):
        if not isinstance(material, dict):
            raise RenderError(f"materials[{index}] must be an object")
        if str(material.get("semantic_role", "")) != "benefit_point":
            raise RenderError(
                f"materials[{index}] must use semantic_role=benefit_point; non-benefit narration must not match supplemental materials"
            )
        if not str(material.get("matched_benefit_text", "")).strip():
            raise RenderError(
                f"materials[{index}] must record matched_benefit_text from the benefit-point narration"
            )
    special_match_errors = special_match_metadata_errors(data.get("materials", []))
    if special_match_errors:
        raise RenderError("; ".join(special_match_errors))
    style = data.get("font", {}).get("caption_style", {})
    if not isinstance(style, dict):
        raise RenderError("font.caption_style must be an object")
    outline = float(style.get("outline", 3))
    shadow = float(style.get("shadow", 0))
    if not 2 <= outline <= 3 or shadow != 0:
        raise RenderError("caption policy requires a 2-3px black outline and shadow=0")
    return data


def resolve_asset(asset_root: Path, value: str) -> Path:
    path = Path(value).expanduser()
    return path.resolve() if path.is_absolute() else (asset_root / path).resolve()


def resolve_assets(config: dict[str, Any], asset_root: Path, logo_variant: str) -> dict[str, Any]:
    logo_config = config["logo"]
    logo_key = "white_path" if logo_variant == "white" else "black_path"
    resolved = {
        "font": resolve_asset(asset_root, config["font"]["body_path"]),
        "brand_font": resolve_asset(asset_root, config["font"]["brand_path"]),
        "logo": resolve_asset(asset_root, logo_config[logo_key]),
        "tail": resolve_asset(asset_root, config["tail"]["path"]),
        "materials": [],
    }
    for material in config["materials"]:
        item = dict(material)
        item["path"] = resolve_asset(asset_root, str(material["path"]))
        resolved["materials"].append(item)
    return resolved


def parse_effective_region(
    raw: Any,
    source_width: int,
    source_height: int,
    *,
    label: str,
) -> dict[str, float | str]:
    if not isinstance(raw, dict):
        raise RenderError(f"Missing effective_region for material: {label}")
    try:
        x = float(raw["x"])
        y = float(raw["y"])
        width = float(raw["width"])
        height = float(raw["height"])
    except (KeyError, TypeError, ValueError) as exc:
        raise RenderError(f"Invalid effective_region for material: {label}") from exc
    coordinate_space = str(raw.get("coordinate_space", "source_pixels"))
    if (
        coordinate_space != "source_pixels"
        or x < 0
        or y < 0
        or width <= 0
        or height <= 0
        or x + width > source_width + 1
        or y + height > source_height + 1
    ):
        raise RenderError(
            f"effective_region must be a positive source_pixels rectangle inside {source_width}x{source_height}: {label}"
        )
    return {
        "x": x,
        "y": y,
        "width": width,
        "height": height,
        "coordinate_space": "source_pixels",
    }


def attach_manifest_effective_regions(
    materials: list[dict[str, Any]],
    manifest_path: Path,
    asset_root: Path,
) -> list[dict[str, Any]]:
    if not manifest_path.exists():
        raise RenderError(f"Asset manifest not found: {manifest_path}")
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise RenderError(f"Asset manifest could not be read: {manifest_path}: {exc}") from exc
    manifest_root = Path(str(manifest.get("asset_root", ""))).expanduser().resolve()
    if manifest_root != asset_root:
        raise RenderError(
            f"Asset manifest root does not match --asset-root: {manifest_root} != {asset_root}"
        )
    records = {
        str(item.get("relative_path")): item
        for item in manifest.get("assets", [])
        if isinstance(item, dict) and item.get("relative_path")
    }
    prepared: list[dict[str, Any]] = []
    for material in materials:
        item = dict(material)
        path = Path(item["path"]).resolve()
        try:
            relative = path.relative_to(asset_root).as_posix()
        except ValueError as exc:
            raise RenderError(f"Material is outside the manifest asset root: {path}") from exc
        record = records.get(relative)
        if record is None:
            raise RenderError(f"Material is not tracked by the asset manifest: {relative}")
        source = media_summary(path)
        source_width = int(source.get("width") or 0)
        source_height = int(source.get("height") or 0)
        if source_width <= 0 or source_height <= 0:
            raise RenderError(f"Unable to read material dimensions: {path}")
        item["effective_region"] = parse_effective_region(
            record.get("effective_region"),
            source_width,
            source_height,
            label=relative,
        )
        prepared.append(item)
    return prepared


def validate_files(input_path: Path, bgm_path: Path, assets: dict[str, Any]) -> None:
    paths = [input_path, bgm_path, assets["font"], assets["brand_font"], assets["logo"], assets["tail"]]
    paths.extend(item["path"] for item in assets["materials"])
    missing = [str(path) for path in paths if not Path(path).exists()]
    if missing:
        raise RenderError("Missing required files:\n" + "\n".join(missing))


def has_alpha_channel(pix_fmt: str | None) -> bool:
    value = (pix_fmt or "").lower()
    return value in {"rgba", "bgra", "argb", "abgr", "ya8", "ya16be", "ya16le"} or value.startswith(("yuva", "gbrap"))


def apply_material_safe_area(
    config: dict[str, Any],
    materials: list[dict[str, Any]],
    canvas_width: int,
    canvas_height: int,
) -> list[dict[str, Any]]:
    policy = resolve_visual_policy(config)
    margins = policy["material_safe_area"]
    safe_left = int(margins["left"])
    safe_top = int(margins["top"])
    safe_right = canvas_width - int(margins["right"])
    safe_bottom = canvas_height - int(margins["bottom"])
    safe_width = safe_right - safe_left
    safe_height = safe_bottom - safe_top

    def base_placement(
        layout: str,
        item: dict[str, Any],
        source_width: int,
        source_height: int,
    ) -> tuple[float, float, float, float]:
        if layout == "full_alpha":
            return 0.0, 0.0, float(canvas_width), float(canvas_height)
        if layout == "phone":
            scale = min(650 / source_width, 1050 / source_height)
            width = source_width * scale
            height = source_height * scale
            return (canvas_width - width) / 2, 350.0, width, height
        if layout == "icon":
            width = 230.0
            height = source_height * width / source_width
            return float(item.get("x", 95)), 720.0, width, height
        if layout == "cta_icon":
            return (canvas_width - 300) / 2, 650.0, 300.0, 300.0
        raise RenderError(f"Unsupported material layout: {layout}")

    def map_effective_bounds(
        region: dict[str, float | str],
        asset_x: float,
        asset_y: float,
        asset_width: float,
        asset_height: float,
        source_width: int,
        source_height: int,
    ) -> dict[str, float]:
        return {
            "x": asset_x + float(region["x"]) * asset_width / source_width,
            "y": asset_y + float(region["y"]) * asset_height / source_height,
            "width": float(region["width"]) * asset_width / source_width,
            "height": float(region["height"]) * asset_height / source_height,
        }

    prepared: list[dict[str, Any]] = []
    for material in materials:
        item = dict(material)
        source = media_summary(Path(item["path"]))
        source_width = int(source.get("width") or 0)
        source_height = int(source.get("height") or 0)
        if source_width <= 0 or source_height <= 0:
            raise RenderError(f"Unable to read material dimensions: {item.get('path')}")
        layout = str(item.get("layout"))
        region = parse_effective_region(
            item.get("effective_region"),
            source_width,
            source_height,
            label=str(item.get("path")),
        )
        asset_x, asset_y, asset_width, asset_height = base_placement(
            layout,
            item,
            source_width,
            source_height,
        )
        effective = map_effective_bounds(
            region,
            asset_x,
            asset_y,
            asset_width,
            asset_height,
            source_width,
            source_height,
        )
        item["effective_region_canvas"] = {
            key: round(value, 4) for key, value in effective.items()
        }
        violates = (
            effective["x"] < safe_left
            or effective["y"] < safe_top
            or effective["x"] + effective["width"] > safe_right
            or effective["y"] + effective["height"] > safe_bottom
        )
        if not violates:
            item["safe_area_decision"] = "keep_original_size_effective_region_is_clear"
            prepared.append(item)
            continue

        if (
            policy["reposition_before_scale"]
            and effective["width"] <= safe_width
            and effective["height"] <= safe_height
        ):
            target_effective_x = min(
                max(effective["x"], safe_left),
                safe_right - effective["width"],
            )
            target_effective_y = min(
                max(effective["y"], safe_top),
                safe_bottom - effective["height"],
            )
            delta_x = target_effective_x - effective["x"]
            delta_y = target_effective_y - effective["y"]
            transform = {
                "width": max(1, int(round(asset_width))),
                "height": max(1, int(round(asset_height))),
                "x": int(round(asset_x + delta_x)),
                "y": int(round(asset_y + delta_y)),
                "scale": 1.0,
                "resized": False,
                "effective_bounds": {
                    "x": round(target_effective_x, 4),
                    "y": round(target_effective_y, 4),
                    "width": round(effective["width"], 4),
                    "height": round(effective["height"], 4),
                },
                "reason": "reposition_only_when_effective_content_overlaps_brand_regions",
            }
        else:
            scale = min(
                safe_width / effective["width"],
                safe_height / effective["height"],
                1.0,
            )
            target_asset_width = asset_width * scale
            target_asset_height = asset_height * scale
            target_effective_width = effective["width"] * scale
            target_effective_height = effective["height"] * scale
            target_effective_x = safe_left + (safe_width - target_effective_width) / 2
            target_effective_y = safe_top + (safe_height - target_effective_height) / 2
            region_offset_x = float(region["x"]) * target_asset_width / source_width
            region_offset_y = float(region["y"]) * target_asset_height / source_height
            transform = {
                "width": max(1, int(round(target_asset_width))),
                "height": max(1, int(round(target_asset_height))),
                "x": int(round(target_effective_x - region_offset_x)),
                "y": int(round(target_effective_y - region_offset_y)),
                "scale": round(scale, 4),
                "resized": scale < 0.9999,
                "effective_bounds": {
                    "x": round(target_effective_x, 4),
                    "y": round(target_effective_y, 4),
                    "width": round(target_effective_width, 4),
                    "height": round(target_effective_height, 4),
                },
                "reason": "largest_safe_scale_only_when_effective_content_cannot_be_repositioned",
            }
        item["safe_transform"] = transform
        prepared.append(item)
    return prepared


def resolve_logo_mode(config: dict[str, Any], logo_info: dict[str, Any]) -> str:
    logo_config = config.get("logo", {})
    requested = str(logo_config.get("mode", "auto"))
    if requested not in {"auto", "full_canvas", "placed"}:
        raise RenderError("logo.mode must be auto, full_canvas, or placed")
    source_width = int(logo_info.get("width") or 0)
    source_height = int(logo_info.get("height") or 0)
    target_width = int(config.get("width", 1080))
    target_height = int(config.get("height", 1920))
    matching_canvas = (
        source_width > 0
        and source_height > 0
        and math.isclose(
            source_width / source_height,
            target_width / target_height,
            rel_tol=0.0,
            abs_tol=0.002,
        )
    )
    alpha = has_alpha_channel(str(logo_info.get("pix_fmt") or ""))
    if requested == "full_canvas":
        if not alpha:
            raise RenderError("full_canvas logo must use an image with an alpha channel")
        return requested
    if requested == "auto" and matching_canvas and alpha:
        return "full_canvas"
    return "placed"


def map_time(value: float, config: dict[str, Any], mode_override: str | None = None) -> float:
    mode = mode_override or config.get("time_mode", "original")
    speed = float(config.get("speed", 1.1))
    if mode == "output":
        return max(0.0, value)
    if mode == "input":
        return max(0.0, value / speed)
    if mode != "original":
        raise RenderError(f"Unsupported time_mode: {mode}")
    original = value
    removed = 0.0
    for start, end in config.get("removed_ranges", []):
        start_value, end_value = float(start), float(end)
        if original >= end_value:
            removed += end_value - start_value
            continue
        if original > start_value:
            original = start_value
        break
    return max(0.0, (original - removed) / speed)


def mapped_captions(config: dict[str, Any], main_duration: float) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for caption in config["captions"]:
        caption_time_mode = str(caption.get("time_mode") or config.get("time_mode", "original"))
        start = min(map_time(float(caption["start"]), config, caption_time_mode), main_duration)
        end = min(map_time(float(caption["end"]), config, caption_time_mode), main_duration)
        if end - start < 0.18:
            end = min(main_duration, start + 0.18)
        if end > start:
            text = normalize_subtitle_text(str(caption["text"]))
            if text:
                result.append(
                    {
                        "start": start,
                        "end": end,
                        "text": text,
                        "time_mode": caption_time_mode,
                        "timing_source": caption.get("timing_source"),
                    }
                )
    return result


def mapped_materials(config: dict[str, Any], assets: dict[str, Any], main_duration: float) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for material in assets["materials"]:
        item = dict(material)
        item["mapped_start"] = min(map_time(float(material["start"]), config), main_duration)
        item["mapped_end"] = min(map_time(float(material["end"]), config), main_duration)
        result.append(item)
    return result


def ass_timestamp(seconds: float) -> str:
    value = max(0.0, seconds)
    hours = int(value // 3600)
    minutes = int((value % 3600) // 60)
    secs = value % 60
    return f"{hours}:{minutes:02d}:{secs:05.2f}"


def escape_ass_text(text: str) -> str:
    return text.replace("\\", r"\\").replace("{", r"\{").replace("}", r"\}").replace("\n", r"\N")


def normalize_subtitle_text(text: str) -> str:
    """Remove subtitle punctuation while keeping phrase-separating spaces."""
    normalized_lines: list[str] = []
    for raw_line in str(text).replace("\r\n", "\n").replace("\r", "\n").split("\n"):
        chars: list[str] = []
        for char in raw_line:
            if unicodedata.category(char).startswith("P"):
                chars.append(" ")
            else:
                chars.append(char)
        line = re.sub(r"[ \t]+", " ", "".join(chars)).strip()
        if line:
            normalized_lines.append(line)
    return "\n".join(normalized_lines)


def rgb_to_ass(value: str, *, style: bool = False) -> str:
    match = re.fullmatch(r"#?([0-9A-Fa-f]{6})", value.strip())
    if not match:
        raise RenderError(f"Invalid RGB color: {value}; expected #RRGGBB")
    rgb = match.group(1).upper()
    red, green, blue = rgb[0:2], rgb[2:4], rgb[4:6]
    bgr = blue + green + red
    return f"&H00{bgr}" if style else f"&H{bgr}&"


def resolve_caption_style(config: dict[str, Any], width: int, height: int) -> dict[str, Any]:
    raw = config.get("font", {}).get("caption_style", {})
    if not isinstance(raw, dict):
        raise RenderError("font.caption_style must be an object")

    def number(name: str, default: float, minimum: float, maximum: float) -> float:
        value = float(raw.get(name, default))
        if not minimum <= value <= maximum:
            raise RenderError(
                f"font.caption_style.{name} must be between {minimum:g} and {maximum:g}"
            )
        return value

    alignment = int(raw.get("alignment", 2))
    if alignment not in range(1, 10):
        raise RenderError("font.caption_style.alignment must be between 1 and 9")

    position_mode = str(raw.get("position_mode", "margins"))
    if position_mode not in {"margins", "center_offset", "absolute"}:
        raise RenderError(
            "font.caption_style.position_mode must be margins, center_offset, or absolute"
        )

    style: dict[str, Any] = {
        "font_size": number("font_size", 70, 1, 300),
        "scale_x": number("scale_x", 100, 10, 500),
        "scale_y": number("scale_y", 100, 10, 500),
        "spacing": number("spacing", 0, -50, 100),
        "outline": number("outline", 3, 0, 50),
        "shadow": number("shadow", 0, 0, 50),
        "alignment": alignment,
        "margin_left": int(number("margin_left", 72, 0, width)),
        "margin_right": int(number("margin_right", 72, 0, width)),
        "margin_vertical": int(number("margin_vertical", 330, 0, height)),
        "position_mode": position_mode,
    }
    if position_mode != "margins":
        x = number("x", 0, -width * 2, width * 2)
        y = number("y", 0, -height * 2, height * 2)
        if position_mode == "center_offset":
            # Template coordinates use the canvas centre as origin and positive Y upward.
            position_x = width / 2 + x
            position_y = height / 2 - y
        else:
            position_x, position_y = x, y
        if not 0 <= position_x <= width or not 0 <= position_y <= height:
            raise RenderError("font.caption_style position resolves outside the output canvas")
        style["x"] = x
        style["y"] = y
        style["position_x"] = position_x
        style["position_y"] = position_y
    return style


def ass_number(value: float | int) -> str:
    return f"{float(value):g}"


def apply_brand_style(
    text: str,
    body_family: str,
    brand_family: str,
    body_color: str,
    brand_color: str,
) -> str:
    escaped = escape_ass_text(text)
    pattern = re.compile("汽水音乐|汽水")
    brand_override = "{\\fn" + brand_family + "\\1c" + rgb_to_ass(brand_color) + "}"
    body_override = "{\\fn" + body_family + "\\1c" + rgb_to_ass(body_color) + "}"
    return pattern.sub(
        lambda match: brand_override + match.group(0) + body_override,
        escaped,
    )


def generate_ass(
    captions: list[dict[str, Any]],
    output_path: Path,
    *,
    width: int,
    height: int,
    body_family: str,
    brand_family: str,
    body_color: str,
    brand_color: str,
    caption_style: dict[str, Any],
) -> None:
    position_override = ""
    if caption_style["position_mode"] != "margins":
        position_override = (
            "{\\pos("
            + ass_number(caption_style["position_x"])
            + ","
            + ass_number(caption_style["position_y"])
            + ")}"
        )
    header = f"""[Script Info]
ScriptType: v4.00+
PlayResX: {width}
PlayResY: {height}
ScaledBorderAndShadow: yes
WrapStyle: 0

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Default,{body_family},{ass_number(caption_style['font_size'])},{rgb_to_ass(body_color, style=True)},&H000000FF,&H00000000,&H64000000,-1,0,0,0,{ass_number(caption_style['scale_x'])},{ass_number(caption_style['scale_y'])},{ass_number(caption_style['spacing'])},0,1,{ass_number(caption_style['outline'])},{ass_number(caption_style['shadow'])},{caption_style['alignment']},{caption_style['margin_left']},{caption_style['margin_right']},{caption_style['margin_vertical']},1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    lines = [header]
    for caption in captions:
        text = apply_brand_style(
            str(caption["text"]),
            body_family,
            brand_family,
            body_color,
            brand_color,
        )
        lines.append(
            f"Dialogue: 0,{ass_timestamp(float(caption['start']))},{ass_timestamp(float(caption['end']))},Default,,0,0,0,,{position_override}{text}\n"
        )
    output_path.write_text("".join(lines), encoding="utf-8-sig")


def escape_filter_path(path: Path) -> str:
    return str(path).replace("\\", r"\\").replace(":", r"\:").replace("'", r"\'")


def escape_drawtext(text: str) -> str:
    return (
        text.replace("\\", r"\\")
        .replace("'", r"\'")
        .replace(":", r"\:")
        .replace("%", r"\%")
    )


def drawtext(
    text: str,
    *,
    font_file: Path,
    x: str,
    y: str,
    size: int,
    color: str,
    enable: str | None = None,
    border: int = 0,
    border_color: str = "black@0.72",
) -> str:
    options = [
        f"fontfile='{escape_filter_path(font_file)}'",
        f"text='{escape_drawtext(text)}'",
        f"x={x}",
        f"y={y}",
        f"fontsize={size}",
        f"fontcolor={color}",
    ]
    if border:
        options.extend([f"borderw={border}", f"bordercolor={border_color}"])
    if enable:
        options.append(f"enable='{enable}'")
    return "drawtext=" + ":".join(options)


def common_encode_args(config: dict[str, Any]) -> list[str]:
    fps = int(config.get("fps", 30))
    return [
        "-c:v", "libx264",
        "-preset", str(config.get("preset", "medium")),
        "-crf", str(config.get("crf", 18)),
        "-profile:v", "high",
        "-level:v", "4.1",
        "-pix_fmt", "yuv420p",
        "-r", str(fps),
        "-g", str(fps * 2),
        "-keyint_min", str(fps * 2),
        "-sc_threshold", "0",
        "-c:a", "aac",
        "-b:a", "192k",
        "-ar", "44100",
        "-ac", "2",
        "-movflags", "+faststart",
    ]


def input_args(path: Path, kind: str, fps: int) -> list[str]:
    if kind == "image":
        return ["-loop", "1", "-framerate", str(fps), "-i", str(path)]
    return ["-stream_loop", "-1", "-i", str(path)]


def render_main(
    input_path: Path,
    ass_path: Path,
    output_path: Path,
    config: dict[str, Any],
    assets: dict[str, Any],
    font_dir: Path,
    materials: list[dict[str, Any]],
    main_duration: float,
    *,
    show_warning: bool,
    logo_mode: str,
) -> None:
    width, height, fps = int(config.get("width", 1080)), int(config.get("height", 1920)), int(config.get("fps", 30))
    speed = float(config.get("speed", 1.1))
    font_file = assets["font"]
    safe_margins = resolve_visual_policy(config)["material_safe_area"]
    safe_left = int(safe_margins["left"])
    safe_top = int(safe_margins["top"])
    safe_width = width - safe_left - int(safe_margins["right"])
    safe_height = height - safe_top - int(safe_margins["bottom"])
    command = ["ffmpeg", "-hide_banner", "-y", "-i", str(input_path)]
    command.extend(input_args(assets["logo"], "image", fps))
    for material in materials:
        if str(material.get("layout")) == "motion_alpha":
            command.extend(["-i", str(material["path"])])
        else:
            command.extend(input_args(Path(material["path"]), str(material["kind"]), fps))

    base_filters = [
        f"setpts=PTS/{speed}", f"fps={fps}", f"scale={width}:{height}", "setsar=1",
    ]

    filters = [f"[0:v]{','.join(base_filters)}[base]"]
    logo_config = config.get("logo", {})
    if logo_mode == "full_canvas":
        filters.append(f"[1:v]scale={width}:{height},setsar=1,format=rgba[logo]")
        logo_x, logo_y = 0, 0
    else:
        logo_width = int(logo_config.get("width", 286))
        crop = logo_config.get("crop")
        if crop and len(crop) == 4:
            filters.append(
                f"[1:v]crop={int(crop[2])}:{int(crop[3])}:{int(crop[0])}:{int(crop[1])},scale={logo_width}:-1,format=rgba[logo]"
            )
        else:
            filters.append(f"[1:v]scale={logo_width}:-1,format=rgba[logo]")
        logo_x = int(logo_config.get("x", 48))
        logo_y = int(logo_config.get("y", 72))
    current = "base"
    for offset, material in enumerate(materials, start=2):
        asset_label, next_label = f"asset{offset}", f"v{offset}"
        enable = f"between(t,{material['mapped_start']:.3f},{material['mapped_end']:.3f})"
        layout = material["layout"]
        if layout == "full_alpha":
            transform = material.get("safe_transform")
            if transform:
                chain: list[str] = []
                crop = transform.get("crop")
                if crop:
                    chain.append(f"crop={int(crop[2])}:{int(crop[3])}:{int(crop[0])}:{int(crop[1])}")
                chain.extend(
                    [
                        f"scale={int(transform['width'])}:{int(transform['height'])}",
                        "setsar=1",
                        "format=rgba",
                    ]
                )
                filters.append(f"[{offset}:v]" + ",".join(chain) + f"[{asset_label}]")
                overlay = f"[{current}][{asset_label}]overlay=x={int(transform['x'])}:y={int(transform['y'])}:format=auto:enable='{enable}':eof_action=pass[{next_label}]"
            else:
                filters.append(f"[{offset}:v]scale={width}:{height},format=rgba[{asset_label}]")
                overlay = f"[{current}][{asset_label}]overlay=x=0:y=0:format=auto:enable='{enable}':eof_action=pass[{next_label}]"
        elif layout == "phone":
            transform = material.get("safe_transform")
            target_width = int(transform["width"]) if transform else 650
            target_height = int(transform["height"]) if transform else 1050
            overlay_x = str(int(transform["x"])) if transform else "(W-w)/2"
            overlay_y = str(int(transform["y"])) if transform else "350"
            filters.append(f"[{offset}:v]scale={target_width}:{target_height}:force_original_aspect_ratio=decrease,setsar=1,format=rgba[{asset_label}]")
            overlay = f"[{current}][{asset_label}]overlay=x={overlay_x}:y={overlay_y}:format=auto:enable='{enable}':eof_action=pass[{next_label}]"
        elif layout == "icon":
            transform = material.get("safe_transform")
            if transform:
                filters.append(f"[{offset}:v]scale={int(transform['width'])}:{int(transform['height'])},format=rgba[{asset_label}]")
                overlay_x, overlay_y = int(transform["x"]), int(transform["y"])
            else:
                filters.append(f"[{offset}:v]scale=230:-1,format=rgba[{asset_label}]")
                overlay_x, overlay_y = int(material.get("x", 95)), 720
            overlay = f"[{current}][{asset_label}]overlay=x={overlay_x}:y={overlay_y}:format=auto:enable='{enable}':eof_action=pass[{next_label}]"
        elif layout == "cta_icon":
            transform = material.get("safe_transform")
            target_width = int(transform["width"]) if transform else 300
            target_height = int(transform["height"]) if transform else 300
            overlay_x = str(int(transform["x"])) if transform else "(W-w)/2"
            overlay_y = str(int(transform["y"])) if transform else "650"
            filters.append(f"[{offset}:v]scale={target_width}:{target_height},format=rgba[{asset_label}]")
            overlay = f"[{current}][{asset_label}]overlay=x={overlay_x}:y={overlay_y}:format=auto:enable='{enable}':eof_action=pass[{next_label}]"
        elif layout == "motion_alpha":
            motion = material.get("motion_effect", {})
            clip_duration = float(motion.get("clip_duration", 0.0))
            visible_duration = max(
                0.0,
                float(material["mapped_end"]) - float(material["mapped_start"]),
            )
            if clip_duration <= 0:
                raise RenderError(f"Invalid Remotion alpha duration for {material.get('name')}")
            hold_duration = max(0.0, visible_duration - clip_duration)
            chain = [
                f"[{offset}:v]trim=duration={clip_duration:.6f}",
                "setpts=PTS-STARTPTS",
                f"fps={fps}",
                f"scale={width}:{height}",
                "setsar=1",
                "format=rgba",
                f"crop={safe_width}:{safe_height}:{safe_left}:{safe_top}",
                f"pad={width}:{height}:{safe_left}:{safe_top}:color=black@0",
                "format=rgba",
            ]
            if hold_duration > 0:
                chain.append(f"tpad=stop_mode=clone:stop_duration={hold_duration:.6f}")
            chain.append(f"setpts=PTS+{float(material['mapped_start']):.6f}/TB[{asset_label}]")
            filters.append(",".join(chain))
            overlay = f"[{current}][{asset_label}]overlay=x=0:y=0:format=auto:enable='{enable}':eof_action=pass[{next_label}]"
        else:
            raise RenderError(f"Unsupported material layout: {layout}")
        filters.append(overlay)
        current = next_label

    caption_filters = [
        f"subtitles='{escape_filter_path(ass_path)}':fontsdir='{escape_filter_path(font_dir)}'"
    ]
    cta = next(
        (
            item for item in materials
            if item.get("layout") == "cta_icon"
            or item.get("base_layout") == "cta_icon"
        ),
        None,
    )
    if cta:
        enable = f"between(t,{cta['mapped_start']:.3f},{cta['mapped_end']:.3f})"
        cta_config = config.get("cta", {})
        caption_filters.extend(
            [
                drawtext(str(cta_config.get("title", "")), font_file=font_file, x="(w-text_w)/2", y="1010", size=74, color="0x3BFD42", enable=enable),
                drawtext(str(cta_config.get("subtitle", "")), font_file=font_file, x="(w-text_w)/2", y="1110", size=42, color="white", enable=enable),
            ]
        )
    filters.append(f"[{current}]" + ",".join(caption_filters) + "[captioned]")
    logo_output = "logoed" if show_warning else "vout"
    filters.append(
        f"[captioned][logo]overlay=x={logo_x}:y={logo_y}:format=auto:eof_action=pass[{logo_output}]"
    )
    if show_warning:
        filters.append(
            f"[logoed]"
            + drawtext(
                str(config.get("warning_text", "本视频为广告创意，具体奖励金额以产品实际情况为准")),
                font_file=font_file, x="(w-text_w)/2", y="1822", size=27,
                color="white@0.92",
            )
            + "[vout]"
        )
    filters.append(
        f"[0:a]atempo={speed},loudnorm=I=-16:LRA=7:TP=-1.5,aformat=sample_rates=44100:channel_layouts=stereo[aout]"
    )
    command.extend(
        [
            "-filter_complex", ";".join(filters), "-map", "[vout]", "-map", "[aout]",
            "-t", f"{main_duration:.3f}", *common_encode_args(config), str(output_path),
        ]
    )
    run(command, label="main-render")


def render_tail(output_path: Path, config: dict[str, Any], tail_path: Path, tail_duration: float) -> None:
    width, height, fps = int(config.get("width", 1080)), int(config.get("height", 1920)), int(config.get("fps", 30))
    info = media_summary(tail_path)
    if info["has_audio"]:
        command = [
            "ffmpeg", "-hide_banner", "-y", "-i", str(tail_path),
            "-filter_complex", f"[0:v]scale={width}:{height},fps={fps},setsar=1[vout];[0:a]aformat=sample_rates=44100:channel_layouts=stereo,volume=0.9[aout]",
            "-map", "[vout]", "-map", "[aout]", "-t", f"{tail_duration:.3f}",
            *common_encode_args(config), str(output_path),
        ]
    else:
        command = [
            "ffmpeg", "-hide_banner", "-y", "-i", str(tail_path),
            "-f", "lavfi", "-t", f"{tail_duration:.3f}", "-i", "anullsrc=r=44100:cl=stereo",
            "-filter_complex", f"[0:v]scale={width}:{height},fps={fps},setsar=1[vout]",
            "-map", "[vout]", "-map", "1:a:0", "-t", f"{tail_duration:.3f}",
            *common_encode_args(config), str(output_path),
        ]
    run(command, label="tail-render")


def concat_parts(parts: Iterable[Path], list_path: Path, output_path: Path) -> None:
    list_path.write_text("\n".join(f"file '{part.as_posix()}'" for part in parts) + "\n", encoding="utf-8")
    run(
        ["ffmpeg", "-hide_banner", "-y", "-f", "concat", "-safe", "0", "-i", str(list_path), "-c", "copy", str(output_path)],
        label="timeline-concat",
    )


def mix_bgm_and_cues(
    timeline_path: Path,
    bgm_path: Path,
    output_path: Path,
    total_duration: float,
    config: dict[str, Any],
    cue_materials: list[dict[str, Any]],
    bgm_target_lufs: float,
    bgm_volume: float,
) -> None:
    bgm_target_lufs, bgm_volume = validate_bgm_settings(bgm_target_lufs, bgm_volume)
    fade_out_start = max(0.0, total_duration - 1.25)
    filters = [
        "[0:a]aformat=sample_rates=44100:channel_layouts=stereo[base]",
        f"[1:a]atrim=0:{total_duration:.3f},asetpts=PTS-STARTPTS,aformat=sample_rates=44100:channel_layouts=stereo,loudnorm=I={bgm_target_lufs:.1f}:LRA=7:TP=-2.0,volume={bgm_volume:.3f},afade=t=in:st=0:d=0.8,afade=t=out:st={fade_out_start:.3f}:d=1.2[bgm]",
    ]
    cue_labels: list[str] = []
    for index, material in enumerate(cue_materials):
        delay_ms = round(float(material["mapped_start"]) * 1000)
        frequency = 760 + (index % 3) * 120
        label = f"cue{index}"
        filters.append(
            f"sine=frequency={frequency}:sample_rate=44100:duration=0.12,volume=0.075,afade=t=out:st=0.02:d=0.10,adelay={delay_ms}|{delay_ms},aformat=sample_rates=44100:channel_layouts=stereo[{label}]"
        )
        cue_labels.append(f"[{label}]")
    inputs = "[base][bgm]" + "".join(cue_labels)
    filters.append(f"{inputs}amix=inputs={2 + len(cue_labels)}:duration=first:dropout_transition=0:normalize=0,alimiter=limit=0.95[outa]")
    run(
        [
            "ffmpeg", "-hide_banner", "-y", "-i", str(timeline_path), "-stream_loop", "-1", "-i", str(bgm_path),
            "-filter_complex", ";".join(filters), "-map", "0:v:0", "-map", "[outa]", "-c:v", "copy",
            "-c:a", "aac", "-b:a", "192k", "-ar", "44100", "-ac", "2", "-movflags", "+faststart", "-shortest", str(output_path),
        ],
        label="bgm-mix",
    )


def extract_cover(video_path: Path, cover_path: Path) -> None:
    run(
        ["ffmpeg", "-hide_banner", "-y", "-i", str(video_path), "-frames:v", "1", "-q:v", "2", str(cover_path)],
        label="cover",
    )


def build_report(
    input_path: Path,
    bgm_path: Path,
    output_path: Path,
    asset_root: Path,
    timeline_path: Path,
    config: dict[str, Any],
    assets: dict[str, Any],
    materials: list[dict[str, Any]],
    source_duration: float,
    main_duration: float,
    tail_duration: float,
    bgm_target_lufs: float,
    bgm_volume: float,
    logo_variant: str,
    logo_mode: str,
    logo_info: dict[str, Any],
) -> dict[str, Any]:
    return {
        "renderer": "standalone-ffmpeg",
        "input": str(input_path),
        "bgm": str(bgm_path),
        "bgm_target_lufs": bgm_target_lufs,
        "bgm_volume": bgm_volume,
        "bgm_volume_mode": "post-normalization-fine-gain",
        "output": str(output_path),
        "asset_root": str(asset_root),
        "timeline_json": str(timeline_path),
        "resolution": [int(config.get("width", 1080)), int(config.get("height", 1920))],
        "fps": int(config.get("fps", 30)),
        "speed": float(config.get("speed", 1.1)),
        "source_duration": source_duration,
        "main_duration": main_duration,
        "pre_roll_duration": 0.0,
        "opening_policy": "direct-to-digital-human",
        "caption_layer": "above-all-materials",
        "caption_text_policy": "caller-script text filled into actual Whisper word timestamps; punctuation removed at render",
        "material_matching_policy": "supplemental materials only on explicit benefit-point narration",
        "material_collision_policy": "only effective_region content can trigger repositioning or scaling",
        "logo_layer": "above-materials-captions-and-cta",
        "warning_layer": "topmost-when-enabled",
        "layer_order": ["base", "materials", "captions_and_cta", "logo", "warning"],
        "tail_duration": tail_duration,
        "estimated_total_duration": main_duration + tail_duration,
        "logo_variant": logo_variant,
        "logo_mode": logo_mode,
        "logo": str(assets["logo"]),
        "logo_source": {
            "width": logo_info.get("width"),
            "height": logo_info.get("height"),
            "pix_fmt": logo_info.get("pix_fmt"),
        },
        "font": str(assets["font"]),
        "brand_font": str(assets["brand_font"]),
        "tail": str(assets["tail"]),
        "visual_policy": resolve_visual_policy(config),
        "materials": [
            {**{key: value for key, value in item.items() if key != "path"}, "path": str(item["path"])}
            for item in materials
        ],
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--asset-root", type=Path, required=True)
    parser.add_argument("--asset-manifest", type=Path, required=True)
    parser.add_argument("--bgm", type=Path, required=True)
    parser.add_argument("--timeline-json", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument(
        "--speed",
        type=float,
        help="Playback speed applied after pause trimming; defaults to timeline speed or 1.1",
    )
    parser.add_argument(
        "--bgm-target-lufs",
        type=float,
        default=DEFAULT_BGM_TARGET_LUFS,
        help="Target integrated loudness for BGM before fine gain; defaults to -28 LUFS",
    )
    parser.add_argument(
        "--bgm-volume",
        type=float,
        default=DEFAULT_BGM_FINE_VOLUME,
        help="Post-normalization BGM fine gain, normally 1.0; valid range 0.5-1.5",
    )
    parser.add_argument("--logo-variant", choices=("white", "black"), default="white")
    parser.add_argument("--show-warning", action="store_true")
    parser.add_argument("--motion-effects", choices=("auto", "off", "required"))
    parser.add_argument("--motion-seed")
    parser.add_argument("--dry-run", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    require_binary("ffmpeg")
    input_path = args.input.expanduser().resolve()
    asset_root = args.asset_root.expanduser().resolve()
    asset_manifest_path = args.asset_manifest.expanduser().resolve()
    bgm_path = args.bgm.expanduser().resolve()
    timeline_path = args.timeline_json.expanduser().resolve()
    output_path = args.output.expanduser().resolve()
    config = load_timeline(timeline_path)
    try:
        config = apply_motion_overrides(config, args.motion_effects, args.motion_seed)
    except MotionEffectsError as exc:
        raise RenderError(str(exc)) from exc
    bgm_target_lufs, bgm_volume = validate_bgm_settings(args.bgm_target_lufs, args.bgm_volume)
    if args.speed is not None:
        config["speed"] = float(args.speed)
    speed = float(config.get("speed", 1.1))
    if not 0.5 <= speed <= 2.0:
        raise RenderError("speed must be between 0.5 and 2.0 for FFmpeg atempo")
    assets = resolve_assets(config, asset_root, args.logo_variant)
    assets["materials"] = attach_manifest_effective_regions(
        assets["materials"],
        asset_manifest_path,
        asset_root,
    )
    validate_files(input_path, bgm_path, assets)
    logo_info = media_summary(assets["logo"])
    logo_mode = resolve_logo_mode(config, logo_info)
    caption_style = resolve_caption_style(
        config,
        int(config.get("width", 1080)),
        int(config.get("height", 1920)),
    )

    source_duration = media_summary(input_path)["duration"]
    main_duration = source_duration / speed
    tail_info = media_summary(assets["tail"])
    tail_duration = float(config.get("tail_duration") or tail_info["duration"])
    captions = mapped_captions(config, main_duration)
    materials = mapped_materials(config, assets, main_duration)
    materials = apply_material_safe_area(
        config,
        materials,
        int(config.get("width", 1080)),
        int(config.get("height", 1920)),
    )
    try:
        motion_plan = plan_motion_effects(
            config,
            materials,
            timeline_path=timeline_path,
            output_path=output_path,
            canvas_width=int(config.get("width", 1080)),
            canvas_height=int(config.get("height", 1920)),
            fps=int(config.get("fps", 30)),
        )
    except MotionEffectsError as exc:
        raise RenderError(str(exc)) from exc
    report = build_report(
        input_path, bgm_path, output_path, asset_root, timeline_path, config, assets,
        materials, source_duration, main_duration, tail_duration, bgm_target_lufs, bgm_volume, args.logo_variant,
        logo_mode, logo_info,
    )
    report["captions"] = captions
    report["caption_style"] = caption_style
    report["motion_effects"] = motion_plan
    if motion_plan.get("status") == "planned":
        report["renderer"] = "standalone-ffmpeg-remotion-effects"
    print(json.dumps(report, ensure_ascii=False, indent=2))
    if args.dry_run:
        return 0

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="soda_standalone_") as temp_dir:
        temp = Path(temp_dir)
        ass_path = temp / "captions.ass"
        main_path = temp / "02_main.mp4"
        tail_path = temp / "03_tail.mp4"
        concat_list = temp / "concat.txt"
        timeline_video = temp / "timeline.mp4"
        font_dir = temp / "fonts"
        font_dir.mkdir()
        try:
            render_materials, motion_report = render_motion_effects(
                motion_plan,
                materials,
                asset_root=asset_root,
                work_dir=temp / "motion_effects",
                canvas_width=int(config.get("width", 1080)),
                canvas_height=int(config.get("height", 1920)),
                fps=int(config.get("fps", 30)),
            )
        except MotionEffectsError as exc:
            raise RenderError(str(exc)) from exc
        report["motion_effects"] = motion_report
        if motion_report.get("rendered"):
            report["renderer"] = "standalone-ffmpeg-remotion-effects"
        shutil.copy2(assets["font"], font_dir / ("body" + assets["font"].suffix))
        shutil.copy2(
            assets["brand_font"],
            font_dir / ("brand" + assets["brand_font"].suffix),
        )
        generate_ass(
            captions,
            ass_path,
            width=int(config.get("width", 1080)),
            height=int(config.get("height", 1920)),
            body_family=str(config["font"]["body_family"]),
            brand_family=str(config["font"]["brand_family"]),
            body_color=str(config["font"].get("body_color", "#FFFFFF")),
            brand_color=str(config["font"].get("brand_color", "#3BFD42")),
            caption_style=caption_style,
        )
        render_main(
            input_path,
            ass_path,
            main_path,
            config,
            assets,
            font_dir,
            render_materials,
            main_duration,
            show_warning=args.show_warning,
            logo_mode=logo_mode,
        )
        render_tail(tail_path, config, assets["tail"], tail_duration)
        concat_parts([main_path, tail_path], concat_list, timeline_video)
        actual_duration = media_summary(timeline_video)["duration"] or report["estimated_total_duration"]
        cue_materials: list[dict[str, Any]] = []
        seen: set[float] = set()
        for item in materials:
            start = round(float(item["mapped_start"]), 3)
            if start not in seen:
                seen.add(start)
                cue_materials.append(item)
        mix_bgm_and_cues(
            timeline_video,
            bgm_path,
            output_path,
            actual_duration,
            config,
            cue_materials,
            bgm_target_lufs,
            bgm_volume,
        )

    cover_path = output_path.with_name(output_path.stem + "_封面.jpg")
    extract_cover(output_path, cover_path)
    report["actual_output"] = media_summary(output_path)
    report["cover"] = str(cover_path)
    report_path = output_path.with_suffix(".json")
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Finished video: {output_path}")
    print(f"Cover: {cover_path}")
    print(f"Report: {report_path}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (RenderError, MotionEffectsError, OSError, ValueError, json.JSONDecodeError) as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False, indent=2), file=sys.stderr)
        raise SystemExit(2)
