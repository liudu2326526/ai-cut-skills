#!/usr/bin/env python3
"""Generate one LLM-written description per visual asset and cache it in a Manifest.

The script intentionally stores only ``content_understanding.description`` as
semantic content.  Keywords and recommended-usage fields are not requested or
persisted.  It uses an OpenAI-compatible /chat/completions endpoint configured
through CLI arguments or environment variables, and keeps the existing
Manifest format backward compatible.
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import mimetypes
import os
import subprocess
import tempfile
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp", ".bmp", ".gif", ".tif", ".tiff", ".svg"}
VIDEO_EXTENSIONS = {".mp4", ".mov", ".m4v", ".mkv", ".webm", ".avi"}
DEFAULT_PROMPT_VERSION = "asset-understanding-v1"


class UnderstandingError(RuntimeError):
    pass


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def load_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise UnderstandingError(f"Unable to read JSON: {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise UnderstandingError(f"Expected a JSON object: {path}")
    return value


def atomic_write_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(path.name + ".tmp")
    temp.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temp.replace(path)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def resolve_asset_path(asset_root: Path, relative_path: str) -> Path:
    value = Path(relative_path).expanduser()
    return value.resolve() if value.is_absolute() else (asset_root / value).resolve()


def mime_type(path: Path) -> str:
    return mimetypes.guess_type(path.name)[0] or "application/octet-stream"


def image_data_url(path: Path) -> str:
    encoded = base64.b64encode(path.read_bytes()).decode("ascii")
    return f"data:{mime_type(path)};base64,{encoded}"


def media_duration(asset: dict[str, Any]) -> float:
    media = asset.get("media")
    if isinstance(media, dict):
        try:
            return max(0.0, float(media.get("duration_seconds") or 0.0))
        except (TypeError, ValueError):
            pass
    return 0.0


def extract_video_frames(path: Path, duration: float, max_frames: int) -> list[Path]:
    ffmpeg = shutil_which("ffmpeg")
    if not ffmpeg:
        raise UnderstandingError("ffmpeg is required to sample video assets")
    frame_count = max(1, min(max_frames, 6))
    if duration <= 0:
        timestamps = [0.0]
    elif frame_count == 1:
        timestamps = [min(duration / 2.0, max(0.0, duration - 0.05))]
    else:
        last = max(0.0, duration - 0.05)
        timestamps = [last * index / (frame_count - 1) for index in range(frame_count)]
    temp_dir = Path(tempfile.mkdtemp(prefix="soda_asset_frames_"))
    frames: list[Path] = []
    try:
        for index, timestamp in enumerate(timestamps, start=1):
            output = temp_dir / f"frame_{index:02d}.jpg"
            command = [
                ffmpeg,
                "-hide_banner",
                "-loglevel",
                "error",
                "-y",
                "-ss",
                f"{timestamp:.3f}",
                "-i",
                str(path),
                "-frames:v",
                "1",
                "-vf",
                "scale=1024:-2:force_original_aspect_ratio=decrease",
                str(output),
            ]
            result = subprocess.run(command, text=True, capture_output=True, check=False)
            if result.returncode != 0 or not output.exists():
                raise UnderstandingError(
                    f"Unable to extract video frame from {path}: {(result.stderr or 'ffmpeg failed').strip()}"
                )
            frames.append(output)
        return frames
    except Exception:
        for item in temp_dir.glob("*"):
            item.unlink(missing_ok=True)
        temp_dir.rmdir()
        raise


def shutil_which(name: str) -> str | None:
    # Kept local so the script remains a single, standard-library-only file.
    import shutil

    return shutil.which(name)


def request_json(
    url: str,
    payload: dict[str, Any],
    api_key: str | None,
    *,
    retry_without_response_format: bool = True,
) -> dict[str, Any]:
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    headers = {"Content-Type": "application/json"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    request = urllib.request.Request(url, data=body, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(request, timeout=180) as response:
            value = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        if retry_without_response_format and exc.code in {400, 404, 422} and "response_format" in payload:
            fallback = dict(payload)
            fallback.pop("response_format", None)
            return request_json(url, fallback, api_key, retry_without_response_format=False)
        detail = exc.read().decode("utf-8", errors="replace")
        raise UnderstandingError(f"LLM request failed ({exc.code}): {detail[:500]}") from exc
    except (OSError, json.JSONDecodeError) as exc:
        raise UnderstandingError(f"LLM request failed: {exc}") from exc
    if not isinstance(value, dict):
        raise UnderstandingError("LLM response was not a JSON object")
    return value


def parse_model_description(response: dict[str, Any]) -> str:
    try:
        content = response["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError) as exc:
        raise UnderstandingError("LLM response did not contain choices[0].message.content") from exc
    if isinstance(content, list):
        content = "".join(str(item.get("text", "")) for item in content if isinstance(item, dict))
    text = str(content or "").strip()
    if text.startswith("```"):
        text = text.strip("`").strip()
        if text.startswith("json"):
            text = text[4:].lstrip()
    try:
        parsed = json.loads(text)
        if isinstance(parsed, dict):
            text = str(parsed.get("description", "")).strip()
    except json.JSONDecodeError:
        # A plain-text answer is accepted as a compatibility fallback, but only
        # the description itself is saved in the Manifest.
        pass
    if not text:
        raise UnderstandingError("LLM returned an empty description")
    if len(text) > 2000:
        text = text[:2000].rstrip()
    return text


def build_prompt(asset: dict[str, Any], *, media_kind: str, frame_count: int) -> str:
    category = str(asset.get("category") or "unknown")
    file_name = str(asset.get("file_name") or Path(str(asset.get("relative_path", ""))).name)
    media = asset.get("media") if isinstance(asset.get("media"), dict) else {}
    return (
        '你是短视频素材库的内容理解助手。请只返回 JSON：{"description":"..."}。'
        "不要返回 keywords、recommended_usage、category 或其他字段。"
        "description 必须是一段自然、具体、可检索的中文描述，包含画面主体、场景、正在发生的动作、"
        "界面/物料展示的功能或信息、可见的重要文字，以及适合表达的口播语义。"
        "不要根据文件名臆测画面内容；透明区域不要描述成黑色背景。"
        f"素材类型：{media_kind}；文件名：{file_name}；现有粗分类：{category}；"
        f"媒体信息：{json.dumps(media, ensure_ascii=False)}；视频代表帧数：{frame_count}。"
    )


def analyze_asset(
    asset: dict[str, Any],
    asset_root: Path,
    *,
    endpoint: str,
    model: str,
    api_key: str | None,
    prompt_version: str,
    max_frames: int,
) -> dict[str, Any]:
    relative_path = str(asset.get("relative_path") or "")
    path = resolve_asset_path(asset_root, relative_path)
    if not path.exists():
        raise UnderstandingError(f"Asset not found: {path}")
    suffix = path.suffix.casefold()
    if suffix not in IMAGE_EXTENSIONS and suffix not in VIDEO_EXTENSIONS:
        return {}
    source_fingerprint = sha256_file(path)
    parts: list[dict[str, Any]] = []
    frames: list[Path] = []
    try:
        if suffix in IMAGE_EXTENSIONS:
            parts.append({"type": "image_url", "image_url": {"url": image_data_url(path)}})
            media_kind = "image"
        else:
            frames = extract_video_frames(path, media_duration(asset), max_frames)
            parts.extend({"type": "image_url", "image_url": {"url": image_data_url(frame)}} for frame in frames)
            media_kind = "video"
        prompt = build_prompt(asset, media_kind=media_kind, frame_count=len(frames))
        payload = {
            "model": model,
            "temperature": 0.1,
            "messages": [
                {
                    "role": "user",
                    "content": [{"type": "text", "text": prompt}, *parts],
                }
            ],
            "response_format": {"type": "json_object"},
        }
        response = request_json(endpoint, payload, api_key)
        description = parse_model_description(response)
        return {
            "description": description,
            "status": "ready",
            "model": model,
            "prompt_version": prompt_version,
            "source_fingerprint": source_fingerprint,
            "analyzed_at": utc_now(),
        }
    finally:
        for frame in frames:
            frame.unlink(missing_ok=True)
        if frames:
            frames[0].parent.rmdir()


def should_reuse(existing: Any, source_fingerprint: str, model: str, prompt_version: str) -> bool:
    return (
        isinstance(existing, dict)
        and existing.get("status") == "ready"
        and existing.get("source_fingerprint") == source_fingerprint
        and existing.get("model") == model
        and existing.get("prompt_version") == prompt_version
        and bool(str(existing.get("description") or "").strip())
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--asset-root", type=Path)
    parser.add_argument("--output-manifest", type=Path)
    parser.add_argument("--base-url", default=os.environ.get("OPENAI_BASE_URL", "https://api.openai.com/v1"))
    parser.add_argument("--api-key", default=os.environ.get("OPENAI_API_KEY"))
    parser.add_argument("--model", default=os.environ.get("OPENAI_MODEL"))
    parser.add_argument("--prompt-version", default=DEFAULT_PROMPT_VERSION)
    parser.add_argument("--max-frames", type=int, default=4)
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--limit", type=int)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if not args.model:
        raise SystemExit("--model is required unless OPENAI_MODEL is set")
    if args.max_frames < 1 or args.max_frames > 6:
        raise SystemExit("--max-frames must be between 1 and 6")
    manifest_path = args.manifest.expanduser().resolve()
    manifest = load_json(manifest_path)
    asset_root = (args.asset_root or Path(str(manifest.get("asset_root") or ""))).expanduser().resolve()
    if not asset_root.is_dir():
        raise SystemExit(f"Asset root not found: {asset_root}")
    assets = manifest.get("assets")
    if not isinstance(assets, list):
        raise SystemExit("Manifest does not contain an assets list")
    output_manifest = (args.output_manifest or manifest_path).expanduser().resolve()
    endpoint = args.base_url.rstrip("/") + "/chat/completions"
    analyzed = reused = skipped = failed = 0
    for asset in assets[: args.limit] if args.limit else assets:
        if not isinstance(asset, dict):
            skipped += 1
            continue
        path = resolve_asset_path(asset_root, str(asset.get("relative_path") or ""))
        if path.suffix.casefold() not in IMAGE_EXTENSIONS | VIDEO_EXTENSIONS:
            skipped += 1
            continue
        try:
            source_fingerprint = sha256_file(path)
            if not args.force and should_reuse(
                asset.get("content_understanding"), source_fingerprint, args.model, args.prompt_version
            ):
                reused += 1
                continue
            asset["content_understanding"] = analyze_asset(
                asset,
                asset_root,
                endpoint=endpoint,
                model=args.model,
                api_key=args.api_key,
                prompt_version=args.prompt_version,
                max_frames=args.max_frames,
            )
            analyzed += 1
        except (OSError, UnderstandingError, ValueError) as exc:
            failed += 1
            asset["content_understanding"] = {
                "status": "failed",
                "error": str(exc),
                "model": args.model,
                "prompt_version": args.prompt_version,
                "analyzed_at": utc_now(),
            }
    manifest["content_understanding"] = {
        "description_only": True,
        "last_run_at": utc_now(),
        "model": args.model,
        "prompt_version": args.prompt_version,
    }
    atomic_write_json(output_manifest, manifest)
    print(
        json.dumps(
            {
                "ok": failed == 0,
                "manifest": str(output_manifest),
                "analyzed": analyzed,
                "reused": reused,
                "skipped": skipped,
                "failed": failed,
                "description_only": True,
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0 if failed == 0 else 2


if __name__ == "__main__":
    raise SystemExit(main())
