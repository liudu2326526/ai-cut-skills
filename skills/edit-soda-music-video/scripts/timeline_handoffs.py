#!/usr/bin/env python3
"""Validate caption-aligned, half-open material intervals."""

from __future__ import annotations

from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from typing import Any


TIMELINE_PRECISION = Decimal("0.000001")
DEFAULT_SEQUENCE_ID = "continuous-materials"


class TimelineHandoffError(ValueError):
    pass


def _seconds(value: Any, location: str) -> Decimal:
    try:
        result = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise TimelineHandoffError(f"{location} must be a finite number") from exc
    if not result.is_finite():
        raise TimelineHandoffError(f"{location} must be a finite number")
    return result


def _tick(value: Decimal) -> Decimal:
    return value.quantize(TIMELINE_PRECISION, rounding=ROUND_HALF_UP)


def _display(value: Decimal) -> str:
    return f"{value:.6f}".rstrip("0").rstrip(".") or "0"


def mapped_time_decimal(
    value: Any,
    config: dict[str, Any],
    mode_override: str | None = None,
    *,
    location: str = "timeline time",
) -> Decimal:
    original = _seconds(value, location)
    if original < 0:
        raise TimelineHandoffError(f"{location} must be non-negative")
    mode = str(mode_override or config.get("time_mode", "original"))
    speed = _seconds(config.get("speed", 1.1), "speed")
    if speed <= 0:
        raise TimelineHandoffError("speed must be greater than zero")
    if mode == "output":
        return _tick(original)
    if mode == "input":
        return _tick(original / speed)
    if mode != "original":
        raise TimelineHandoffError(f"Unsupported time_mode: {mode}")

    mapped_original = original
    removed = Decimal("0")
    for index, raw_range in enumerate(config.get("removed_ranges", [])):
        if not isinstance(raw_range, (list, tuple)) or len(raw_range) != 2:
            raise TimelineHandoffError(f"removed_ranges[{index}] must contain [start, end]")
        start = _seconds(raw_range[0], f"removed_ranges[{index}][0]")
        end = _seconds(raw_range[1], f"removed_ranges[{index}][1]")
        if start < 0 or end <= start:
            raise TimelineHandoffError(
                f"removed_ranges[{index}] must use non-negative start and end > start"
            )
        if mapped_original >= end:
            removed += end - start
            continue
        if mapped_original > start:
            mapped_original = start
        break
    return _tick(max(Decimal("0"), mapped_original - removed) / speed)


def map_timeline_time(
    value: Any,
    config: dict[str, Any],
    mode_override: str | None = None,
) -> float:
    return float(mapped_time_decimal(value, config, mode_override))


def validate_material_handoffs(config: dict[str, Any]) -> dict[str, Any]:
    materials = config.get("materials", [])
    captions = config.get("captions", [])
    if not isinstance(materials, list):
        raise TimelineHandoffError("materials must be a list")
    if not isinstance(captions, list):
        raise TimelineHandoffError("captions must be a list")

    caption_starts: set[Decimal] = set()
    caption_boundaries: set[Decimal] = set()
    for index, caption in enumerate(captions):
        if not isinstance(caption, dict):
            raise TimelineHandoffError(f"captions[{index}] must be an object")
        mode = str(caption.get("time_mode") or config.get("time_mode", "original"))
        try:
            start = mapped_time_decimal(
                caption["start"],
                config,
                mode,
                location=f"captions[{index}].start",
            )
            end = mapped_time_decimal(
                caption["end"],
                config,
                mode,
                location=f"captions[{index}].end",
            )
        except KeyError as exc:
            raise TimelineHandoffError(
                f"captions[{index}] is missing required field: {exc.args[0]}"
            ) from exc
        if end <= start:
            raise TimelineHandoffError(f"captions[{index}] must use end > start")
        caption_starts.add(start)
        caption_boundaries.update((start, end))

    prepared: list[dict[str, Any]] = []
    for index, material in enumerate(materials):
        if not isinstance(material, dict):
            raise TimelineHandoffError(f"materials[{index}] must be an object")
        mode = str(material.get("time_mode") or config.get("time_mode", "original"))
        try:
            start = mapped_time_decimal(
                material["start"],
                config,
                mode,
                location=f"materials[{index}].start",
            )
            end = mapped_time_decimal(
                material["end"],
                config,
                mode,
                location=f"materials[{index}].end",
            )
        except KeyError as exc:
            raise TimelineHandoffError(
                f"materials[{index}] is missing required field: {exc.args[0]}"
            ) from exc
        if end <= start:
            raise TimelineHandoffError(f"materials[{index}] must use end > start")
        sequence_id = str(material.get("sequence_id") or DEFAULT_SEQUENCE_ID).strip()
        if not sequence_id:
            raise TimelineHandoffError(f"materials[{index}].sequence_id must not be empty")
        prepared.append(
            {
                "index": index,
                "name": str(material.get("name") or f"materials[{index}]"),
                "sequence_id": sequence_id,
                "start": start,
                "end": end,
            }
        )

    if prepared and not caption_boundaries:
        raise TimelineHandoffError(
            "materials require captions so every material boundary can align to a caption switch"
        )

    prepared.sort(key=lambda item: (item["start"], item["end"], item["index"]))
    errors: list[str] = []
    for item in prepared:
        for field in ("start", "end"):
            value = item[field]
            if value not in caption_boundaries:
                errors.append(
                    f"materials[{item['index']}].{field}={_display(value)} is not a caption boundary"
                )

    handoff_count = 0
    sequence_ids: list[str] = []
    seen_sequences: set[str] = set()
    closed_sequences: set[str] = set()
    active_sequence: str | None = None
    for item in prepared:
        sequence_id = item["sequence_id"]
        if sequence_id != active_sequence:
            if active_sequence is not None:
                closed_sequences.add(active_sequence)
            if sequence_id in closed_sequences:
                errors.append(
                    f"sequence_id={sequence_id!r} is split into multiple non-contiguous blocks"
                )
            active_sequence = sequence_id
        if sequence_id not in seen_sequences:
            seen_sequences.add(sequence_id)
            sequence_ids.append(sequence_id)

    for previous, current in zip(prepared, prepared[1:]):
        if previous["end"] > current["start"]:
            errors.append(
                f"materials[{previous['index']}] overlaps materials[{current['index']}] "
                f"at {_display(current['start'])}-{_display(previous['end'])}"
            )
            continue
        same_sequence = previous["sequence_id"] == current["sequence_id"]
        if same_sequence and previous["end"] != current["start"]:
            errors.append(
                f"materials[{previous['index']}].end={_display(previous['end'])} must exactly equal "
                f"materials[{current['index']}].start={_display(current['start'])}; "
                "transition buffers and gaps are forbidden inside one sequence"
            )
            continue
        if previous["end"] == current["start"]:
            handoff_count += 1
            if current["start"] not in caption_starts:
                errors.append(
                    f"material handoff at {_display(current['start'])} must equal a caption start"
                )

    if errors:
        raise TimelineHandoffError("; ".join(errors))

    return {
        "ok": True,
        "interval_semantics": "half-open-[start,end)",
        "timestamp_precision_seconds": float(TIMELINE_PRECISION),
        "material_count": len(prepared),
        "sequence_count": len(sequence_ids),
        "sequence_ids": sequence_ids,
        "handoff_count": handoff_count,
        "caption_aligned": True,
        "seamless_within_sequence": True,
    }
