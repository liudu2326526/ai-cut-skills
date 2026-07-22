#!/usr/bin/env python3
"""Shared deterministic caption wrapping for preflight, timing, and ASS render."""

from __future__ import annotations

import math
import re
import unicodedata
from functools import lru_cache
from typing import Any


class CaptionLayoutError(ValueError):
    pass


SEMANTIC_TOKEN_RE = re.compile(
    r"汽水音乐|汽水|"
    r"(?:满\s*)?\d+(?:[.．]\d+)?(?:\s*(?:万?金币|元|块|毛))?|"
    r"[A-Za-z0-9_]+(?:[-'][A-Za-z0-9_]+)*|\s+|.",
    re.DOTALL,
)


def resolve_caption_wrap_policy(
    caption_style: dict[str, Any], canvas_width: int
) -> dict[str, Any]:
    mode = str(caption_style.get("wrap_mode", "balanced_explicit"))
    if mode != "balanced_explicit":
        raise CaptionLayoutError("caption wrap_mode must be balanced_explicit")
    try:
        configured_left = float(caption_style.get("margin_left", 72))
        configured_right = float(caption_style.get("margin_right", 72))
        default_minimum = 96.0 * float(canvas_width) / 1080.0
        minimum_margin = float(
            caption_style.get("minimum_horizontal_margin", default_minimum)
        )
        safety_ratio = float(caption_style.get("width_safety_ratio", 0.92))
        preferred_max_lines = int(caption_style.get("preferred_max_lines", 2))
        max_lines = int(caption_style.get("max_lines", 3))
        outline = float(caption_style.get("outline", 3))
    except (TypeError, ValueError) as exc:
        raise CaptionLayoutError("caption wrapping fields must be numeric") from exc
    if minimum_margin < 0 or configured_left < 0 or configured_right < 0:
        raise CaptionLayoutError("caption horizontal margins must be non-negative")
    if not 0.75 <= safety_ratio <= 1.0:
        raise CaptionLayoutError("caption width_safety_ratio must be between 0.75 and 1.0")
    if not 1 <= preferred_max_lines <= max_lines <= 3:
        raise CaptionLayoutError(
            "caption lines must satisfy 1 <= preferred_max_lines <= max_lines <= 3"
        )
    left = max(configured_left, minimum_margin)
    right = max(configured_right, minimum_margin)
    raw_width = float(canvas_width) - left - right - outline * 2.0
    available_width = raw_width * safety_ratio
    if available_width <= 0:
        raise CaptionLayoutError("caption margins leave no usable horizontal space")
    return {
        "mode": mode,
        "left_margin": left,
        "right_margin": right,
        "minimum_horizontal_margin": minimum_margin,
        "width_safety_ratio": safety_ratio,
        "preferred_max_lines": preferred_max_lines,
        "max_lines": max_lines,
        "available_width": available_width,
    }


def caption_tokens(text: str) -> list[str]:
    value = str(text).replace("．", ".")
    return [match.group(0) for match in SEMANTIC_TOKEN_RE.finditer(value)]


def _visible_text(tokens: list[str]) -> str:
    return re.sub(r"[ \t]+", " ", "".join(tokens)).strip()


def measure_caption_text(text: str, caption_style: dict[str, Any]) -> float:
    font_size = float(caption_style.get("font_size", 70))
    scale_x = float(caption_style.get("scale_x", 100)) / 100.0
    spacing = float(caption_style.get("spacing", 0))
    if font_size <= 0 or scale_x <= 0:
        raise CaptionLayoutError("caption font_size and scale_x must be positive")

    value = str(text)
    brand_indices: set[int] = set()
    for match in re.finditer("汽水音乐|汽水", value):
        brand_indices.update(range(match.start(), match.end()))

    widths: list[float] = []
    for index, char in enumerate(value):
        if char.isspace():
            em = 0.35
        elif index in brand_indices:
            em = 1.05
        elif unicodedata.east_asian_width(char) in {"W", "F", "A"}:
            em = 1.0
        elif char.isascii() and (char.isalpha() or char.isdigit()):
            em = 0.58
        elif char in ".-_/'":
            em = 0.32
        else:
            em = 0.5
        widths.append(font_size * scale_x * em)
    return sum(widths) + max(0, len(widths) - 1) * spacing


