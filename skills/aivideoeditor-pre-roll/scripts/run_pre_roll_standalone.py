#!/usr/bin/env python3
"""Standalone pre-roll video runner.

This script does not import the AIVideoEditor backend.  It can produce a local
MP4 with FFmpeg, optional local TTS, optional Ark/Seedance video generation,
safe-area subtitles, a visual-only disclaimer, and an optional caller-provided
logo.
"""

from __future__ import annotations

import argparse
import base64
import json
import math
import os
import platform
import random
import re
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
import uuid
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

from pre_roll_asset_manifest import (
    DEFAULT_MANIFEST_NAME as DEFAULT_ASSET_MANIFEST_NAME,
    ManifestError,
    validate_manifest_for_paths,
)


SKILL_ROOT = Path(__file__).resolve().parents[1]
BUNDLED_MATERIAL_ROOT = SKILL_ROOT / "assets" / "汽水物料-新"
DEFAULT_OUTPUT_DIR = Path.cwd() / "pre_roll_outputs"
DEFAULT_DISCLAIMER = "本视频为广告创意\n具体奖励金额以实际情况为准"
DEFAULT_BODY_FONT_NAME = "FZLanTingHeiS-DB1-GB"
DEFAULT_BRAND_FONT_NAME = "Soda Font"
DEFAULT_BRAND_SUBTITLE_COLOR = "&H0042FD3B"
DEFAULT_BRAND_SUBTITLE_OUTLINE_COLOR = "&H00000000"
DEFAULT_BRAND_SUBTITLE_SCALE = 1.18
DEFAULT_DISCLAIMER_FONT_NAME = "Microsoft YaHei"
DEFAULT_SUBTITLE_BRAND_TERMS = ("汽水音乐", "汽水")
FORBIDDEN_COPY_TERMS = ("红包", "花不完")
DEFAULT_SUBTITLE_BRAND_LOGO_WIDTH_RATIO = 0.18
DEFAULT_SUBTITLE_BRAND_LOGO_GAP_RATIO = 0.018
VISUAL_COMMON_NEGATIVE = (
    "不要出现任何文字、字幕、Logo、水印（包括 AI 生成水印）、品牌、UI 界面、按钮、二维码、"
    "清晰真人脸、真人露脸、擦边、纹身、知名 IP、影视剧、车牌、涉军涉政、箭头图标等元素。"
)

TERMINAL_ARK_STATUSES = {"completed", "failed", "cancelled", "canceled"}

VISUAL_SCENES: Dict[str, List[str]] = {
    "decompression": [
        "肥皂切割特写",
        "动力沙缓慢切割",
        "彩色史莱姆揉捏拉伸",
        "液压机压碎彩色物体",
        "果冻切割",
        "蜡烛切片",
        "热刀切黄油",
        "彩色液体缓慢混合",
        "酒精墨水扩散",
        "沙画流动",
        "齿轮机械循环运动",
        "滚珠迷宫缓慢滚动",
    ],
    "scenery": [
        "清晨山谷云雾缓慢流动",
        "海浪反复冲刷沙滩纹理",
        "森林溪流穿过鹅卵石",
        "日落海岸线与缓慢移动的云层",
        "湖面微风波纹和远处山影",
        "雨后城市街道路面反光",
    ],
    "gold_reward": [
        "金币缓慢落下，通用奖励卡片轻微浮动",
        "金色进度条逐步填满，金币图标连续点亮",
        "金色数字从小到大滚动，背景是干净的金币纹理",
        "通用福利卡片翻转，显示金币增长和任务完成状态",
    ],
    "chinese_fortune": [
        "红金国风祥云、元宝和金币组成喜庆福利画面",
        "锦鲤穿过金色水纹，旁边出现通用领取卡片",
        "红金灯笼和金币雨形成发财氛围背景",
    ],
    "pet_funny": [
        "可爱猫咪看向通用奖励弹窗，画面轻松干净",
        "小狗歪头看着金币增长浮层",
        "宠物坐在沙发上听到提示音后做出好奇反应",
    ],
    "ai_lifestyle": [
        "成年用户在明亮客厅里戴耳机听音乐，只拍背影或手部局部，画面自然干净",
        "成年用户在通勤路上轻松听音乐，只拍侧影或局部，旁边有通用福利卡片",
        "成年用户在办公室休息区听歌放松，不露清晰正脸，画面明亮自然",
    ],
    "ai_beauty_image": [
        "成年女性在明亮咖啡店戴耳机听音乐，只拍背影或侧影，生活方式广告感",
        "成年女性在居家客厅戴耳机听歌，不露清晰正脸，画面温暖干净",
        "成年女性在阳光窗边听音乐，只拍手部和半身侧影，旁边有轻量福利浮层",
    ],
}

VISUAL_PROMPTS: Dict[str, str] = {
    "decompression": (
        "生成一段高质量、循环感强、适合作为短视频背景的 ASMR 解压视频。"
        "场景：{scene}。要求画面主体居中，特写镜头，光线柔和，细节丰富，动作连续自然，"
        "节奏舒缓。画面干净简洁，无人物对镜讲话，无剧情，无剧烈切换，不出现文字、字幕、"
        "Logo、水印、品牌、UI、按钮、二维码、金币、现金奖励提示、到账、App 页面等元素，方便后期叠加字幕和配音。"
        + VISUAL_COMMON_NEGATIVE
    ),
    "scenery": (
        "生成一段高质量风景类短视频背景。场景：{scene}。画面真实自然、干净明亮、镜头运动平稳，"
        "不要出现人物口播、讲解、品牌、Logo、水印、字幕、App 页面、UI 按钮、二维码、金币、现金奖励提示或到账元素。"
        + VISUAL_COMMON_NEGATIVE
    ),
    "gold_reward": (
        "生成一段短视频广告风格的金色福利背景。场景：{scene}。突出金币、进度条、任务卡片、数字增长等通用视觉元素，"
        "如果出现金币到账数字，单次大额和多次累计都必须小于 5 万金币。"
        "不要复刻具体 App，不要出现真人口播、二维码、手机号、银行卡号、具体品牌 Logo 或外部水印。"
        + VISUAL_COMMON_NEGATIVE
    ),
    "chinese_fortune": (
        "生成一段国风发财氛围的短视频前贴背景。场景：{scene}。红金色喜庆、干净不杂乱，"
        "可以出现通用福利卡片和进度元素，但不要出现具体品牌页面、二维码、手机号、银行卡号、Logo 或水印。"
        + VISUAL_COMMON_NEGATIVE
    ),
    "pet_funny": (
        "生成一段轻松趣味的萌宠短视频背景。场景：{scene}。画面可爱、干净、节奏轻松，"
        "不要出现人物口播、讲解、对口型、二维码、手机号、银行卡号、具体品牌 Logo 或水印。"
        + VISUAL_COMMON_NEGATIVE
    ),
    "ai_lifestyle": (
        "生成一段短视频广告风格的生活方式背景。场景：{scene}。成年人物只用背影、侧影、手部或生活局部出镜，动作轻微，"
        "不露清晰正脸，不讲话、不讲解、不对口型，不展示具体手机品牌界面，不出现二维码、手机号、银行卡号、具体品牌 Logo 或水印。"
        + VISUAL_COMMON_NEGATIVE
    ),
    "ai_beauty_image": (
        "生成一段适合前贴底片的生活方式画面。场景：{scene}。人物必须是成年女性，只拍背影、侧影、手部或生活局部，"
        "不露清晰正脸，日常得体穿着，不暴露、不性感化，不直播、不带货、不对口型，不出现二维码、手机号、银行卡号、具体品牌 Logo 或水印。"
        + VISUAL_COMMON_NEGATIVE
    ),
}


class RunnerError(RuntimeError):
    pass


def require_binary(name: str, explicit_path: Optional[str] = None) -> str:
    if explicit_path:
        path = Path(explicit_path).expanduser()
        if path.exists():
            return str(path)
        raise RunnerError(f"{name} not found: {path}")
    found = shutil.which(name)
    if not found:
        raise RunnerError(f"Required binary not found: {name}. Install FFmpeg or pass --{name}.")
    return found


def run(command: List[str], *, label: str, capture: bool = False) -> subprocess.CompletedProcess[str]:
    print(f"[{label}] " + " ".join(command))
    result = subprocess.run(
        command,
        text=True,
        stdout=subprocess.PIPE if capture else None,
        stderr=subprocess.PIPE if capture else None,
        check=False,
    )
    if result.returncode != 0:
        output = "\n".join(part for part in (result.stdout, result.stderr) if part)
        raise RunnerError(f"{label} failed with exit code {result.returncode}:\n{output}")
    return result


def load_json_file(path: Optional[str]) -> Dict[str, Any]:
    if not path:
        return {}
    resolved = Path(path).expanduser().resolve()
    if not resolved.exists():
        raise RunnerError(f"Config file not found: {resolved}")
    value = json.loads(resolved.read_text(encoding="utf-8-sig"))
    if not isinstance(value, dict):
        raise RunnerError("Config file root must be a JSON object")
    return value


def parse_json_object(raw: Optional[str], label: str) -> Dict[str, Any]:
    if not raw:
        return {}
    try:
        value = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise RunnerError(f"{label} is not valid JSON: {exc}") from exc
    if not isinstance(value, dict):
        raise RunnerError(f"{label} must be a JSON object")
    return value


def _parse_string_list(raw: Any) -> List[str]:
    if not raw:
        return []
    if isinstance(raw, list):
        parts = raw
    else:
        parts = str(raw).replace("，", ",").replace("|", ",").split(",")

    values: List[str] = []
    for part in parts:
        clean = str(part or "").strip()
        if clean:
            values.append(clean)
    return list(dict.fromkeys(values))


def clamp_float(value: Any, default: float, minimum: float, maximum: float) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        number = default
    return max(minimum, min(maximum, number))


def merge_dict(base: Dict[str, Any], patch: Dict[str, Any]) -> Dict[str, Any]:
    result = dict(base)
    for key, value in patch.items():
        if value is None:
            continue
        if isinstance(value, dict) and isinstance(result.get(key), dict):
            result[key] = merge_dict(result[key], value)
        else:
            result[key] = value
    return result


def arg_value(args: argparse.Namespace, key: str, default: Any = None) -> Any:
    value = getattr(args, key, None)
    return default if value is None else value


def ffprobe_duration(ffprobe_bin: str, path: Path) -> Optional[float]:
    if not path.exists():
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


def clamp_subtitle_offset(offset: float, duration: float, max_auto_offset: float) -> float:
    # 字幕可以整体提前一点或延后一段，但不能把整条时间轴推到视频外面。
    lower = -1.0
    upper = max(0.0, min(float(max_auto_offset), float(duration) - 0.45))
    return max(lower, min(float(offset), upper))


