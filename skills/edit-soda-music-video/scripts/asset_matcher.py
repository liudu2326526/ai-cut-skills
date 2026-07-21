#!/usr/bin/env python3
"""Match a spoken query against cached asset descriptions without a vector store."""

from __future__ import annotations

import argparse
import json
import os
import re
import urllib.error
import urllib.request
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any


class MatcherError(RuntimeError):
    pass


def load_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise MatcherError(f"Unable to read JSON: {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise MatcherError(f"Expected a JSON object: {path}")
    return value


def normalize(value: str) -> str:
    return re.sub(r"\s+", "", str(value)).casefold()


def ngrams(value: str) -> set[str]:
    text = normalize(value)
    grams: set[str] = set()
    for size in (2, 3):
        grams.update(text[index : index + size] for index in range(max(0, len(text) - size + 1)))
    return grams


def lexical_score(query: str, description: str) -> float:
    query_text = normalize(query)
    description_text = normalize(description)
    if not query_text or not description_text:
        return 0.0
    overlap = len(ngrams(query_text) & ngrams(description_text)) / max(1, len(ngrams(query_text)))
    similarity = SequenceMatcher(None, query_text, description_text).ratio()
    return min(1.0, 0.7 * overlap + 0.3 * similarity)


def request_json(url: str, payload: dict[str, Any], api_key: str | None) -> dict[str, Any]:
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    headers = {"Content-Type": "application/json"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    request = urllib.request.Request(url, data=body, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(request, timeout=120) as response:
            value = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise MatcherError(f"LLM request failed ({exc.code}): {detail[:500]}") from exc
    except (OSError, json.JSONDecodeError) as exc:
        raise MatcherError(f"LLM request failed: {exc}") from exc
    if not isinstance(value, dict):
        raise MatcherError("LLM response was not a JSON object")
    return value


def parse_matches(response: dict[str, Any], allowed_paths: set[str]) -> list[dict[str, Any]]:
    try:
        content = response["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError) as exc:
        raise MatcherError("LLM response did not contain choices[0].message.content") from exc
    text = str(content or "").strip().strip("`").strip()
    if text.startswith("json"):
        text = text[4:].lstrip()
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError as exc:
        raise MatcherError(f"LLM matching response was not valid JSON: {exc}") from exc
    raw_matches = parsed.get("matches", []) if isinstance(parsed, dict) else []
    if not isinstance(raw_matches, list):
        return []
    result: list[dict[str, Any]] = []
    for item in raw_matches:
        if not isinstance(item, dict) or str(item.get("path")) not in allowed_paths:
            continue
        try:
            score = max(0.0, min(1.0, float(item.get("score", 0.0))))
        except (TypeError, ValueError):
            score = 0.0
        result.append(
            {
                "path": str(item["path"]),
                "score": score,
                "reason": str(item.get("reason", "")).strip(),
            }
        )
    return result


def call_llm(
    query: str,
    candidates: list[dict[str, Any]],
    *,
    base_url: str,
    model: str,
    api_key: str | None,
) -> list[dict[str, Any]]:
    candidate_text = "\n".join(
        f"[{index}] path={item['path']}\ndescription={item['description']}"
        for index, item in enumerate(candidates, start=1)
    )
    prompt = (
        "你是素材语义匹配助手。根据口播查询，从候选素材的 description 中选择最匹配的素材。"
        "只能选择候选中已有的 path，不要根据文件名臆测内容。"
        "只返回 JSON：{\"matches\":[{\"path\":\"...\",\"score\":0.0,\"reason\":\"...\"}]}。"
        "按匹配度从高到低排序，最多返回 5 个。"
        f"\n口播查询：{query}\n候选素材：\n{candidate_text}"
    )
    payload = {
        "model": model,
        "temperature": 0.0,
        "messages": [{"role": "user", "content": prompt}],
        "response_format": {"type": "json_object"},
    }
    try:
        response = request_json(base_url.rstrip("/") + "/chat/completions", payload, api_key)
    except MatcherError:
        payload.pop("response_format", None)
        response = request_json(base_url.rstrip("/") + "/chat/completions", payload, api_key)
    return parse_matches(response, {str(item["path"]) for item in candidates})


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--query", required=True)
    parser.add_argument("--output-json", type=Path, required=True)
    parser.add_argument("--kind")
    parser.add_argument("--category")
    parser.add_argument("--max-candidates", type=int, default=20)
    parser.add_argument("--no-llm", action="store_true")
    parser.add_argument("--base-url", default=os.environ.get("OPENAI_BASE_URL", "https://api.openai.com/v1"))
    parser.add_argument("--api-key", default=os.environ.get("OPENAI_API_KEY"))
    parser.add_argument("--model", default=os.environ.get("OPENAI_MODEL"))
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.max_candidates < 1:
        raise SystemExit("--max-candidates must be positive")
    manifest = load_json(args.manifest.expanduser().resolve())
    raw_assets = manifest.get("assets", [])
    if not isinstance(raw_assets, list):
        raise SystemExit("Manifest does not contain an assets list")
    candidates: list[dict[str, Any]] = []
    for asset in raw_assets:
        if not isinstance(asset, dict):
            continue
        understanding = asset.get("content_understanding")
        if not isinstance(understanding, dict) or understanding.get("status") != "ready":
            continue
        description = str(understanding.get("description") or "").strip()
        if not description:
            continue
        if args.kind and str(asset.get("kind")) != args.kind:
            continue
        if args.category and str(asset.get("category")) != args.category:
            continue
        path = str(asset.get("relative_path") or "")
        candidates.append(
            {
                "path": path,
                "description": description,
                "kind": asset.get("kind"),
                "category": asset.get("category"),
                "lexical_score": lexical_score(args.query, description),
            }
        )
    candidates.sort(key=lambda item: float(item["lexical_score"]), reverse=True)
    candidates = candidates[: args.max_candidates]
    if not candidates:
        output = {"ok": True, "query": args.query, "matching_method": "description_only", "matches": []}
        args.output_json.expanduser().resolve().write_text(
            json.dumps(output, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        print(json.dumps(output, ensure_ascii=False, indent=2))
        return 0

    method = "lexical_description_fallback"
    matches: list[dict[str, Any]]
    if args.no_llm:
        matches = [
            {
                "path": item["path"],
                "score": round(float(item["lexical_score"]), 4),
                "reason": "description text overlap fallback",
            }
            for item in candidates
        ]
    else:
        if not args.model:
            raise SystemExit("--model is required unless OPENAI_MODEL is set; use --no-llm for offline matching")
        matches = call_llm(
            args.query,
            candidates,
            base_url=args.base_url,
            model=args.model,
            api_key=args.api_key,
        )
        method = "llm_description_match"
    by_path = {item["path"]: item for item in candidates}
    for item in matches:
        source = by_path.get(item["path"], {})
        item["description"] = source.get("description", "")
        item["kind"] = source.get("kind")
        item["category"] = source.get("category")
    output = {
        "ok": True,
        "query": args.query,
        "matching_method": method,
        "description_only": True,
        "candidate_count": len(candidates),
        "matches": matches,
        "selected": matches[0] if matches else None,
    }
    output_path = args.output_json.expanduser().resolve()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(output, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(output, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
