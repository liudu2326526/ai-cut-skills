"""Metadata validation for model-selected special material matches.

The executing model remains responsible for understanding narration, inspecting
the current visual asset, and choosing the match.  This module intentionally does
not validate file hashes or infer matches from narration text.
"""

from __future__ import annotations

from typing import Any


WITHDRAW_0_3_RULE_ID = "withdraw_0_3"
KNOWN_SPECIAL_MATCH_RULES = {WITHDRAW_0_3_RULE_ID}


def special_match_metadata_errors(materials: Any) -> list[str]:
    """Validate only explicit rule declarations; do not infer matches from text."""
    if not isinstance(materials, list):
        return []
    errors: list[str] = []
    for index, material in enumerate(materials):
        if not isinstance(material, dict):
            continue
        rule_id = str(material.get("special_match_rule", "")).strip()
        if rule_id and rule_id not in KNOWN_SPECIAL_MATCH_RULES:
            errors.append(
                f"materials[{index}].special_match_rule is unknown: {rule_id}"
            )
    return errors