def detect_audio_leading_silence(
    *,
    ffmpeg_bin: str,
    audio_path: Path,
    threshold_db: float,
    min_silence_seconds: float,
    max_auto_offset: float,
    duration: float,
) -> Dict[str, Any]:
    # 用 FFmpeg 检测音频开头的静音，字幕默认从真正开始说话的位置再出现。
    if not audio_path.exists():
        return {"mode": "auto", "offsetSeconds": 0.0, "reason": "audio file missing"}

    command = [
        ffmpeg_bin,
        "-hide_banner",
        "-nostats",
        "-i",
        str(audio_path),
        "-af",
        f"silencedetect=noise={float(threshold_db):.1f}dB:d={float(min_silence_seconds):.3f}",
        "-f",
        "null",
        "-",
    ]
    result = subprocess.run(
        command,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    if result.returncode != 0:
        return {
            "mode": "auto",
            "offsetSeconds": 0.0,
            "thresholdDb": float(threshold_db),
            "reason": "silencedetect failed; kept subtitles at 0",
        }

    output = "\n".join(part for part in (result.stdout, result.stderr) if part)
    start_match = re.search(r"silence_start:\s*([0-9.]+)", output)
    if not start_match:
        return {
            "mode": "auto",
            "offsetSeconds": 0.0,
            "thresholdDb": float(threshold_db),
            "reason": "audio starts with speech or background sound",
        }

    try:
        silence_start = float(start_match.group(1))
    except ValueError:
        silence_start = 999.0
    if silence_start > 0.08:
        return {
            "mode": "auto",
            "offsetSeconds": 0.0,
            "thresholdDb": float(threshold_db),
            "reason": "first silence is not at the beginning",
        }

    end_match = re.search(r"silence_end:\s*([0-9.]+)", output[start_match.end() :])
    if not end_match:
        return {
            "mode": "auto",
            "offsetSeconds": 0.0,
            "thresholdDb": float(threshold_db),
            "reason": "audio is silent or leading silence did not end",
        }

    raw_offset = float(end_match.group(1))
    offset = clamp_subtitle_offset(raw_offset, duration, max_auto_offset)
    return {
        "mode": "auto",
        "offsetSeconds": round(offset, 3),
        "detectedLeadingSilenceSeconds": round(raw_offset, 3),
        "thresholdDb": float(threshold_db),
        "minSilenceSeconds": float(min_silence_seconds),
        "maxAutoOffsetSeconds": float(max_auto_offset),
        "reason": "shifted main subtitles after detected leading silence",
    }


def resolve_subtitle_audio_sync(
    *,
    ffmpeg_bin: str,
    audio_path: Path,
    audio_detail: Dict[str, Any],
    mode: str,
    manual_offset: Optional[float],
    threshold_db: float,
    max_auto_offset: float,
    duration: float,
) -> Dict[str, Any]:
    normalized = str(mode or "auto").strip().lower()
    if normalized not in {"auto", "off"}:
        raise RunnerError("--subtitle-audio-sync must be auto or off")

    if manual_offset is not None:
        offset = clamp_subtitle_offset(float(manual_offset), duration, max_auto_offset)
        return {
            "mode": "manual",
            "offsetSeconds": round(offset, 3),
            "requestedOffsetSeconds": float(manual_offset),
            "reason": "manual subtitle offset was provided",
        }

    if normalized == "off" or audio_detail.get("mode") == "silent":
        return {
            "mode": normalized,
            "offsetSeconds": 0.0,
            "reason": "subtitle audio sync disabled or silent audio",
        }

    return detect_audio_leading_silence(
        ffmpeg_bin=ffmpeg_bin,
        audio_path=audio_path,
        threshold_db=threshold_db,
        min_silence_seconds=0.05,
        max_auto_offset=max_auto_offset,
        duration=duration,
    )


def probe_mean_luma(ffmpeg_bin: str, path: Path, sample_fps: int = 4) -> Optional[float]:
    if not path.exists():
        return None
    # Sample the full clip at a low frame rate so the logo choice follows the
    # overall brightness of the rendered background, not just the first seconds.
    result = subprocess.run(
        [
            ffmpeg_bin,
            "-hide_banner",
            "-loglevel",
            "error",
            "-i",
            str(path),
            "-vf",
            f"scale=32:32:force_original_aspect_ratio=decrease,fps={sample_fps},format=gray",
            "-f",
            "rawvideo",
            "-",
        ],
        text=False,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    if result.returncode != 0 or not result.stdout:
        return None
    data = result.stdout
    return sum(data) / (255.0 * len(data))


def choose_logo_variant(
    *,
    ffmpeg_bin: str,
    base_video: Path,
    logo_path: Optional[Path],
    logo_light_path: Optional[Path],
    logo_dark_path: Optional[Path],
    threshold: float = 0.56,
) -> Dict[str, Any]:
    if logo_path:
        return {
            "mode": "direct",
            "variant": "direct",
            "path": str(logo_path),
            "reason": "explicit logo-path provided",
        }

    if logo_light_path and not logo_light_path.exists():
        raise RunnerError(f"Logo light path not found: {logo_light_path}")
    if logo_dark_path and not logo_dark_path.exists():
        raise RunnerError(f"Logo dark path not found: {logo_dark_path}")

    if logo_light_path and logo_dark_path:
        luma = probe_mean_luma(ffmpeg_bin, base_video)
        if luma is None:
            chosen = logo_dark_path
            variant = "dark"
            reason = "brightness probe failed; fell back to dark logo"
        elif luma >= threshold:
            chosen = logo_dark_path
            variant = "dark"
            reason = f"background is bright ({luma:.3f}); chose dark logo"
        else:
            chosen = logo_light_path
            variant = "light"
            reason = f"background is dark ({luma:.3f}); chose light logo"
        return {
            "mode": "auto",
            "variant": variant,
            "path": str(chosen),
            "luma": round(luma, 4) if luma is not None else None,
            "threshold": threshold,
            "measurement": "full_clip_mean_luma",
            "rule": "bright background -> dark logo; dark background -> light logo",
            "reason": reason,
        }

    if logo_dark_path:
        return {
            "mode": "single",
            "variant": "dark",
            "path": str(logo_dark_path),
            "reason": "only dark logo provided",
        }
    if logo_light_path:
        return {
            "mode": "single",
            "variant": "light",
            "path": str(logo_light_path),
            "reason": "only light logo provided",
        }
    raise RunnerError("Missing logo material. Provide --logo-path, or --logo-light-path / --logo-dark-path.")


def output_size(resolution: str, ratio: str) -> Tuple[int, int]:
    landscape_height = {
        "480p": 480,
        "720p": 720,
        "1080p": 1080,
        "4k": 2160,
        "seedance4k": 2160,
    }.get(str(resolution or "720p").lower(), 720)
    ratio_map = {
        "16:9": (16, 9),
        "9:16": (9, 16),
        "1:1": (1, 1),
        "4:3": (4, 3),
        "3:4": (3, 4),
        "21:9": (21, 9),
    }
    rw, rh = ratio_map.get(str(ratio or "9:16"), (9, 16))
    if rw >= rh:
        height = landscape_height
        width = int(round(height * rw / rh / 2) * 2)
    else:
        width = landscape_height
        height = int(round(width * rh / rw / 2) * 2)
    return max(2, width), max(2, height)


def normalize_visual_type(value: Optional[str]) -> str:
    aliases = {
        "解压": "decompression",
        "解压类": "decompression",
        "风景": "scenery",
        "金币": "gold_reward",
        "金币类型": "gold_reward",
        "发财": "chinese_fortune",
        "国风": "chinese_fortune",
        "宠物": "pet_funny",
        "美女": "ai_beauty_image",
        "生活": "ai_lifestyle",
    }
    normalized = str(value or "decompression").strip()
    return aliases.get(normalized, normalized if normalized in VISUAL_SCENES else "decompression")


def choose_scene(visual_type: str, seed: Optional[str]) -> str:
    rng = random.Random(seed or f"{visual_type}-{time.time_ns()}")
    scenes = VISUAL_SCENES.get(visual_type) or VISUAL_SCENES["decompression"]
    if len(scenes) >= 2 and rng.random() < 0.25:
        left, right = rng.sample(scenes, 2)
        return f"{left}，并融合{right}"
    return rng.choice(scenes)


def build_visual_prompt(visual_type: str, scene: str, override: Optional[str]) -> str:
    def with_safety(prompt: str) -> str:
        prompt = str(prompt or "").strip()
        if not prompt or VISUAL_COMMON_NEGATIVE in prompt:
            return prompt
        return f"{prompt}{VISUAL_COMMON_NEGATIVE}"

    if override:
        return with_safety(override)
    template = VISUAL_PROMPTS.get(visual_type, VISUAL_PROMPTS["decompression"])
    return with_safety(template.format(scene=scene))


def validate_copy_text(text: str, label: str = "scriptText") -> None:
    matched = [term for term in FORBIDDEN_COPY_TERMS if term in str(text or "")]
    if matched:
        raise RunnerError(f"{label} cannot contain: {', '.join(matched)}")


def estimate_text_duration(text: str, minimum: float) -> float:
    chinese_chars = len(re.findall(r"[\u4e00-\u9fff]", text))
    latin_words = len(re.findall(r"[A-Za-z0-9]+", text))
    punctuation = len(re.findall(r"[，。！？,.!?；;：:]", text))
    estimate = chinese_chars * 0.22 + latin_words * 0.36 + punctuation * 0.12 + 0.8
    return max(float(minimum), min(max(estimate, 3.0), 90.0))


def split_text_units(text: str, max_chars: int) -> List[str]:
    cleaned = re.sub(r"\s+", "", text or "").strip()
    if not cleaned:
        return []
    raw_parts = [part for part in re.split(r"([，。！？,.!?；;：:])", cleaned) if part]
    phrases: List[str] = []
    current = ""
    for part in raw_parts:
        current += part
        if part in "，。！？,.!?；;：:" or len(current) >= max_chars:
            phrases.append(current)
            current = ""
    if current:
        phrases.append(current)

    chunks: List[str] = []
    for phrase in phrases:
        while len(phrase) > max_chars:
            chunks.append(phrase[:max_chars])
            phrase = phrase[max_chars:]
        if phrase:
            chunks.append(phrase)
    return chunks or [cleaned]


def ass_time(seconds: float) -> str:
    seconds = max(0.0, float(seconds))
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = int(seconds % 60)
    centis = int(round((seconds - int(seconds)) * 100))
    if centis >= 100:
        secs += 1
        centis -= 100
    return f"{hours:d}:{minutes:02d}:{secs:02d}.{centis:02d}"


def ass_escape(text: str) -> str:
    return str(text or "").replace("\\", "\\\\").replace("{", r"\{").replace("}", r"\}").replace("\n", r"\N")


def ass_inline_color(value: Optional[str], default_value: str) -> str:
    raw = str(value or default_value or "").strip()
    if not raw:
        return "&HFFFFFF&"

    hex_color = raw[1:] if raw.startswith("#") else None
    if hex_color and re.fullmatch(r"[0-9A-Fa-f]{6}", hex_color):
        red, green, blue = hex_color[0:2], hex_color[2:4], hex_color[4:6]
        return f"&H{blue}{green}{red}&".upper()

    match = re.fullmatch(r"&H([0-9A-Fa-f]{6})&?", raw)
    if match:
        return f"&H{match.group(1)}&".upper()

    match = re.fullmatch(r"&H[0-9A-Fa-f]{2}([0-9A-Fa-f]{6})&?", raw)
    if match:
        return f"&H{match.group(1)}&".upper()

    return ass_inline_color(default_value, "&H00FFFFFF")


def ass_escape_with_brand_font(
    text: str,
    body_font_name: str,
    brand_font_name: str,
    *,
    body_color: str = "&H00FFFFFF",
    body_outline_color: str = "&H00000000",
    brand_color: str = DEFAULT_BRAND_SUBTITLE_COLOR,
    brand_outline_color: str = DEFAULT_BRAND_SUBTITLE_OUTLINE_COLOR,
    brand_font_scale: float = DEFAULT_BRAND_SUBTITLE_SCALE,
) -> str:
    raw_text = str(text or "")
    if not raw_text:
        return ""

    pattern = re.compile("|".join(re.escape(term) for term in DEFAULT_SUBTITLE_BRAND_TERMS))
    brand_scale = int(round(clamp_float(brand_font_scale, DEFAULT_BRAND_SUBTITLE_SCALE, 1.0, 2.0) * 100))
    body_inline_color = ass_inline_color(body_color, "&H00FFFFFF")
    body_inline_outline = ass_inline_color(body_outline_color, "&H00000000")
    brand_inline_color = ass_inline_color(brand_color, DEFAULT_BRAND_SUBTITLE_COLOR)
    brand_inline_outline = ass_inline_color(brand_outline_color, DEFAULT_BRAND_SUBTITLE_OUTLINE_COLOR)
    parts: List[str] = []
    cursor = 0
    for match in pattern.finditer(raw_text):
        parts.append(ass_escape(raw_text[cursor:match.start()]))
        # 品牌词单独切成 SodaFont + 绿色，结束后立刻恢复正文样式。
        parts.append(
            f"{{\\fn{brand_font_name}\\fscx{brand_scale}\\fscy{brand_scale}"
            f"\\1c{brand_inline_color}\\3c{brand_inline_outline}}}"
            f"{ass_escape(match.group(0))}"
            f"{{\\fn{body_font_name}\\fscx100\\fscy100\\1c{body_inline_color}\\3c{body_inline_outline}}}"
        )
        cursor = match.end()
    parts.append(ass_escape(raw_text[cursor:]))
    return "".join(parts)


def subtitle_position_config(position: str, width: int, height: int, raw: Dict[str, Any]) -> Dict[str, Any]:
    normalized = str(position or raw.get("position") or "lower_center").strip()
    safe_margin = float(raw.get("safeMarginRatio", 0.12))
    bottom_margin = float(raw.get("bottomMarginRatio", 0.22))
    if normalized == "middle_center":
        alignment, margin_v = 5, 0
    elif normalized == "top_center":
        alignment, margin_v = 8, int(height * safe_margin)
    elif normalized == "bottom_center":
        alignment, margin_v = 2, int(height * 0.10)
    else:
        alignment, margin_v = 2, int(height * bottom_margin)
    return {
        "position": normalized,
        "alignment": alignment,
        "margin_l": int(width * safe_margin),
        "margin_r": int(width * safe_margin),
        "margin_v": margin_v,
    }


def generate_ass(
    *,
    output_path: Path,
    text: str,
    duration: float,
    width: int,
    height: int,
    subtitle_config: Dict[str, Any],
    disclaimer_text: Optional[str],
    disclaimer_config: Dict[str, Any],
    brand_text: Optional[str],
    subtitle_offset: float = 0.0,
) -> Dict[str, Any]:
    font_name = str(subtitle_config.get("fontName") or DEFAULT_BODY_FONT_NAME)
    brand_font_name = str(subtitle_config.get("brandFontName") or DEFAULT_BRAND_FONT_NAME)
    font_size = int(subtitle_config.get("fontSize") or 46)
    max_lines = int(subtitle_config.get("maxLines") or 2)
    max_chars = max(8, int(subtitle_config.get("maxCharsPerLine") or 14) * max(1, max_lines))
    primary_color = str(subtitle_config.get("primaryColor") or subtitle_config.get("PrimaryColour") or "&H00FFFFFF")
    secondary_color = str(subtitle_config.get("secondaryColor") or subtitle_config.get("SecondaryColour") or "&H00FFFFFF")
    outline_color = str(subtitle_config.get("outlineColor") or subtitle_config.get("OutlineColour") or "&H00000000")
    back_color = str(subtitle_config.get("backColor") or subtitle_config.get("BackColour") or "&H00000000")
    brand_primary_color = str(
        subtitle_config.get("brandPrimaryColor")
        or subtitle_config.get("BrandPrimaryColour")
        or DEFAULT_BRAND_SUBTITLE_COLOR
    )
    brand_outline_color = str(
        subtitle_config.get("brandOutlineColor")
        or subtitle_config.get("BrandOutlineColour")
        or DEFAULT_BRAND_SUBTITLE_OUTLINE_COLOR
    )
    brand_font_scale = clamp_float(
        subtitle_config.get("brandFontScale") or subtitle_config.get("BrandFontScale"),
        DEFAULT_BRAND_SUBTITLE_SCALE,
        1.0,
        2.0,
    )
    outline = float(subtitle_config.get("outline", 2))
    shadow = float(subtitle_config.get("shadow", 0))
    pos = subtitle_position_config(str(subtitle_config.get("position") or "lower_center"), width, height, subtitle_config)

    # 警示语和主字幕分开设字体：主字幕继续用方正兰亭，警示语恢复老的清晰白字样式。
    disclaimer_font_name = str(disclaimer_config.get("fontName") or disclaimer_config.get("Fontname") or DEFAULT_DISCLAIMER_FONT_NAME)
    disclaimer_font_size = int(disclaimer_config.get("fontSize") or 22)
    disclaimer_primary_color = str(disclaimer_config.get("primaryColor") or disclaimer_config.get("PrimaryColour") or "&H00FFFFFF")
    disclaimer_secondary_color = str(disclaimer_config.get("secondaryColor") or disclaimer_config.get("SecondaryColour") or "&H00FFFFFF")
    disclaimer_outline_color = str(disclaimer_config.get("outlineColor") or disclaimer_config.get("OutlineColour") or "&H00000000")
    disclaimer_back_color = str(disclaimer_config.get("backColor") or disclaimer_config.get("BackColour") or "&H00000000")
    disclaimer_bold = -1 if bool(disclaimer_config.get("bold") or disclaimer_config.get("Bold")) else 0
    disclaimer_outline = float(disclaimer_config.get("outline", disclaimer_config.get("Outline", 1.4)))
    disclaimer_shadow = int(float(disclaimer_config.get("shadow", disclaimer_config.get("Shadow", 0))))
    disclaimer_margin = int(height * float(disclaimer_config.get("bottomMarginRatio", 0.045)))
    disclaimer_margin_r = int(width * float(disclaimer_config.get("safeMarginRatio", 0.045)))

    lines = [
        "[Script Info]",
        "ScriptType: v4.00+",
        f"PlayResX: {width}",
        f"PlayResY: {height}",
        "ScaledBorderAndShadow: yes",
        "",
        "[V4+ Styles]",
        "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, "
        "Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, "
        "Shadow, Alignment, MarginL, MarginR, MarginV, Encoding",
        (
            f"Style: Main,{font_name},{font_size},{primary_color},{secondary_color},{outline_color},{back_color},"
            f"-1,0,0,0,100,100,0,0,1,{outline},{shadow},{pos['alignment']},"
            f"{pos['margin_l']},{pos['margin_r']},{pos['margin_v']},1"
        ),
        (
            f"Style: Disclaimer,{disclaimer_font_name},{disclaimer_font_size},{disclaimer_primary_color},{disclaimer_secondary_color},"
            f"{disclaimer_outline_color},{disclaimer_back_color},{disclaimer_bold},0,0,0,100,100,0,0,1,"
            f"{disclaimer_outline},{disclaimer_shadow},3,{int(width * 0.04)},{disclaimer_margin_r},{disclaimer_margin},1"
        ),
        (
            f"Style: Brand,{brand_font_name},{int(height * 0.026)},&H00FFFFFF,&H00FFFFFF,&H00000000,&H00000000,"
            f"-1,0,0,0,100,100,0,0,1,1.6,0,7,{int(width * 0.045)},{int(width * 0.04)},{int(height * 0.035)},1"
        ),
        "",
        "[Events]",
        "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text",
    ]

    chunks = split_text_units(text, max_chars)
    total_weight = sum(max(1, len(chunk)) for chunk in chunks) or 1
    cursor = float(subtitle_offset or 0.0)
    available_duration = max(0.45, duration - cursor)
    events: List[Dict[str, Any]] = []
    for index, chunk in enumerate(chunks):
        if index == len(chunks) - 1:
            end = duration
        else:
            share = max(0.75, available_duration * max(1, len(chunk)) / total_weight)
            end = min(duration, cursor + share)
        if end - cursor < 0.45:
            end = min(duration, cursor + 0.45)
        event_start = max(0.0, cursor)
        event_end = max(event_start + 0.05, min(duration, end))
        lines.append(
            f"Dialogue: 5,{ass_time(event_start)},{ass_time(event_end)},Main,,0,0,0,,"
            f"{ass_escape_with_brand_font(chunk, font_name, brand_font_name, body_color=primary_color, body_outline_color=outline_color, brand_color=brand_primary_color, brand_outline_color=brand_outline_color, brand_font_scale=brand_font_scale)}"
        )
        events.append({"start": round(event_start, 3), "end": round(event_end, 3), "text": chunk})
        cursor = end
        if cursor >= duration - 0.05:
            break

    if brand_text:
        lines.append(
            f"Dialogue: 8,{ass_time(0)},{ass_time(duration)},Brand,,0,0,0,,{ass_escape(brand_text)}"
        )
    if disclaimer_text:
        lines.append(
            f"Dialogue: 10,{ass_time(0)},{ass_time(duration)},Disclaimer,,0,0,0,,{ass_escape(disclaimer_text)}"
        )

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return {
        "path": str(output_path),
        "events": events,
        "position": pos["position"],
        "fontName": font_name,
        "brandFontName": brand_font_name,
        "brandPrimaryColor": brand_primary_color,
        "brandOutlineColor": brand_outline_color,
        "brandFontScale": brand_font_scale,
        "fontSize": font_size,
        "subtitleOffsetSeconds": round(float(subtitle_offset or 0.0), 3),
        "disclaimerEnabled": bool(disclaimer_text),
        "disclaimerFontName": disclaimer_font_name,
        "brandTextEnabled": bool(brand_text),
    }


def escape_filter_path(path: Path) -> str:
    value = path.resolve().as_posix()
    value = value.replace(":", r"\:")
    value = value.replace("'", r"\'")
    return value


def normalize_media_input(value: Optional[str]) -> Optional[Path]:
    if not value:
        return None
    path = Path(value).expanduser()
    return path.resolve() if path.is_absolute() else (Path.cwd() / path).resolve()


def normalize_optional_text_path(value: Optional[str]) -> Optional[str]:
    if not value:
        return None
    path = Path(value).expanduser()
    return str(path.resolve() if path.is_absolute() else (Path.cwd() / path).resolve())


def find_first_existing_path(candidates: Iterable[Path]) -> Optional[Path]:
    for candidate in candidates:
        if candidate and candidate.exists():
            return candidate.resolve()
    return None


def find_font_file(filename: str, roots: Iterable[Path]) -> Optional[Path]:
    for root in roots:
        if not root.exists():
            continue
        direct = root / filename
        if direct.exists():
            return direct.resolve()
        try:
            found = next((path for path in root.rglob(filename) if path.is_file()), None)
        except (OSError, StopIteration):
            found = None
        if found:
            return found.resolve()
    return None


def discover_default_font_paths(use_bundled_assets: bool = True) -> Tuple[Optional[Path], Optional[Path]]:
    # 没传字体时，优先用 skill 自带的汽水物料包；没有包时再看当前工作区附近。
    roots = [
        BUNDLED_MATERIAL_ROOT,
        BUNDLED_MATERIAL_ROOT / "汽水字体",
        Path.cwd(),
        Path.cwd().parent,
        Path.cwd().parent.parent,
        SKILL_ROOT,
        SKILL_ROOT.parent,
        SKILL_ROOT.parent.parent,
    ]
    if not use_bundled_assets:
        roots = roots[2:]
    brand_font = find_font_file("SodaFont-Regular.otf", roots)
    body_font = find_first_existing_path(
        filter(
            None,
            (
                find_font_file("方正兰亭中粗黑简体.TTF", roots),
                find_font_file("方正兰亭中黑简体.TTF", roots),
                find_font_file("方正兰亭黑简体.TTF", roots),
                find_font_file("方正兰亭粗黑简体.TTF", roots),
            ),
        )
    )
    return body_font, brand_font


def discover_default_brand_asset_paths(use_bundled_assets: bool = True) -> Tuple[Optional[Path], Optional[Path], Optional[Path]]:
    if not use_bundled_assets or not BUNDLED_MATERIAL_ROOT.exists():
        return None, None, None

    logo_root = BUNDLED_MATERIAL_ROOT / "logo尾帧"
    light_logo = find_first_existing_path(
        [
            logo_root / "汽水logo-白色竖版.png",
        ]
    )
    dark_logo = find_first_existing_path(
        [
            logo_root / "汽水logo-黑色竖版.png",
        ]
    )
    subtitle_icon = find_first_existing_path(
        [
            logo_root / "汽水图标.png",
        ]
    )
    return light_logo, dark_logo, subtitle_icon


def is_within_path(candidate: Optional[Path], root: Path) -> bool:
    if not candidate:
        return False
    try:
        return candidate.resolve().is_relative_to(root.resolve())
    except AttributeError:
        return str(candidate.resolve()).casefold().startswith(str(root.resolve()).casefold())


def prepare_fonts_dir(
    *,
    work_dir: Path,
    fonts_dir: Optional[Path],
    body_font_path: Optional[Path],
    brand_font_path: Optional[Path],
) -> Optional[Path]:
    font_sources: List[Path] = []
    if fonts_dir:
        if not fonts_dir.exists():
            raise RunnerError(f"Fonts dir not found: {fonts_dir}")
        font_sources.extend(
            path
            for path in fonts_dir.rglob("*")
            if path.is_file() and path.suffix.lower() in {".ttf", ".otf", ".ttc"}
        )
    for explicit_path, label in ((body_font_path, "body font"), (brand_font_path, "brand font")):
        if explicit_path:
            if not explicit_path.exists():
                raise RunnerError(f"{label} path not found: {explicit_path}")
            font_sources.append(explicit_path)

    if not font_sources:
        return None

    output_dir = work_dir / "fonts"
    output_dir.mkdir(parents=True, exist_ok=True)
    for index, source in enumerate(font_sources):
        target = output_dir / f"font_{index}{source.suffix.lower()}"
        shutil.copy2(source, target)
    return output_dir


def choose_voice_name(voice_name: Optional[str], seed: Optional[str] = None) -> Optional[str]:
    if not voice_name:
        return None
    candidates = [part.strip() for part in str(voice_name).split("|") if part.strip()]
    if not candidates:
        return None
    if len(candidates) == 1:
        return candidates[0]
    rng = random.Random(seed or f"{voice_name}-{time.time_ns()}")
    return rng.choice(candidates)


def download_url(url: str, destination: Path, timeout: int = 300) -> Path:
    destination.parent.mkdir(parents=True, exist_ok=True)
    request = urllib.request.Request(url, headers={"User-Agent": "AIVideoEditor-PreRoll-Standalone/1.0"})
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response, destination.open("wb") as file:
            shutil.copyfileobj(response, file)
    except urllib.error.URLError as exc:
        raise RunnerError(f"Failed to download {url}: {exc}") from exc
    if not destination.exists() or destination.stat().st_size <= 0:
        raise RunnerError(f"Downloaded file is empty: {destination}")
    return destination


def ark_request_json(method: str, url: str, api_key: str, body: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    data = json.dumps(body, ensure_ascii=False).encode("utf-8") if body is not None else None
    request = urllib.request.Request(
        url,
        data=data,
        method=method,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=60) as response:
            text = response.read().decode("utf-8")
            return json.loads(text) if text else {}
    except urllib.error.HTTPError as exc:
        text = exc.read().decode("utf-8", errors="replace")
        raise RunnerError(f"Ark API error HTTP {exc.code}: {text}") from exc
    except urllib.error.URLError as exc:
        raise RunnerError(f"Ark API request failed: {exc}") from exc


def normalize_ark_status(payload: Dict[str, Any]) -> str:
    raw = str(payload.get("status") or "").lower()
    if raw == "succeeded" or (isinstance(payload.get("content"), dict) and payload["content"].get("video_url")):
        return "completed"
    if raw in {"queued", "running", "failed", "cancelled", "canceled"}:
        return raw
    return raw or "pending"


def generate_seedance_video(
    *,
    api_key: str,
    base_url: str,
    model: str,
    prompt: str,
    duration: int,
    ratio: str,
    resolution: str,
    output_path: Path,
    poll_interval: float,
    timeout_seconds: int,
) -> Dict[str, Any]:
    root = base_url.rstrip("/")
    path = "/contents/generations/tasks"
    ark_resolution = "4k" if resolution == "seedance4k" else resolution
    payload = {
        "model": model,
        "content": [{"type": "text", "text": prompt}],
        "duration": max(4, min(int(duration), 15)),
        "ratio": ratio,
        "resolution": ark_resolution,
        "generate_audio": False,
        "watermark": False,
        "return_last_frame": True,
    }
    created = ark_request_json("POST", f"{root}{path}", api_key, payload)
    task_id = str(created.get("id") or "")
    if not task_id:
        raise RunnerError(f"Ark create response has no id: {created}")

    deadline = time.time() + timeout_seconds
    current = created
    status = normalize_ark_status(current)
    while status not in TERMINAL_ARK_STATUSES and time.time() < deadline:
        time.sleep(poll_interval)
        current = ark_request_json("GET", f"{root}{path}/{task_id}", api_key)
        status = normalize_ark_status(current)
        print(f"[ark] task={task_id} status={status}")
    if status != "completed":
        raise RunnerError(f"Ark task did not complete: status={status}, response={current}")

    content = current.get("content") if isinstance(current.get("content"), dict) else {}
    video_url = str(content.get("video_url") or "").strip()
    if not video_url:
        raise RunnerError(f"Ark task completed but no video_url found: {current}")
    download_url(video_url, output_path)
    return {
        "taskId": task_id,
        "videoUrl": video_url,
        "coverUrl": content.get("last_frame_url"),
        "path": str(output_path),
        "prompt": prompt,
        "request": payload,
    }


def make_base_video(
    *,
    ffmpeg_bin: str,
    background_video: Optional[Path],
    background_image: Optional[Path],
    background_url: Optional[str],
    visual_type: str,
    duration: float,
    width: int,
    height: int,
    output_path: Path,
    work_dir: Path,
) -> Dict[str, Any]:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    if background_url:
        downloaded = download_url(background_url, work_dir / "background_download")
        background_video = downloaded

    scale_crop = (
        f"scale={width}:{height}:force_original_aspect_ratio=increase,"
        f"crop={width}:{height},setsar=1,fps=30,format=yuv420p"
    )
    if background_video:
        if not background_video.exists():
            raise RunnerError(f"Background video not found: {background_video}")
        command = [
            ffmpeg_bin,
            "-hide_banner",
            "-y",
            "-stream_loop",
            "-1",
            "-i",
            str(background_video),
            "-t",
            f"{duration:.3f}",
            "-an",
            "-vf",
            scale_crop,
            "-c:v",
            "libx264",
            "-preset",
            "veryfast",
            "-crf",
            "20",
            "-pix_fmt",
            "yuv420p",
            str(output_path),
        ]
        run(command, label="prepare-background-video")
        return {"type": "background_video", "path": str(background_video)}

    if background_image:
        if not background_image.exists():
            raise RunnerError(f"Background image not found: {background_image}")
        command = [
            ffmpeg_bin,
            "-hide_banner",
            "-y",
            "-loop",
            "1",
            "-i",
            str(background_image),
            "-t",
            f"{duration:.3f}",
            "-an",
            "-vf",
            scale_crop,
            "-c:v",
            "libx264",
            "-preset",
            "veryfast",
            "-crf",
            "20",
            "-pix_fmt",
            "yuv420p",
            str(output_path),
        ]
        run(command, label="prepare-background-image")
        return {"type": "background_image", "path": str(background_image)}

    raise RunnerError(
        "Missing real video content. Provide --background-video, --background-image, "
        "--background-url/--scraped-video-url, or use --asset-strategy generated with --ark-api-key. "
        "Placeholder backgrounds are disabled for pre-roll production."
    )


def generate_local_sapi_tts(text: str, output_path: Path, voice_name: Optional[str]) -> Optional[Path]:
    if platform.system().lower() != "windows":
        return None
    powershell = shutil.which("powershell.exe") or shutil.which("powershell")
    if not powershell:
        return None
    encoded_text = base64.b64encode(text.encode("utf-8")).decode("ascii")
    encoded_output = base64.b64encode(str(output_path).encode("utf-8")).decode("ascii")
    voice_clause = ""
    if voice_name:
        encoded_voice = base64.b64encode(voice_name.encode("utf-8")).decode("ascii")
        voice_clause = (
            f"$voice=[Text.Encoding]::UTF8.GetString([Convert]::FromBase64String('{encoded_voice}'));"
            "try { $synth.SelectVoice($voice) } catch {};"
        )
    script = (
        "Add-Type -AssemblyName System.Speech;"
        f"$text=[Text.Encoding]::UTF8.GetString([Convert]::FromBase64String('{encoded_text}'));"
        f"$out=[Text.Encoding]::UTF8.GetString([Convert]::FromBase64String('{encoded_output}'));"
        "$synth=New-Object System.Speech.Synthesis.SpeechSynthesizer;"
        f"{voice_clause}"
        "$synth.Rate=0;"
        "$synth.Volume=100;"
        "$synth.SetOutputToWaveFile($out);"
        "$synth.Speak($text);"
        "$synth.Dispose();"
    )
    encoded_command = base64.b64encode(script.encode("utf-16le")).decode("ascii")
    result = subprocess.run(
        [powershell, "-NoProfile", "-ExecutionPolicy", "Bypass", "-EncodedCommand", encoded_command],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    if result.returncode != 0 or not output_path.exists() or output_path.stat().st_size <= 0:
        print("[tts] local SAPI TTS failed; fallback to silent audio", file=sys.stderr)
        if result.stderr:
            print(result.stderr, file=sys.stderr)
        return None
    return output_path


def make_audio(
    *,
    ffmpeg_bin: str,
    ffprobe_bin: str,
    script_text: str,
    duration: float,
    voiceover_path: Optional[Path],
    generate_dubbing: bool,
    local_tts: bool,
    voice_name: Optional[str],
    voice_seed: Optional[str],
    output_path: Path,
) -> Dict[str, Any]:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    source_path: Optional[Path] = None
    mode = "silent"
    selected_voice_name = choose_voice_name(voice_name, voice_seed)
    if voiceover_path:
        if not voiceover_path.exists():
            raise RunnerError(f"Voiceover path not found: {voiceover_path}")
        source_path = voiceover_path
        mode = "provided"
    elif generate_dubbing and local_tts:
        source_path = generate_local_sapi_tts(script_text, output_path.with_suffix(".tts.wav"), selected_voice_name)
        if source_path:
            mode = "local_sapi"

    if source_path:
        command = [
            ffmpeg_bin,
            "-hide_banner",
            "-y",
            "-i",
            str(source_path),
            "-t",
            f"{duration:.3f}",
            "-af",
            "loudnorm=I=-16:LRA=7:TP=-1.5,aformat=sample_rates=44100:channel_layouts=stereo",
            "-c:a",
            "pcm_s16le",
            str(output_path),
        ]
        run(command, label="prepare-voiceover")
        audio_duration = ffprobe_duration(ffprobe_bin, output_path) or duration
        return {
            "mode": mode,
            "path": str(output_path),
            "sourcePath": str(source_path),
            "duration": round(audio_duration, 3),
            "voiceName": selected_voice_name if mode == "local_sapi" else None,
        }

    command = [
        ffmpeg_bin,
        "-hide_banner",
        "-y",
        "-f",
        "lavfi",
        "-t",
        f"{duration:.3f}",
        "-i",
        "anullsrc=r=44100:cl=stereo",
        "-c:a",
        "pcm_s16le",
        str(output_path),
    ]
    run(command, label="prepare-silent-audio")
    return {"mode": "silent", "path": str(output_path), "duration": round(duration, 3)}


def overlay_position_expr(position: str, margin_x: int, margin_y: int) -> Tuple[str, str]:
    safe_position = str(position or "top_left").strip().lower().replace("-", "_")
    if safe_position in {"top_center", "center_top"}:
        return "(W-w)/2", str(margin_y)
    if safe_position == "top_right":
        return f"W-w-{margin_x}", str(margin_y)
    if safe_position in {"middle_left", "center_left"}:
        return str(margin_x), "(H-h)/2"
    if safe_position in {"center", "middle_center"}:
        return "(W-w)/2", "(H-h)/2"
    if safe_position in {"middle_right", "center_right"}:
        return f"W-w-{margin_x}", "(H-h)/2"
    if safe_position == "bottom_left":
        return str(margin_x), f"H-h-{margin_y}"
    if safe_position in {"bottom_center", "center_bottom", "lower_center"}:
        return "(W-w)/2", f"H-h-{margin_y}"
    if safe_position in {"bottom_right", "right_bottom", "lower_right"}:
        return f"W-w-{margin_x}", f"H-h-{margin_y}"
    return str(margin_x), str(margin_y)


def overlay_image_on_video(
    *,
    ffmpeg_bin: str,
    input_path: Path,
    image_path: Path,
    output_path: Path,
    position: str,
    margin_x: int,
    margin_y: int,
    overlay_width: int,
    overlay_height: Optional[int],
    opacity: float,
    start_time: float,
    duration: float,
) -> None:
    if not input_path.exists():
        raise RunnerError(f"Video file not found for image overlay: {input_path}")
    if not image_path.exists():
        raise RunnerError(f"Overlay image not found: {image_path}")

    x_expr, y_expr = overlay_position_expr(position, max(0, margin_x), max(0, margin_y))
    overlay_filters: List[str] = []
    if overlay_width and overlay_height:
        overlay_filters.append(
            f"scale={max(1, int(overlay_width))}:{max(1, int(overlay_height))}:force_original_aspect_ratio=decrease"
        )
    elif overlay_width:
        overlay_filters.append(f"scale={max(1, int(overlay_width))}:-1")
    overlay_filters.append("format=rgba")
    safe_opacity = max(0.0, min(1.0, float(opacity)))
    if safe_opacity < 0.999:
        overlay_filters.append(f"colorchannelmixer=aa={safe_opacity:.3f}")

    start = max(0.0, float(start_time or 0.0))
    end = start + max(0.05, float(duration or 0.0))
    filter_complex = (
        f"[1:v]{','.join(overlay_filters)}[ov];"
        f"[0:v][ov]overlay=x={x_expr}:y={y_expr}:eof_action=repeat:format=auto:"
        f"enable='between(t,{start:.3f},{end:.3f})'[v]"
    )
    command = [
        ffmpeg_bin,
        "-hide_banner",
        "-y",
        "-i",
        str(input_path),
        "-i",
        str(image_path),
        "-filter_complex",
        filter_complex,
        "-map",
        "[v]",
        "-map",
        "0:a?",
        "-c:v",
        "libx264",
        "-preset",
        "veryfast",
        "-crf",
        "20",
        "-pix_fmt",
        "yuv420p",
        "-c:a",
        "aac",
        "-movflags",
        "+faststart",
        str(output_path),
    ]
    run(command, label="overlay-subtitle-brand-logo")


def build_subtitle_brand_logo_events(
    *,
    subtitle_events: Iterable[Dict[str, Any]],
    terms: Iterable[str],
    duration: float,
    max_overlays: int = 8,
) -> List[Dict[str, Any]]:
    safe_terms = sorted({term.strip() for term in terms if str(term or "").strip()}, key=len, reverse=True)
    result: List[Dict[str, Any]] = []
    total = max(0.1, float(duration or 0.0))
    for event in subtitle_events:
        if len(result) >= max_overlays:
            break
        text = str(event.get("text") or "")
        matched = [term for term in safe_terms if term in text]
        if not matched:
            continue
        start = max(0.0, min(float(event.get("start") or 0.0), total - 0.05))
        end = max(start + 0.05, min(float(event.get("end") or total), total))
        result.append(
            {
                "matchedText": text,
                "matchedTerms": matched,
                "start": round(start, 3),
                "duration": round(max(0.45, end - start), 3),
            }
        )
    return result


def apply_subtitle_brand_logo_overlays(
    *,
    ffmpeg_bin: str,
    input_path: Path,
    work_dir: Path,
    subtitle_detail: Dict[str, Any],
    subtitle_config: Dict[str, Any],
    fallback_logo_path: Optional[Path],
    duration: float,
    width: int,
    height: int,
    enabled: bool,
    terms: Iterable[str],
    logo_width_ratio: float,
    gap_ratio: float,
    max_overlays: int,
    opacity: float,
) -> Dict[str, Any]:
    if not enabled:
        return {"enabled": False, "path": str(input_path), "events": [], "appliedEvents": [], "reason": "字幕品牌图标已关闭"}

    events = build_subtitle_brand_logo_events(
        subtitle_events=subtitle_detail.get("events") or [],
        terms=terms,
        duration=duration,
        max_overlays=max_overlays,
    )
    if not events:
        return {"enabled": False, "path": str(input_path), "events": [], "appliedEvents": [], "reason": "字幕里没有命中品牌词"}

    logo_path = fallback_logo_path
    if not logo_path or not logo_path.exists():
        return {"enabled": False, "path": str(input_path), "events": events, "appliedEvents": [], "reason": "没有可用的字幕品牌图标素材"}

    pos = subtitle_position_config(str(subtitle_config.get("position") or "lower_center"), width, height, subtitle_config)
    overlay_position_map = {
        "lower_center": "bottom_center",
        "bottom_center": "bottom_center",
        "bottom_left": "bottom_left",
        "bottom_right": "bottom_right",
    }
    overlay_position = overlay_position_map.get(str(pos.get("position") or "lower_center"))
    if not overlay_position:
        return {
            "enabled": False,
            "path": str(input_path),
            "events": events,
            "appliedEvents": [],
            "reason": f"字幕位置 {pos.get('position')} 不在底部区域，暂不叠字幕上方图标",
        }

    overlay_width = max(72, min(int(width * logo_width_ratio), int(width * 0.5)))
    gap = max(6, int(height * gap_ratio))
    font_size = int(subtitle_config.get("fontSize") or 46)
    max_lines = int(subtitle_config.get("maxLines") or 2)
    # overlay 的 margin_y 是“离底部的距离”。把字幕行高算进去，图标才会真的在字幕上方。
    subtitle_block_height = int(font_size * max(1, max_lines) * 1.28)
    margin_y = max(8, int(pos.get("margin_v") or height * 0.22) + subtitle_block_height + gap)
    margin_x = max(8, int(pos.get("margin_l") or width * 0.12))
    overlay_dir = work_dir / "subtitle_brand_logo_overlay"
    overlay_dir.mkdir(parents=True, exist_ok=True)

    current_path = input_path
    applied_events: List[Dict[str, Any]] = []
    for index, event in enumerate(events, start=1):
        output_path = overlay_dir / f"subtitle_logo_{index}.mp4"
        overlay_image_on_video(
            ffmpeg_bin=ffmpeg_bin,
            input_path=current_path,
            image_path=logo_path,
            output_path=output_path,
            position=overlay_position,
            margin_x=margin_x,
            margin_y=margin_y,
            overlay_width=overlay_width,
            overlay_height=overlay_width,
            opacity=opacity,
            start_time=float(event["start"]),
            duration=float(event["duration"]),
        )
        current_path = output_path
        applied_events.append(
            {
                **event,
                "outputPath": str(output_path),
                "assetPath": str(logo_path),
                "position": overlay_position,
                "overlayWidth": overlay_width,
            }
        )

    return {
        "enabled": bool(applied_events),
        "path": str(current_path),
        "events": events,
        "appliedEvents": applied_events,
        "assetPath": str(logo_path),
        "reason": None if applied_events else "命中了品牌词，但字幕上方图标叠加失败",
    }


def compose_final(
    *,
    ffmpeg_bin: str,
    base_video: Path,
    audio_path: Path,
    ass_path: Path,
    fonts_dir: Optional[Path],
    logo_path: Optional[Path],
    output_path: Path,
    duration: float,
    width: int,
    height: int,
) -> Dict[str, Any]:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    subtitle_filter = f"subtitles='{escape_filter_path(ass_path)}'"
    if fonts_dir:
        subtitle_filter = f"{subtitle_filter}:fontsdir='{escape_filter_path(fonts_dir)}'"
    command = [ffmpeg_bin, "-hide_banner", "-y", "-i", str(base_video), "-i", str(audio_path)]
    filter_parts: List[str] = [f"[0:v]{subtitle_filter}[captioned]"]
    map_video = "[captioned]"
    logo_detail: Dict[str, Any] = {"enabled": False}
    if logo_path:
        if not logo_path.exists():
            raise RunnerError(f"Logo path not found: {logo_path}")
        command.extend(["-loop", "1", "-i", str(logo_path)])
        logo_width = max(96, int(width * 0.20))
        margin = max(20, int(width * 0.035))
        filter_parts.append(f"[2:v]scale={logo_width}:-1,format=rgba[logo]")
        filter_parts.append(f"[captioned][logo]overlay=x={margin}:y={margin}:format=auto[vout]")
        map_video = "[vout]"
        logo_detail = {
            "enabled": True,
            "path": str(logo_path),
            "width": logo_width,
            "x": margin,
            "y": margin,
        }

    filter_parts.append("[1:a]aformat=sample_rates=44100:channel_layouts=stereo[aout]")
    command.extend(
        [
            "-filter_complex",
            ";".join(filter_parts),
            "-map",
            map_video,
            "-map",
            "[aout]",
            "-t",
            f"{duration:.3f}",
            "-c:v",
            "libx264",
            "-preset",
            "veryfast",
            "-crf",
            "20",
            "-pix_fmt",
            "yuv420p",
            "-c:a",
            "aac",
            "-b:a",
            "192k",
            "-movflags",
            "+faststart",
            str(output_path),
        ]
    )
    run(command, label="compose-final")
    return {
        "path": str(output_path),
        "logo": logo_detail,
        "fontsDir": str(fonts_dir) if fonts_dir else None,
    }


def extract_cover(ffmpeg_bin: str, video_path: Path, cover_path: Path) -> Optional[str]:
    try:
        run(
            [
                ffmpeg_bin,
                "-hide_banner",
                "-y",
                "-i",
                str(video_path),
                "-frames:v",
                "1",
                "-update",
                "1",
                "-q:v",
                "2",
                str(cover_path),
            ],
            label="extract-cover",
        )
    except RunnerError:
        return None
    return str(cover_path) if cover_path.exists() else None


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run a standalone local pre-roll workflow.")
    parser.add_argument("--config", help="Optional JSON config file. Command-line args override it.")
    parser.add_argument("--script-text", default=None, help="Main spoken copy and subtitle text.")
    parser.add_argument("--prompt-text", default=None, help="Custom visual prompt for AI video generation.")
    parser.add_argument("--visual-template-id", default="decompression")
    parser.add_argument("--asset-strategy", default="generated", choices=("generated", "local_video", "local_image", "scraped"))
    parser.add_argument("--background-video", default=None, help="Local background MP4/MOV. Preferred for backend-free real production.")
    parser.add_argument("--background-image", default=None, help="Local background image. It will be converted to a video background.")
    parser.add_argument("--background-url", default=None, help="Direct downloadable video URL. Used for scraped/simple remote source mode.")
    parser.add_argument("--scraped-video-url", default=None, help="Alias of --background-url for compatibility with the API payload.")
    parser.add_argument("--asset-root", default=None, help="Local asset root used for manifest tracking and preflight checks.")
    parser.add_argument("--asset-manifest", default=None, help=f"Manifest path. Defaults to {DEFAULT_ASSET_MANIFEST_NAME} in the current workspace when omitted.")
    parser.add_argument("--asset-preflight", default=None, choices=("off", "warn", "required"), help="Validate local visual assets against the manifest before rendering.")
    parser.add_argument("--use-bundled-assets", dest="use_bundled_assets", action="store_true", help="Use bundled 汽水物料-新 for default logo/font/icon assets.")
    parser.add_argument("--no-bundled-assets", dest="use_bundled_assets", action="store_false", help="Do not use bundled 汽水物料-新 defaults.")
    parser.set_defaults(use_bundled_assets=True)
    parser.add_argument("--material-selection-json", default=None, help="Optional JSON file describing the chosen overlay/material items to validate semantically.")
    parser.add_argument("--duration", type=float, default=8.0)
    parser.add_argument("--ratio", default="9:16")
    parser.add_argument("--resolution", default="720p")
    parser.add_argument("--subtitle-position", default="lower_center")
    parser.add_argument("--subtitle-font-size", type=int, default=None)
    parser.add_argument("--subtitle-config-json", default=None)
    parser.add_argument("--subtitle-audio-sync", default=None, choices=("auto", "off"), help="Shift main subtitles after detected voiceover leading silence.")
    parser.add_argument("--subtitle-offset-seconds", type=float, default=None, help="Manual main subtitle time offset. Positive delays subtitles; negative shows them earlier.")
    parser.add_argument("--subtitle-speech-threshold-db", type=float, default=None, help="Silence threshold for automatic subtitle sync.")
    parser.add_argument("--subtitle-max-auto-offset-seconds", type=float, default=None, help="Largest automatic subtitle delay allowed.")
    parser.add_argument("--body-font-name", default=None, help="ASS family name for normal subtitle text.")
    parser.add_argument("--brand-font-name", default=None, help="ASS family name for 汽水音乐/汽水 subtitle text.")
    parser.add_argument("--brand-primary-color", default=None, help="ASS/RGB fill color for 汽水音乐/汽水 subtitle text.")
    parser.add_argument("--brand-outline-color", default=None, help="ASS/RGB outline color for 汽水音乐/汽水 subtitle text.")
    parser.add_argument("--brand-font-scale", type=float, default=None, help="Scale for 汽水音乐/汽水 subtitle text, for example 1.18.")
    parser.add_argument("--fonts-dir", default=None, help="Directory containing body and brand font files for FFmpeg fontsdir.")
    parser.add_argument("--body-font-path", default=None, help="方正兰亭 font file path.")
    parser.add_argument("--brand-font-path", default=None, help="SodaFont font file path.")
    parser.add_argument("--include-disclaimer-subtitle", action="store_true", default=True)
    parser.add_argument("--no-include-disclaimer-subtitle", dest="include_disclaimer_subtitle", action="store_false")
    parser.add_argument("--disclaimer-text", default=DEFAULT_DISCLAIMER)
    parser.add_argument("--disclaimer-config-json", default=None)
    parser.add_argument("--brand-text", default="", help="Optional extra top-left text. Do not use it as a logo replacement.")
    parser.add_argument("--logo-path", default=None, help="Caller-provided logo image. Required unless you provide both light and dark variants.")
    parser.add_argument("--logo-light-path", default=None, help="Logo to use on dark backgrounds.")
    parser.add_argument("--logo-dark-path", default=None, help="Logo to use on bright backgrounds.")
    parser.add_argument("--logo-luma-threshold", type=float, default=0.56, help="Mean brightness threshold; brighter backgrounds pick the dark logo.")
    parser.add_argument("--subtitle-logo-enabled", dest="subtitle_logo_enabled", action="store_true")
    parser.add_argument("--no-subtitle-logo-enabled", dest="subtitle_logo_enabled", action="store_false")
    parser.set_defaults(subtitle_logo_enabled=True)
    parser.add_argument("--subtitle-logo-path", default=None, help="Optional icon placed above subtitles when brand terms appear.")
    parser.add_argument("--subtitle-logo-width-ratio", type=float, default=DEFAULT_SUBTITLE_BRAND_LOGO_WIDTH_RATIO, help="Width ratio for the subtitle icon.")
    parser.add_argument("--subtitle-logo-gap-ratio", type=float, default=DEFAULT_SUBTITLE_BRAND_LOGO_GAP_RATIO, help="Extra gap above the subtitle block.")
    parser.add_argument("--subtitle-logo-opacity", type=float, default=1.0, help="Opacity for the subtitle icon.")
    parser.add_argument("--subtitle-logo-max-overlays", type=int, default=8, help="Maximum number of subtitle icon overlays.")
    parser.add_argument("--subtitle-logo-terms", default="汽水音乐|汽水", help="Terms that trigger the subtitle icon overlay.")
    parser.add_argument("--voiceover-path", default=None, help="Optional caller-provided voiceover audio.")
    parser.add_argument("--generate-dubbing", action="store_true", default=True)
    parser.add_argument("--no-generate-dubbing", dest="generate_dubbing", action="store_false")
    parser.add_argument("--local-tts", action="store_true", help="Use Windows SAPI TTS when available. Otherwise silent audio is used.")
    parser.add_argument("--voice-name", default=None, help="Optional Windows SAPI voice name. Use | to provide multiple candidates and let the runner pick one.")
    parser.add_argument("--ark-api-key", default=os.getenv("ARK_API_KEY") or os.getenv("AIVIDEOEDITOR_ARK_API_KEY"))
    parser.add_argument("--ark-base-url", default=os.getenv("ARK_BASE_URL", "https://ark.cn-beijing.volces.com/api/v3"))
    parser.add_argument("--ark-model", default=os.getenv("SEEDANCE_MODEL", "doubao-seedance-1-0-pro-250528"))
    parser.add_argument("--ark-poll-interval", type=float, default=5.0)
    parser.add_argument("--ark-timeout-seconds", type=int, default=900)
    parser.add_argument("--seed", default=None)
    parser.add_argument("--output", default=None, help="Final MP4 path. Defaults to ./pre_roll_outputs/<run-id>/final.mp4")
    parser.add_argument("--output-json", default=None, help="Write result JSON here.")
    parser.add_argument("--ffmpeg", default=None)
    parser.add_argument("--ffprobe", default=None)
    parser.add_argument("--dry-run", action="store_true")
    return parser


def apply_config(args: argparse.Namespace, config: Dict[str, Any]) -> argparse.Namespace:
    if not config:
        return args
    argv = sys.argv[1:]
    supplied = {token.split("=", 1)[0] for token in argv if token.startswith("--")}
    direct_map = {
        "scriptText": "script_text",
        "promptText": "prompt_text",
        "visualTemplateId": "visual_template_id",
        "assetStrategy": "asset_strategy",
        "backgroundVideo": "background_video",
        "backgroundImage": "background_image",
        "backgroundUrl": "background_url",
        "scrapedVideoUrl": "scraped_video_url",
        "assetRoot": "asset_root",
        "assetManifest": "asset_manifest",
        "assetPreflight": "asset_preflight",
        "useBundledAssets": "use_bundled_assets",
        "materialSelectionJson": "material_selection_json",
        "duration": "duration",
        "ratio": "ratio",
        "resolution": "resolution",
        "subtitleAudioSync": "subtitle_audio_sync",
        "subtitleOffsetSeconds": "subtitle_offset_seconds",
        "subtitleSpeechThresholdDb": "subtitle_speech_threshold_db",
        "subtitleMaxAutoOffsetSeconds": "subtitle_max_auto_offset_seconds",
        "includeDisclaimerSubtitle": "include_disclaimer_subtitle",
        "disclaimerText": "disclaimer_text",
        "brandText": "brand_text",
        "logoPath": "logo_path",
        "logoLightPath": "logo_light_path",
        "logoDarkPath": "logo_dark_path",
        "logoLumaThreshold": "logo_luma_threshold",
        "subtitleLogoEnabled": "subtitle_logo_enabled",
        "subtitleLogoPath": "subtitle_logo_path",
        "subtitleLogoWidthRatio": "subtitle_logo_width_ratio",
        "subtitleLogoGapRatio": "subtitle_logo_gap_ratio",
        "subtitleLogoOpacity": "subtitle_logo_opacity",
        "subtitleLogoMaxOverlays": "subtitle_logo_max_overlays",
        "subtitleLogoTerms": "subtitle_logo_terms",
        "voiceoverPath": "voiceover_path",
        "generateDubbing": "generate_dubbing",
        "localTts": "local_tts",
        "voiceName": "voice_name",
        "bodyFontName": "body_font_name",
        "brandFontName": "brand_font_name",
        "brandPrimaryColor": "brand_primary_color",
        "brandOutlineColor": "brand_outline_color",
        "brandFontScale": "brand_font_scale",
        "fontsDir": "fonts_dir",
        "bodyFontPath": "body_font_path",
        "brandFontPath": "brand_font_path",
        "arkApiKey": "ark_api_key",
        "arkBaseUrl": "ark_base_url",
        "arkModel": "ark_model",
        "seed": "seed",
        "output": "output",
        "outputJson": "output_json",
    }
    for key, attr in direct_map.items():
        flag = "--" + attr.replace("_", "-")
        if flag not in supplied and key in config:
            setattr(args, attr, config[key])

    brand_overlay = config.get("brandOverlay")
    if isinstance(brand_overlay, dict):
        nested_map = {
            "logoPath": "logo_path",
            "logoLightPath": "logo_light_path",
            "logoDarkPath": "logo_dark_path",
            "logoLumaThreshold": "logo_luma_threshold",
            "subtitleLogoEnabled": "subtitle_logo_enabled",
            "subtitleLogoPath": "subtitle_logo_path",
            "subtitleLogoWidthRatio": "subtitle_logo_width_ratio",
            "subtitleLogoGapRatio": "subtitle_logo_gap_ratio",
            "subtitleLogoOpacity": "subtitle_logo_opacity",
            "subtitleLogoMaxOverlays": "subtitle_logo_max_overlays",
            "subtitleLogoTerms": "subtitle_logo_terms",
            "brandPrimaryColor": "brand_primary_color",
            "brandOutlineColor": "brand_outline_color",
            "brandFontScale": "brand_font_scale",
        }
        for key, attr in nested_map.items():
            flag = "--" + attr.replace("_", "-")
            if flag not in supplied and key in brand_overlay:
                setattr(args, attr, brand_overlay[key])

    if "--subtitle-config-json" not in supplied and isinstance(config.get("subtitleConfig"), dict):
        args.subtitle_config_json = json.dumps(config["subtitleConfig"], ensure_ascii=False)
    if "--disclaimer-config-json" not in supplied and isinstance(config.get("disclaimerConfig"), dict):
        args.disclaimer_config_json = json.dumps(config["disclaimerConfig"], ensure_ascii=False)
    return args


def write_json(path: Optional[str], data: Dict[str, Any]) -> None:
    if not path:
        return
    output = Path(path).expanduser()
    output = output.resolve() if output.is_absolute() else (Path.cwd() / output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def load_optional_selection_json(path_value: Optional[str]) -> Any:
    if not path_value:
        return None
    selection_path = Path(path_value).expanduser().resolve()
    if not selection_path.exists():
        raise RunnerError(f"Material selection JSON not found: {selection_path}")
    return json.loads(selection_path.read_text(encoding="utf-8-sig"))


def resolve_asset_manifest_path(asset_manifest: Optional[str], asset_root: Optional[Path]) -> Optional[Path]:
    if asset_manifest:
        return normalize_media_input(asset_manifest)
    if asset_root:
        return (Path.cwd() / DEFAULT_ASSET_MANIFEST_NAME).resolve()
    return None


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    args = apply_config(args, load_json_file(args.config))

    script_text = str(args.script_text or "").strip()
    if not script_text:
        raise RunnerError("Missing --script-text")
    validate_copy_text(script_text, "scriptText")
    if args.include_disclaimer_subtitle:
        validate_copy_text(str(args.disclaimer_text or ""), "disclaimerText")

    run_id = uuid.uuid4().hex[:12]
    output_path = Path(args.output).expanduser() if args.output else DEFAULT_OUTPUT_DIR / run_id / "final.mp4"
    output_path = output_path.resolve() if output_path.is_absolute() else (Path.cwd() / output_path).resolve()
    work_dir = output_path.parent / "_work"
    work_dir.mkdir(parents=True, exist_ok=True)

    visual_type = normalize_visual_type(args.visual_template_id)
    scene = choose_scene(visual_type, args.seed)
    visual_prompt = build_visual_prompt(visual_type, scene, args.prompt_text)

    subtitle_config = merge_dict(
        {
            "position": args.subtitle_position,
            "fontName": DEFAULT_BODY_FONT_NAME,
            "brandFontName": DEFAULT_BRAND_FONT_NAME,
            "brandPrimaryColor": DEFAULT_BRAND_SUBTITLE_COLOR,
            "brandOutlineColor": DEFAULT_BRAND_SUBTITLE_OUTLINE_COLOR,
            "brandFontScale": DEFAULT_BRAND_SUBTITLE_SCALE,
            "fontSize": args.subtitle_font_size,
            "maxLines": 2,
            "safeMarginRatio": 0.12,
            "bottomMarginRatio": 0.22,
            "outline": 2,
            "shadow": 0,
        },
        parse_json_object(args.subtitle_config_json, "--subtitle-config-json"),
    )
    if args.subtitle_font_size:
        subtitle_config["fontSize"] = args.subtitle_font_size
    if args.subtitle_position:
        subtitle_config["position"] = args.subtitle_position
    if args.body_font_name:
        subtitle_config["fontName"] = args.body_font_name
    if args.brand_font_name:
        subtitle_config["brandFontName"] = args.brand_font_name
    if args.brand_primary_color:
        subtitle_config["brandPrimaryColor"] = args.brand_primary_color
    if args.brand_outline_color:
        subtitle_config["brandOutlineColor"] = args.brand_outline_color
    if args.brand_font_scale is not None:
        subtitle_config["brandFontScale"] = args.brand_font_scale
    if subtitle_config.get("fontSize") is None:
        subtitle_config["fontSize"] = 46
    subtitle_audio_sync = str(
        args.subtitle_audio_sync
        or subtitle_config.get("audioSync")
        or subtitle_config.get("audioSyncMode")
        or "auto"
    ).strip().lower()
    raw_subtitle_offset = (
        args.subtitle_offset_seconds
        if args.subtitle_offset_seconds is not None
        else subtitle_config.get("offsetSeconds", subtitle_config.get("subtitleOffsetSeconds"))
    )
    subtitle_offset_seconds = float(raw_subtitle_offset) if raw_subtitle_offset is not None else None
    raw_threshold_db = (
        args.subtitle_speech_threshold_db
        if args.subtitle_speech_threshold_db is not None
        else subtitle_config.get("speechThresholdDb", -35.0)
    )
    subtitle_speech_threshold_db = float(raw_threshold_db)
    raw_max_auto_offset = (
        args.subtitle_max_auto_offset_seconds
        if args.subtitle_max_auto_offset_seconds is not None
        else subtitle_config.get("maxAutoOffsetSeconds", 1.5)
    )
    subtitle_max_auto_offset_seconds = max(0.0, float(raw_max_auto_offset))

    disclaimer_config = merge_dict(
        {
            "position": "bottom_right",
            "fontSize": 22,
            "fontName": DEFAULT_DISCLAIMER_FONT_NAME,
            "primaryColor": "&H00FFFFFF",
            "outlineColor": "&H00000000",
            "backColor": "&H00000000",
            "outline": 1.4,
            "shadow": 0,
            "safeMarginRatio": 0.045,
            "bottomMarginRatio": 0.045,
        },
        parse_json_object(args.disclaimer_config_json, "--disclaimer-config-json"),
    )
    subtitle_logo_terms = _parse_string_list(args.subtitle_logo_terms) or list(DEFAULT_SUBTITLE_BRAND_TERMS)
    subtitle_logo_width_ratio = clamp_float(
        args.subtitle_logo_width_ratio,
        DEFAULT_SUBTITLE_BRAND_LOGO_WIDTH_RATIO,
        0.05,
        0.5,
    )
    subtitle_logo_gap_ratio = clamp_float(
        args.subtitle_logo_gap_ratio,
        DEFAULT_SUBTITLE_BRAND_LOGO_GAP_RATIO,
        0.0,
        0.2,
    )
    subtitle_logo_opacity = clamp_float(args.subtitle_logo_opacity, 1.0, 0.0, 1.0)
    subtitle_logo_max_overlays = max(0, min(30, int(args.subtitle_logo_max_overlays or 0)))
    width, height = output_size(args.resolution, args.ratio)
    estimated_duration = estimate_text_duration(script_text, args.duration)

    voiceover_path = normalize_media_input(args.voiceover_path)
    ffprobe_bin: Optional[str] = None
    if voiceover_path and not args.dry_run:
        ffprobe_bin = require_binary("ffprobe", args.ffprobe)
        voice_duration = ffprobe_duration(ffprobe_bin, voiceover_path)
        if voice_duration:
            estimated_duration = max(estimated_duration, voice_duration)

    ark_result: Optional[Dict[str, Any]] = None
    background_video = normalize_media_input(args.background_video)
    background_image = normalize_media_input(args.background_image)
    background_url = args.background_url or args.scraped_video_url
    direct_logo_path = normalize_media_input(args.logo_path)
    logo_light_path = normalize_media_input(args.logo_light_path)
    logo_dark_path = normalize_media_input(args.logo_dark_path)
    subtitle_logo_path = normalize_media_input(args.subtitle_logo_path)
    bundled_logo_light_path, bundled_logo_dark_path, bundled_subtitle_logo_path = discover_default_brand_asset_paths(
        bool(args.use_bundled_assets)
    )
    if not logo_light_path:
        logo_light_path = bundled_logo_light_path
    if not logo_dark_path:
        logo_dark_path = bundled_logo_dark_path
    if not subtitle_logo_path:
        subtitle_logo_path = bundled_subtitle_logo_path
    asset_root = normalize_media_input(args.asset_root)
    asset_manifest_path = resolve_asset_manifest_path(args.asset_manifest, asset_root)
    asset_preflight_mode = str(
        args.asset_preflight
        or ("required" if (asset_root or asset_manifest_path) else "off")
    ).strip().lower()
    fonts_dir = normalize_media_input(args.fonts_dir)
    body_font_path = normalize_media_input(args.body_font_path)
    brand_font_path = normalize_media_input(args.brand_font_path)
    discovered_body_font_path, discovered_brand_font_path = discover_default_font_paths(
        bool(args.use_bundled_assets)
    )
    if not body_font_path:
        body_font_path = discovered_body_font_path
    if not brand_font_path:
        brand_font_path = discovered_brand_font_path
    if not (direct_logo_path or logo_light_path or logo_dark_path):
        raise RunnerError("Missing logo material. Provide --logo-path, or --logo-light-path / --logo-dark-path.")

    load_optional_selection_json(args.material_selection_json)
    preflight_required_paths = [
        str(path)
        for path in (
            background_video,
            background_image,
            direct_logo_path,
            logo_light_path,
            logo_dark_path,
            subtitle_logo_path,
        )
        if path and not is_within_path(path, BUNDLED_MATERIAL_ROOT)
    ]
    asset_preflight_report: Optional[Dict[str, Any]] = None
    if asset_preflight_mode != "off":
        if not asset_root or not asset_manifest_path:
            asset_preflight_report = {
                "ok": False,
                "error": "asset preflight requires --asset-root and --asset-manifest",
            }
        else:
            try:
                asset_preflight_report = validate_manifest_for_paths(
                    asset_root=asset_root,
                    asset_manifest=asset_manifest_path,
                    required_paths=preflight_required_paths,
                    selection_json=Path(args.material_selection_json).expanduser().resolve()
                    if args.material_selection_json
                    else None,
                )
            except (ManifestError, OSError, ValueError, json.JSONDecodeError) as exc:
                asset_preflight_report = {"ok": False, "error": str(exc)}
        if asset_preflight_mode == "required" and not args.dry_run and not asset_preflight_report["ok"]:
            raise RunnerError(json.dumps(asset_preflight_report, ensure_ascii=False, indent=2))

    if (
        args.asset_strategy == "generated"
        and not args.dry_run
        and not background_video
        and not background_image
        and not background_url
    ):
        if not args.ark_api_key:
            raise RunnerError(
                "assetStrategy=generated requires --ark-api-key so the workflow can create a real video background. "
                "Placeholder backgrounds are disabled."
            )
        ark_output = work_dir / "seedance.mp4"
        ark_result = generate_seedance_video(
            api_key=args.ark_api_key,
            base_url=args.ark_base_url,
            model=args.ark_model,
            prompt=visual_prompt,
            duration=int(max(4, min(math.ceil(args.duration), 15))),
            ratio=args.ratio,
            resolution=args.resolution,
            output_path=ark_output,
            poll_interval=args.ark_poll_interval,
            timeout_seconds=args.ark_timeout_seconds,
        )
        background_video = ark_output

    preview = {
        "mode": "standalone",
        "runId": run_id,
        "scriptText": script_text,
        "visualTemplateId": visual_type,
        "scene": scene,
        "visualPrompt": visual_prompt,
        "assetStrategy": args.asset_strategy,
        "realVideoContentRequired": True,
        "hasRealVideoSource": bool(
            background_video
            or background_image
            or background_url
            or (args.asset_strategy == "generated" and args.ark_api_key)
        ),
        "assetRoot": str(asset_root) if asset_root else None,
        "assetManifest": str(asset_manifest_path) if asset_manifest_path else None,
        "assetPreflight": asset_preflight_mode,
        "assetPreflightReport": asset_preflight_report,
        "useBundledAssets": bool(args.use_bundled_assets),
        "bundledMaterialRoot": str(BUNDLED_MATERIAL_ROOT) if BUNDLED_MATERIAL_ROOT.exists() else None,
        "size": {"width": width, "height": height, "ratio": args.ratio, "resolution": args.resolution},
        "estimatedDuration": round(estimated_duration, 3),
        "subtitleConfig": subtitle_config,
        "subtitleAudioSync": subtitle_audio_sync,
        "subtitleOffsetSeconds": subtitle_offset_seconds,
        "subtitleSpeechThresholdDb": subtitle_speech_threshold_db,
        "subtitleMaxAutoOffsetSeconds": subtitle_max_auto_offset_seconds,
        "includeDisclaimerSubtitle": args.include_disclaimer_subtitle,
        "disclaimerText": args.disclaimer_text if args.include_disclaimer_subtitle else None,
        "disclaimerConfig": disclaimer_config,
        "brandText": args.brand_text,
        "logoPath": str(direct_logo_path) if direct_logo_path else None,
        "logoLightPath": str(logo_light_path) if logo_light_path else None,
        "logoDarkPath": str(logo_dark_path) if logo_dark_path else None,
        "logoLumaThreshold": float(args.logo_luma_threshold),
        "subtitleBrandLogoOverlay": {
            "enabled": bool(args.subtitle_logo_enabled),
            "terms": subtitle_logo_terms,
            "assetPreference": "subtitleLogoPath -> selected logo fallback",
            "placement": "above the matching main subtitle line",
            "logoPath": str(subtitle_logo_path) if subtitle_logo_path else None,
            "widthRatio": subtitle_logo_width_ratio,
            "gapRatio": subtitle_logo_gap_ratio,
            "opacity": subtitle_logo_opacity,
            "maxOverlays": subtitle_logo_max_overlays,
        },
        "fontsDir": str(fonts_dir) if fonts_dir else None,
        "bodyFontPath": str(body_font_path) if body_font_path else None,
        "brandFontPath": str(brand_font_path) if brand_font_path else None,
        "voiceName": args.voice_name,
        "logoSelection": {
            "mode": (
                "direct"
                if direct_logo_path
                else "auto_pending_in_dry_run"
                if logo_light_path and logo_dark_path
                else "single_candidate"
                if logo_light_path or logo_dark_path
                else "none"
            ),
            "measurement": "full_clip_mean_luma" if logo_light_path and logo_dark_path else None,
            "rule": "bright background -> dark logo; dark background -> light logo" if logo_light_path and logo_dark_path else None,
            "reason": "real brightness is measured after background rendering",
        },
        "backgroundVideo": str(background_video) if background_video else None,
        "backgroundImage": str(background_image) if background_image else None,
        "backgroundUrl": background_url,
        "voiceoverPath": str(voiceover_path) if voiceover_path else None,
        "materialSelectionJson": str(Path(args.material_selection_json).expanduser().resolve()) if args.material_selection_json else None,
        "localTts": bool(args.local_tts),
        "output": str(output_path),
        "outputJson": args.output_json,
    }
    if args.dry_run:
        print(json.dumps(preview, ensure_ascii=False, indent=2))
        write_json(args.output_json, preview)
        return 0

    ffmpeg_bin = require_binary("ffmpeg", args.ffmpeg)
    ffprobe_bin = ffprobe_bin or require_binary("ffprobe", args.ffprobe)

    base_video = work_dir / "base.mp4"
    audio_path = work_dir / "audio.wav"
    ass_path = work_dir / "subtitles.ass"
    prepared_fonts_dir = prepare_fonts_dir(
        work_dir=work_dir,
        fonts_dir=fonts_dir,
        body_font_path=body_font_path,
        brand_font_path=brand_font_path,
    )

    base_detail = make_base_video(
        ffmpeg_bin=ffmpeg_bin,
        background_video=background_video,
        background_image=background_image,
        background_url=background_url,
        visual_type=visual_type,
        duration=estimated_duration,
        width=width,
        height=height,
        output_path=base_video,
        work_dir=work_dir,
    )
    logo_selection = choose_logo_variant(
        ffmpeg_bin=ffmpeg_bin,
        base_video=base_video,
        logo_path=direct_logo_path,
        logo_light_path=logo_light_path,
        logo_dark_path=logo_dark_path,
        threshold=float(args.logo_luma_threshold),
    )
    audio_detail = make_audio(
        ffmpeg_bin=ffmpeg_bin,
        ffprobe_bin=ffprobe_bin,
        script_text=script_text,
        duration=estimated_duration,
        voiceover_path=voiceover_path,
        generate_dubbing=bool(args.generate_dubbing),
        local_tts=bool(args.local_tts),
        voice_name=args.voice_name,
        voice_seed=args.seed,
        output_path=audio_path,
    )
    final_duration = max(estimated_duration, float(audio_detail.get("duration") or estimated_duration))
    subtitle_sync_detail = resolve_subtitle_audio_sync(
        ffmpeg_bin=ffmpeg_bin,
        audio_path=audio_path,
        audio_detail=audio_detail,
        mode=subtitle_audio_sync,
        manual_offset=subtitle_offset_seconds,
        threshold_db=subtitle_speech_threshold_db,
        max_auto_offset=subtitle_max_auto_offset_seconds,
        duration=final_duration,
    )
    subtitle_detail = generate_ass(
        output_path=ass_path,
        text=script_text,
        duration=final_duration,
        width=width,
        height=height,
        subtitle_config=subtitle_config,
        disclaimer_text=args.disclaimer_text if args.include_disclaimer_subtitle else None,
        disclaimer_config=disclaimer_config,
        brand_text=args.brand_text,
        subtitle_offset=float(subtitle_sync_detail.get("offsetSeconds") or 0.0),
    )
    compose_detail = compose_final(
        ffmpeg_bin=ffmpeg_bin,
        base_video=base_video,
        audio_path=audio_path,
        ass_path=ass_path,
        fonts_dir=prepared_fonts_dir,
        logo_path=Path(logo_selection["path"]) if logo_selection.get("path") else None,
        output_path=output_path,
        duration=final_duration,
        width=width,
        height=height,
    )
    subtitle_brand_logo_detail = apply_subtitle_brand_logo_overlays(
        ffmpeg_bin=ffmpeg_bin,
        input_path=output_path,
        work_dir=work_dir,
        subtitle_detail=subtitle_detail,
        subtitle_config=subtitle_config,
        fallback_logo_path=subtitle_logo_path or (Path(logo_selection["path"]) if logo_selection.get("path") else None),
        duration=final_duration,
        width=width,
        height=height,
        enabled=bool(args.subtitle_logo_enabled),
        terms=subtitle_logo_terms,
        logo_width_ratio=subtitle_logo_width_ratio,
        gap_ratio=subtitle_logo_gap_ratio,
        max_overlays=subtitle_logo_max_overlays,
        opacity=subtitle_logo_opacity,
    )
    rendered_with_subtitle_logo = Path(str(subtitle_brand_logo_detail.get("path") or output_path))
    if subtitle_brand_logo_detail.get("enabled") and rendered_with_subtitle_logo != output_path:
        # 用户传进来的 output 始终是最终成品路径；中间叠图文件只留在 _work 里方便排查。
        shutil.copy2(rendered_with_subtitle_logo, output_path)
        subtitle_brand_logo_detail["finalOutputPath"] = str(output_path)
    cover_path = output_path.with_name(output_path.stem + "_cover.jpg")
    cover = extract_cover(ffmpeg_bin, output_path, cover_path)

    result = {
        **preview,
        "status": "completed",
        "duration": round(final_duration, 3),
        "logoSelection": logo_selection,
        "outputs": {
            "finalVideoPath": str(output_path),
            "coverPath": cover,
            "subtitlePath": str(ass_path),
            "fontsDir": str(prepared_fonts_dir) if prepared_fonts_dir else None,
            "workDir": str(work_dir),
        },
        "steps": {
            "arkGeneration": ark_result,
            "background": base_detail,
            "logoSelection": logo_selection,
            "audio": audio_detail,
            "subtitleSync": subtitle_sync_detail,
            "subtitle": subtitle_detail,
            "subtitleBrandLogo": subtitle_brand_logo_detail,
            "compose": compose_detail,
        },
    }
    print(json.dumps(result, ensure_ascii=False, indent=2))
    write_json(args.output_json or str(output_path.with_suffix(".json")), result)
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (RunnerError, ManifestError, OSError, ValueError, json.JSONDecodeError) as exc:
        print(json.dumps({"status": "failed", "error": str(exc)}, ensure_ascii=False, indent=2), file=sys.stderr)
        raise SystemExit(2)
