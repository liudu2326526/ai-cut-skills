from __future__ import annotations

from typing import Any


class AssFontError(ValueError):
    pass


def validate_ass_font_family(value: Any, field: str) -> str:
    family = str(value).strip()
    if not family:
        raise AssFontError(f"{field} must be a non-empty single ASS font family")
    unsafe = {
        ",": "commas split ASS Style fields",
        "\n": "newlines break ASS records",
        "\r": "newlines break ASS records",
        "{": "braces start ASS override blocks",
        "}": "braces end ASS override blocks",
        "\\": "backslashes start ASS override tags",
    }
    for character, reason in unsafe.items():
        if character in family:
            raise AssFontError(
                f"{field} must be one exact font family name, not a fallback list or ASS expression; "
                f"invalid character {character!r}: {reason}"
            )
    return family


def validate_ass_font_config(font_config: dict[str, Any]) -> dict[str, str]:
    if not isinstance(font_config, dict):
        raise AssFontError("font must be an object")
    return {
        "body_family": validate_ass_font_family(
            font_config.get("body_family", ""),
            "font.body_family",
        ),
        "brand_family": validate_ass_font_family(
            font_config.get("brand_family", ""),
            "font.brand_family",
        ),
    }
