#!/usr/bin/env python3
"""Optional bridge from the Soda renderer to the installed Remotion effects skill."""

from __future__ import annotations

import hashlib
import json
import os
import random
import shutil
import subprocess
from pathlib import Path
from typing import Any


class MotionEffectsError(RuntimeError):
    pass


DEFAULT_POLICY = {
    "mode": "auto",
    "selection": "random",
    "seed": None,
    "apply_probability": 1.0,
    "max_events": 3,
    "eligible_layouts": ["full_alpha", "phone", "cta_icon"],
    "min_visible_duration": 0.8,
    "effect_duration": None,
    "samples": None,
}


def apply_motion_overrides(
    config: dict[str, Any],
    mode: str | None = None,
    seed: str | None = None,
) -> dict[str, Any]:
    result = dict(config)
    raw = result.get("motion_effects", {})
    if raw is None:
        raw = {}
    if not isinstance(raw, dict):
        raise MotionEffectsError("motion_effects must be an object")
    policy = dict(raw)
    if mode is not None:
        policy["mode"] = mode
    if seed is not None:
        policy["seed"] = seed
    result["motion_effects"] = policy
    return result


def resolve_motion_policy(config: dict[str, Any]) -> dict[str, Any]:
    raw = config.get("motion_effects", {})
    if raw is None:
        raw = {}
    if not isinstance(raw, dict):
        raise MotionEffectsError("motion_effects must be an object")
    policy = {**DEFAULT_POLICY, **raw}
    mode = str(policy["mode"])
    if mode not in {"auto", "off", "required"}:
        raise MotionEffectsError("motion_effects.mode must be auto, off, or required")
    if str(policy["selection"]) != "random":
        raise MotionEffectsError("motion_effects.selection currently supports random only")
    probability = float(policy["apply_probability"])
    if not 0.0 <= probability <= 1.0:
        raise MotionEffectsError("motion_effects.apply_probability must be between 0 and 1")
    max_events = int(policy["max_events"])
    if max_events < 0:
        raise MotionEffectsError("motion_effects.max_events must be >= 0")
    layouts = policy["eligible_layouts"]
    if not isinstance(layouts, list) or not all(isinstance(item, str) for item in layouts):
        raise MotionEffectsError("motion_effects.eligible_layouts must be a list of layout names")
    min_duration = float(policy["min_visible_duration"])
    effect_duration_raw = policy.get("effect_duration")
    effect_duration = (
        None if effect_duration_raw is None else float(effect_duration_raw)
    )
    samples_raw = policy.get("samples")
    samples = None if samples_raw is None else int(samples_raw)
    if min_duration <= 0 or (effect_duration is not None and effect_duration <= 0):
        raise MotionEffectsError("motion effect durations must be positive")
    if samples is not None and not 1 <= samples <= 96:
        raise MotionEffectsError("motion_effects.samples must be between 1 and 96")
    policy.update(
        {
            "mode": mode,
            "selection": "random",
            "apply_probability": probability,
            "max_events": max_events,
            "eligible_layouts": layouts,
            "min_visible_duration": min_duration,
            "effect_duration": effect_duration,
            "samples": samples,
        }
    )
    return policy


def _skill_root() -> Path:
    codex_home = Path(os.environ.get("CODEX_HOME", Path.home() / ".codex")).expanduser()
    return codex_home / "skills" / "video-motion-effects"


def _chrome_path() -> str | None:
    candidates = [
        os.environ.get("CHROME_PATH"),
        "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
        "/Applications/Chromium.app/Contents/MacOS/Chromium",
        "/usr/bin/google-chrome",
        "/usr/bin/chromium",
    ]
    return next((item for item in candidates if item and Path(item).exists()), None)