def derive_caption_character_budget(
    caption_style: dict[str, Any], canvas_width: int
) -> dict[str, Any]:
    """Calculate one task-level CJK character cap from the active caption style."""

    policy = resolve_caption_wrap_policy(caption_style, canvas_width)
    reference_cjk_width = measure_caption_text("字", caption_style)
    spacing = float(caption_style.get("spacing", 0))
    denominator = reference_cjk_width + spacing
    if denominator <= 0:
        raise CaptionLayoutError(
            "caption font width plus spacing must be positive for character-budget calculation"
        )
    maximum = math.floor(
        (float(policy["available_width"]) + spacing) / denominator
    )
    if maximum < 1:
        raise CaptionLayoutError(
            "caption style leaves room for fewer than one reference CJK character"
        )
    return {
        "calculation": "derived_once_from_caption_style",
        "canvas_width": int(canvas_width),
        "available_width": round(float(policy["available_width"]), 3),
        "reference_cjk_width": round(reference_cjk_width, 3),
        "spacing": round(spacing, 3),
        "max_characters_per_line": int(maximum),
    }


def count_caption_characters(text: str) -> int:
    """Count visible characters for the model-facing semantic line budget."""

    return sum(1 for char in str(text) if not char.isspace())


def _balanced_wrap(
    tokens: list[str],
    caption_style: dict[str, Any],
    available_width: float,
    maximum_lines: int,
) -> list[str]:
    while tokens and tokens[0].isspace():
        tokens = tokens[1:]
    while tokens and tokens[-1].isspace():
        tokens = tokens[:-1]
    if not tokens:
        return []

    total_width = measure_caption_text(_visible_text(tokens), caption_style)
    minimum_lines = max(1, int(math.ceil(total_width / available_width)))
    maximum_lines = min(maximum_lines, len(tokens))

    for line_count in range(minimum_lines, maximum_lines + 1):
        target_width = total_width / line_count

        @lru_cache(maxsize=None)
        def solve(start: int, remaining: int) -> tuple[float, tuple[str, ...]] | None:
            if remaining == 1:
                text = _visible_text(tokens[start:])
                if not text:
                    return None
                width = measure_caption_text(text, caption_style)
                if width > available_width:
                    return None
                return (width - target_width) ** 2, (text,)

            best: tuple[float, tuple[str, ...]] | None = None
            for end in range(start + 1, len(tokens)):
                text = _visible_text(tokens[start:end])
                if not text:
                    continue
                width = measure_caption_text(text, caption_style)
                if width > available_width:
                    break
                tail = solve(end, remaining - 1)
                if tail is None:
                    continue
                whitespace_bonus = -available_width * 0.01 if tokens[end - 1].isspace() else 0.0
                candidate = (
                    (width - target_width) ** 2 + tail[0] + whitespace_bonus,
                    (text, *tail[1]),
                )
                if best is None or candidate[0] < best[0]:
                    best = candidate
            return best

        result = solve(0, line_count)
        if result is not None:
            return list(result[1])

    widest = max(
        (measure_caption_text(token.strip(), caption_style) for token in tokens if token.strip()),
        default=0.0,
    )
    if widest > available_width:
        raise CaptionLayoutError(
            f"caption contains an indivisible semantic unit wider than {available_width:.1f}px"
        )
    raise CaptionLayoutError(
        f"caption requires more than {maximum_lines} lines within {available_width:.1f}px"
    )


def layout_caption_text(
    text: str, caption_style: dict[str, Any], canvas_width: int
) -> dict[str, Any]:
    policy = resolve_caption_wrap_policy(caption_style, canvas_width)
    lines: list[str] = []
    for paragraph in str(text).replace("\r\n", "\n").replace("\r", "\n").split("\n"):
        if not paragraph.strip():
            continue
        remaining = int(policy["max_lines"]) - len(lines)
        if remaining <= 0:
            raise CaptionLayoutError(
                f"caption requires more than {policy['max_lines']} lines"
            )
        lines.extend(
            _balanced_wrap(
                caption_tokens(paragraph),
                caption_style,
                float(policy["available_width"]),
                remaining,
            )
        )
    if not lines:
        raise CaptionLayoutError("caption text is empty after normalization")
    if len(lines) > int(policy["max_lines"]):
        raise CaptionLayoutError(
            f"caption requires more than {policy['max_lines']} lines"
        )
    widths = [measure_caption_text(line, caption_style) for line in lines]
    return {
        "ok": True,
        "lines": lines,
        "line_count": len(lines),
        "line_widths": [round(width, 3) for width in widths],
        "available_width": round(float(policy["available_width"]), 3),
        "left_margin": round(float(policy["left_margin"]), 3),
        "right_margin": round(float(policy["right_margin"]), 3),
        "wrap_mode": str(policy["mode"]),
        "max_lines": int(policy["max_lines"]),
    }