def inspect_motion_skill(config: dict[str, Any]) -> dict[str, Any]:
    policy = resolve_motion_policy(config)
    root = _skill_root()
    cli = root / "scripts" / "remotion" / "render.mjs"
    project = cli.parent
    node = shutil.which("node")
    chrome = _chrome_path()
    dependencies = [
        project / "node_modules" / "remotion" / "package.json",
        project / "node_modules" / "@remotion" / "renderer" / "package.json",
        project / "node_modules" / "@remotion" / "bundler" / "package.json",
        project / "node_modules" / "@vysmo" / "transitions" / "package.json",
    ]
    missing: list[str] = []
    if not root.exists():
        missing.append("skill_root")
    if not cli.exists():
        missing.append("render_cli")
    if not node:
        missing.append("node")
    if not chrome:
        missing.append("chrome")
    for dependency in dependencies:
        if not dependency.exists():
            missing.append(str(dependency.relative_to(root)) if root.exists() else str(dependency))

    effects: list[dict[str, Any]] = []
    list_error: str | None = None
    if not missing:
        result = subprocess.run(
            [str(node), str(cli), "list-effects"],
            text=True,
            capture_output=True,
            check=False,
        )
        if result.returncode == 0:
            try:
                data = json.loads(result.stdout)
                raw_effects = data.get("effects", [])
                if isinstance(raw_effects, list):
                    effects = [item for item in raw_effects if isinstance(item, dict) and item.get("type")]
            except json.JSONDecodeError as exc:
                list_error = f"Invalid list-effects JSON: {exc}"
        else:
            list_error = (result.stderr or result.stdout or "list-effects failed").strip()
    if not effects and not missing:
        missing.append("effects")
    if list_error:
        missing.append("list_effects")
    return {
        "mode": policy["mode"],
        "installed": root.exists(),
        "ready": not missing and bool(effects),
        "skill_root": str(root),
        "cli": str(cli),
        "node": node,
        "chrome": chrome,
        "effects": effects,
        "missing": missing,
        "error": list_error,
        "policy": policy,
    }


def _probe(path: Path) -> dict[str, Any]:
    result = subprocess.run(
        [
            "ffprobe",
            "-v",
            "error",
            "-show_entries",
            "format=duration,size:stream=codec_type,codec_name,width,height,pix_fmt",
            "-of",
            "json",
            str(path),
        ],
        text=True,
        capture_output=True,
        check=False,
    )
    if result.returncode != 0:
        raise MotionEffectsError(f"ffprobe failed for {path}: {result.stderr}")
    data = json.loads(result.stdout)
    video = next((item for item in data.get("streams", []) if item.get("codec_type") == "video"), {})
    return {
        "width": int(video.get("width") or 0),
        "height": int(video.get("height") or 0),
        "pix_fmt": str(video.get("pix_fmt") or ""),
        "duration": float(data.get("format", {}).get("duration") or 0.0),
        "size": int(data.get("format", {}).get("size") or 0),
        "codec": video.get("codec_name"),
    }


def _layout_for_material(
    material: dict[str, Any], canvas_width: int, canvas_height: int
) -> tuple[dict[str, float], list[int] | None]:
    source_path = Path(material["path"])
    source = _probe(source_path)
    source_width = source["width"]
    source_height = source["height"]
    if source_width <= 0 or source_height <= 0:
        raise MotionEffectsError(f"Unable to read material dimensions: {source_path}")
    layout = str(material["layout"])
    source_crop: list[int] | None = None
    safe_transform = material.get("safe_transform")
    effective_region = material.get("effective_region")
    effective_canvas = (
        safe_transform.get("effective_bounds")
        if isinstance(safe_transform, dict)
        else material.get("effective_region_canvas")
    )
    if (
        layout == "icon"
        and isinstance(effective_region, dict)
        and isinstance(effective_canvas, dict)
    ):
        target_width = float(effective_canvas["width"])
        target_height = float(effective_canvas["height"])
        x = float(effective_canvas["x"])
        y = float(effective_canvas["y"])
        origin_x = target_width / 2
        origin_y = target_height / 2
        source_crop = [
            int(round(float(effective_region["x"]))),
            int(round(float(effective_region["y"]))),
            max(1, int(round(float(effective_region["width"])))),
            max(1, int(round(float(effective_region["height"])))),
        ]
    elif isinstance(safe_transform, dict):
        target_width = float(safe_transform["width"])
        target_height = float(safe_transform["height"])
        x = float(safe_transform["x"])
        y = float(safe_transform["y"])
        crop = safe_transform.get("crop")
        source_crop = [int(value) for value in crop] if crop else None
        origin_x = target_width / 2
        origin_y = target_height / 2
    elif layout == "full_alpha":
        target_width = float(source_width)
        target_height = float(source_height)
        x = float(material.get("x", 0))
        y = float(material.get("y", 0))
        origin_x = target_width / 2
        origin_y = target_height / 2
    elif layout == "phone":
        target_width = float(source_width)
        target_height = float(source_height)
        x = float(material.get("x", (canvas_width - target_width) / 2))
        y = float(material.get("y", 350))
        origin_x = target_width / 2
        origin_y = target_height / 2
    elif layout == "icon":
        if isinstance(effective_region, dict):
            source_crop = [
                int(round(float(effective_region["x"]))),
                int(round(float(effective_region["y"]))),
                max(1, int(round(float(effective_region["width"])))),
                max(1, int(round(float(effective_region["height"])))),
            ]
            target_width = float(source_crop[2])
            target_height = float(source_crop[3])
        else:
            target_width = float(source_width)
            target_height = float(source_height)
        x = float(material.get("x", 95))
        y = float(material.get("y", 720))
        origin_x = target_width / 2
        origin_y = target_height / 2
    elif layout == "cta_icon":
        target_width = float(source_width)
        target_height = float(source_height)
        x = float(material.get("x", (canvas_width - target_width) / 2))
        y = float(material.get("y", 650))
        origin_x = target_width / 2
        origin_y = target_height / 2
    else:
        raise MotionEffectsError(f"Unsupported motion-effect material layout: {layout}")
    return (
        {
            "width": target_width,
            "height": target_height,
            "x": x,
            "y": y,
            "origin_x": origin_x,
            "origin_y": origin_y,
            "border_radius": 0.0,
        },
        source_crop,
    )


def _seed_value(policy: dict[str, Any], timeline_path: Path, output_path: Path, materials: list[dict[str, Any]]) -> tuple[str, int]:
    explicit = policy.get("seed")
    if explicit is None:
        material_key = [
            [item.get("name"), item.get("mapped_start"), item.get("mapped_end"), str(item.get("path"))]
            for item in materials
        ]
        source = json.dumps(
            {
                "timeline": str(timeline_path.resolve()),
                "output": str(output_path.resolve()),
                "materials": material_key,
            },
            ensure_ascii=False,
            sort_keys=True,
        )
        label = hashlib.sha256(source.encode("utf-8")).hexdigest()[:16]
    else:
        label = str(explicit)
    numeric = int(hashlib.sha256(label.encode("utf-8")).hexdigest()[:16], 16)
    return label, numeric


def plan_motion_effects(
    config: dict[str, Any],
    materials: list[dict[str, Any]],
    *,
    timeline_path: Path,
    output_path: Path,
    canvas_width: int,
    canvas_height: int,
    fps: int,
) -> dict[str, Any]:
    inspection = inspect_motion_skill(config)
    policy = inspection["policy"]
    report: dict[str, Any] = {
        "mode": policy["mode"],
        "selection": policy["selection"],
        "installed": inspection["installed"],
        "ready": inspection["ready"],
        "skill_root": inspection["skill_root"],
        "effects_available": inspection["effects"],
        "missing": inspection["missing"],
        "seed": None,
        "planned": [],
        "warnings": [],
        "status": "disabled" if policy["mode"] == "off" else "unavailable",
        "inspection": inspection,
    }
    if policy["mode"] == "off":
        return report
    if not inspection["ready"]:
        message = "video-motion-effects is not ready; using static material overlays"
        if policy["mode"] == "required":
            raise MotionEffectsError(f"{message}: {inspection['missing']}")
        report["warnings"].append(message)
        return report

    eligible: list[tuple[int, dict[str, Any]]] = []
    allowed_layouts = set(policy["eligible_layouts"])
    for index, material in enumerate(materials):
        duration = float(material["mapped_end"]) - float(material["mapped_start"])
        if (
            str(material.get("kind")) == "image"
            and str(material.get("layout")) in allowed_layouts
            and duration >= policy["min_visible_duration"]
        ):
            eligible.append((index, material))

    seed_label, seed_number = _seed_value(policy, timeline_path, output_path, materials)
    report["seed"] = seed_label
    rng = random.Random(seed_number)
    selected = [item for item in eligible if rng.random() <= policy["apply_probability"]]
    max_events = policy["max_events"]
    if max_events and len(selected) > max_events:
        selected = rng.sample(selected, max_events)
    selected.sort(key=lambda item: item[0])
    effects = inspection["effects"]
    for index, material in selected:
        effect = rng.choice(effects)
        presets = effect.get("presets") if isinstance(effect.get("presets"), list) else []
        default_preset = effect.get("defaultPreset")
        if default_preset not in presets:
            raise MotionEffectsError(
                f"Effect catalog must provide a valid defaultPreset for {effect['type']}"
            )
        preset = str(default_preset)
        configured_duration = policy.get("effect_duration")
        default_duration = effect.get("defaultDuration")
        if configured_duration is None and default_duration is None:
            raise MotionEffectsError(
                f"Effect catalog is missing defaultDuration for {effect['type']}"
            )
        requested_duration = float(
            configured_duration
            if configured_duration is not None
            else default_duration
        )
        effect_duration = min(
            requested_duration,
            float(material["mapped_end"]) - float(material["mapped_start"]) - 1 / fps,
        )
        if effect_duration <= 0:
            continue
        remotion_layout, source_crop = _layout_for_material(material, canvas_width, canvas_height)
        configured_samples = policy.get("samples")
        default_samples = effect.get("defaultSamples")
        samples = (
            int(configured_samples)
            if configured_samples is not None and default_samples is not None
            else (int(default_samples) if default_samples is not None else None)
        )
        planned = {
            "material_index": index,
            "material_name": str(material.get("name", f"material_{index}")),
            "source_path": str(material["path"]),
            "effect": str(effect["type"]),
            "preset": preset,
            "effect_duration": effect_duration,
            "clip_duration": effect_duration + 1 / fps,
            "samples": samples,
            "layout": remotion_layout,
            "base_layout": str(material.get("layout")),
            "source_crop": source_crop,
            "mapped_start": float(material["mapped_start"]),
            "mapped_end": float(material["mapped_end"]),
        }
        report["planned"].append(planned)
    report["status"] = "planned" if report["planned"] else "no-eligible-materials"
    return report


def render_motion_effects(
    plan: dict[str, Any],
    materials: list[dict[str, Any]],
    *,
    asset_root: Path,
    work_dir: Path,
    canvas_width: int,
    canvas_height: int,
    fps: int,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    prepared = [dict(item) for item in materials]
    result_report = dict(plan)
    result_report["rendered"] = []
    result_report["failed"] = []
    if plan.get("status") != "planned":
        return prepared, result_report
    inspection = plan["inspection"]
    cli = Path(inspection["cli"])
    node = inspection["node"]
    required = plan["mode"] == "required"
    work_dir.mkdir(parents=True, exist_ok=True)

    for order, event in enumerate(plan["planned"], start=1):
        event_source = Path(event["source_path"])
        if event.get("source_crop"):
            bx, by, bw, bh = (int(value) for value in event["source_crop"])
            cropped_source = work_dir / f"event_{order:03d}_source.png"
            crop_process = subprocess.run(
                [
                    "ffmpeg",
                    "-y",
                    "-v",
                    "error",
                    "-i",
                    str(event_source),
                    "-vf",
                    f"crop={bw}:{bh}:{bx}:{by}",
                    "-frames:v",
                    "1",
                    str(cropped_source),
                ],
                text=True,
                capture_output=True,
                check=False,
            )
            if crop_process.returncode != 0 or not cropped_source.exists():
                failure = {
                    **event,
                    "error": (crop_process.stderr or "Failed to crop transparent material").strip(),
                }
                result_report["failed"].append(failure)
                if required:
                    raise MotionEffectsError(
                        f"Material crop failed for {event['material_name']}: {failure['error']}"
                    )
                result_report["warnings"].append(
                    f"Material crop failed for {event['material_name']}; kept static overlay"
                )
                continue
            event_source = cropped_source
        timeline = {
            "canvas": {
                "width": canvas_width,
                "height": canvas_height,
                "fps": fps,
                "duration": event["clip_duration"],
                "base_fit": "cover",
                "background_color": "#000000",
            },
            "events": [
                {
                    "name": event["material_name"],
                    "path": str(event_source),
                    "kind": "image",
                    "start": 0,
                    "end": event["clip_duration"],
                    "layout": event["layout"],
                    "effect": {
                        "type": event["effect"],
                        **({"preset": event["preset"]} if event["preset"] else {}),
                        "duration": event["effect_duration"],
                        **({"samples": event["samples"]} if event.get("samples") is not None else {}),
                    },
                }
            ],
        }
        timeline_path = work_dir / f"event_{order:03d}.json"
        output_path = work_dir / f"event_{order:03d}.mov"
        report_path = work_dir / f"event_{order:03d}.motion.json"
        timeline_path.write_text(json.dumps(timeline, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        command = [
            str(node),
            str(cli),
            "render",
            "--asset-root",
            str(asset_root),
            "--timeline-json",
            str(timeline_path),
            "--output",
            str(output_path),
            "--report",
            str(report_path),
            "--mode",
            "alpha",
        ]
        process = subprocess.run(command, text=True, capture_output=True, check=False)
        if process.returncode != 0 or not output_path.exists():
            failure = {
                **event,
                "error": (process.stderr or process.stdout or "Remotion render failed").strip(),
            }
            result_report["failed"].append(failure)
            if required:
                raise MotionEffectsError(f"Remotion effect failed for {event['material_name']}: {failure['error']}")
            result_report["warnings"].append(
                f"Remotion effect failed for {event['material_name']}; kept static overlay"
            )
            continue
        summary = _probe(output_path)
        index = int(event["material_index"])
        prepared_item = dict(prepared[index])
        prepared_item.update(
            {
                "path": output_path,
                "kind": "video",
                "layout": "motion_alpha",
                "base_layout": event.get("base_layout"),
                "motion_effect": {
                    **event,
                    "clip_duration": summary["duration"],
                    "output_summary": summary,
                },
            }
        )
        prepared[index] = prepared_item
        result_report["rendered"].append(
            {
                **event,
                "output_summary": summary,
            }
        )
    result_report["status"] = "rendered" if result_report["rendered"] else "fallback-static"
    return prepared, result_report
