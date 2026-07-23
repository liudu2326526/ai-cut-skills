from __future__ import annotations

import argparse
import base64
import json
import os
import shutil
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any, Dict, Optional


TERMINAL_STATUSES = {"completed", "failed", "cancelled", "canceled"}
DEFAULT_DISCLAIMER = "本视频为广告创意\n具体奖励金额以实际情况为准"
DEFAULT_BODY_FONT_NAME = "FZLanTingHeiS-DB1-GB"
DEFAULT_BRAND_FONT_NAME = "Soda Font"
DEFAULT_BRAND_SUBTITLE_COLOR = "&H0042FD3B"
DEFAULT_BRAND_SUBTITLE_OUTLINE_COLOR = "&H00000000"
DEFAULT_BRAND_SUBTITLE_SCALE = 1.18
DEFAULT_DISCLAIMER_FONT_NAME = "Microsoft YaHei"
FORBIDDEN_COPY_TERMS = ("红包", "花不完")

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8")


def _load_json(path: Optional[str]) -> Dict[str, Any]:
    if not path:
        return {}
    with Path(path).open("r", encoding="utf-8") as file:
        payload = json.load(file)
    if not isinstance(payload, dict):
        raise SystemExit("Config root must be a JSON object")
    return payload


def _parse_json_object(raw: Optional[str], label: str) -> Dict[str, Any]:
    if not raw:
        return {}
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise SystemExit(f"{label} is not valid JSON: {exc}") from exc
    if not isinstance(payload, dict):
        raise SystemExit(f"{label} must be a JSON object")
    return payload


def _parse_string_list(raw: Optional[str]) -> list[str]:
    if not raw:
        return []
    values: list[str] = []
    for part in str(raw).replace("，", ",").replace("|", ",").split(","):
        clean = part.strip()
        if clean:
            values.append(clean)
    return list(dict.fromkeys(values))


def _merge_dict(base: Dict[str, Any], patch: Dict[str, Any]) -> Dict[str, Any]:
    result = dict(base)
    for key, value in patch.items():
        if isinstance(value, dict) and isinstance(result.get(key), dict):
            result[key] = _merge_dict(result[key], value)
        elif value is not None:
            result[key] = value
    return result


def _validate_copy_text(text: Any, label: str) -> None:
    matched = [term for term in FORBIDDEN_COPY_TERMS if term in str(text or "")]
    if matched:
        raise SystemExit(f"{label} cannot contain: {', '.join(matched)}")


def _iter_text_values(value: Any):
    if isinstance(value, dict):
        for child in value.values():
            yield from _iter_text_values(child)
    elif isinstance(value, list):
        for child in value:
            yield from _iter_text_values(child)
    elif value is not None:
        yield str(value)


def _server_root(base_url: str, api_prefix: str) -> tuple[str, str]:
    base = (base_url or "").strip().rstrip("/")
    if not base:
        raise SystemExit("Missing --base-url or AIVIDEOEDITOR_API_BASE_URL")
    prefix = (api_prefix or "/api/v1").strip()
    if not prefix.startswith("/"):
        prefix = "/" + prefix
    if base.endswith(prefix):
        return base[: -len(prefix)].rstrip("/"), prefix
    return base, prefix


def _request_json(
    method: str,
    url: str,
    *,
    body: Optional[Dict[str, Any]] = None,
    token: Optional[str] = None,
    timeout: int = 60,
) -> Dict[str, Any]:
    data = None
    headers = {"Accept": "application/json"}
    if body is not None:
        data = json.dumps(body, ensure_ascii=False).encode("utf-8")
        headers["Content-Type"] = "application/json"
    if token:
        headers["Authorization"] = f"Bearer {token}"

    request = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            text = response.read().decode("utf-8")
            return json.loads(text) if text else {}
    except urllib.error.HTTPError as exc:
        text = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"HTTP {exc.code} for {url}: {text}") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"Request failed for {url}: {exc}") from exc


def _task_url(base_url: str, api_prefix: str, user_id: str, task_id: Optional[str] = None) -> str:
    root, prefix = _server_root(base_url, api_prefix)
    query = urllib.parse.urlencode({"userId": user_id})
    if task_id:
        return f"{root}{prefix}/pre-roll/tasks/{urllib.parse.quote(task_id)}?{query}"
    return f"{root}{prefix}/pre-roll/tasks?{query}"


def _auth_url(base_url: str, api_prefix: str, path: str) -> str:
    root, prefix = _server_root(base_url, api_prefix)
    safe_path = path if path.startswith("/") else f"/{path}"
    return f"{root}{prefix}/auth{safe_path}"


def _unwrap_response_data(response: Dict[str, Any]) -> Dict[str, Any]:
    data = response.get("data")
    return data if isinstance(data, dict) else response


def _decode_jwt_payload(token: Optional[str]) -> Dict[str, Any]:
    raw_token = (token or "").strip()
    parts = raw_token.split(".")
    if len(parts) != 3:
        return {}

    try:
        payload_segment = parts[1] + ("=" * (-len(parts[1]) % 4))
        payload = json.loads(base64.urlsafe_b64decode(payload_segment).decode("utf-8"))
    except (ValueError, json.JSONDecodeError, UnicodeDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def _is_placeholder_user_id(user_id: str) -> bool:
    normalized = user_id.strip().lower()
    return normalized in {"default", "anonymous", "anon"} or normalized.startswith("pre-roll-anon-")


def _login(args: argparse.Namespace) -> Dict[str, str]:
    wants_password_login = bool(args.login_account or args.login_password)
    wants_wechat_login = bool(args.wechat_code)
    wants_browser_login = bool(args.browser_login_token)
    login_count = sum([wants_password_login, wants_wechat_login, wants_browser_login])
    if login_count == 0:
        return {}
    if login_count > 1:
        raise SystemExit("Choose only one login method: password, wechat code, or browser login token")

    if wants_password_login:
        if not args.login_account or not args.login_password:
            raise SystemExit("--login-account and --login-password must be provided together")
        response = _request_json(
            "POST",
            _auth_url(args.base_url, args.api_prefix, "/password/login"),
            body={"account": args.login_account, "password": args.login_password},
            timeout=args.request_timeout,
        )
    elif wants_wechat_login:
        response = _request_json(
            "POST",
            _auth_url(args.base_url, args.api_prefix, "/wechat/login"),
            body={"code": args.wechat_code},
            timeout=args.request_timeout,
        )
    else:
        response = _request_json(
            "POST",
            _auth_url(args.base_url, args.api_prefix, "/browser-login/consume"),
            body={"token": args.browser_login_token},
            timeout=args.request_timeout,
        )

    data = _unwrap_response_data(response)
    token = str(data.get("token") or "").strip()
    user = data.get("user") if isinstance(data.get("user"), dict) else {}
    user_id = str(user.get("id") or "").strip()
    if not token or not user_id:
        raise SystemExit("Login succeeded but response did not include token and user.id")
    return {"auth_token": token, "user_id": user_id}


def _resolve_user_id(explicit_user_id: str, auth_token: Optional[str]) -> str:
    user_id = (explicit_user_id or "").strip()
    if user_id:
        if _is_placeholder_user_id(user_id):
            raise SystemExit(
                "Do not use a placeholder userId for real submission. "
                "Log in or pass an existing backend user id linked to wx_userid."
            )
        return user_id

    jwt_payload = _decode_jwt_payload(auth_token)
    token_user_id = str(jwt_payload.get("sub") or jwt_payload.get("user_id") or "").strip()
    if token_user_id:
        return token_user_id

    raise SystemExit(
        "Missing real user identity. Provide login credentials, --auth-token with a JWT "
        "containing sub/user_id, or --user-id for an existing backend user linked to wx_userid."
    )


def _build_payload(args: argparse.Namespace) -> Dict[str, Any]:
    payload = _load_json(args.config)
    payload_subtitle_config = payload.get("subtitleConfig") if isinstance(payload.get("subtitleConfig"), dict) else {}
    subtitle_config = _merge_dict(
        {
            "fontName": DEFAULT_BODY_FONT_NAME,
            "brandFontName": DEFAULT_BRAND_FONT_NAME,
            "brandPrimaryColor": DEFAULT_BRAND_SUBTITLE_COLOR,
            "brandOutlineColor": DEFAULT_BRAND_SUBTITLE_OUTLINE_COLOR,
            "brandFontScale": DEFAULT_BRAND_SUBTITLE_SCALE,
        },
        payload_subtitle_config,
    )
    subtitle_config = _merge_dict(
        subtitle_config,
        _parse_json_object(args.subtitle_config_json, "--subtitle-config-json"),
    )
    disclaimer_config = _parse_json_object(args.disclaimer_config_json, "--disclaimer-config-json")
    if not disclaimer_config:
        disclaimer_config = {
            "position": "bottom_right",
            "fontSize": 22,
            "fontName": DEFAULT_DISCLAIMER_FONT_NAME,
            "primaryColor": "&H00FFFFFF",
            "outlineColor": "&H00000000",
            "backColor": "&H00000000",
            "outline": 1.4,
            "shadow": 0,
        }
    scraped_video_urls = _parse_json_object(args.scraped_video_urls_json, "--scraped-video-urls-json")
    extra = _parse_json_object(args.extra_json, "--extra-json")
    brand_overlay: Dict[str, Any] = {}
    if args.logo_path:
        brand_overlay["logoPath"] = args.logo_path
    if args.logo_light_path:
        brand_overlay["logoLightPath"] = args.logo_light_path
    if args.logo_dark_path:
        brand_overlay["logoDarkPath"] = args.logo_dark_path
    if args.logo_luma_threshold is not None:
        brand_overlay["logoLumaThreshold"] = args.logo_luma_threshold
    if args.subtitle_logo_enabled is not None:
        brand_overlay["subtitleLogoEnabled"] = bool(args.subtitle_logo_enabled)
    if args.subtitle_logo_path:
        brand_overlay["subtitleLogoPath"] = args.subtitle_logo_path
    subtitle_logo_terms = _parse_string_list(args.subtitle_logo_terms)
    if subtitle_logo_terms:
        brand_overlay["subtitleLogoTerms"] = subtitle_logo_terms
    if args.subtitle_logo_width_ratio is not None:
        brand_overlay["subtitleLogoWidthRatio"] = args.subtitle_logo_width_ratio
    if args.subtitle_logo_gap_ratio is not None:
        brand_overlay["subtitleLogoGapRatio"] = args.subtitle_logo_gap_ratio
    if args.subtitle_logo_opacity is not None:
        brand_overlay["subtitleLogoOpacity"] = args.subtitle_logo_opacity
    if args.subtitle_logo_max_overlays is not None:
        brand_overlay["subtitleLogoMaxOverlays"] = args.subtitle_logo_max_overlays
    voice_candidates = _parse_string_list(args.voice_candidates)

    generated: Dict[str, Any] = {
        "scriptText": args.script_text,
        "visualTemplateId": args.visual_template_id,
        "visualPromptText": args.visual_prompt_text,
        "assetStrategy": args.asset_strategy,
        "scrapedVideoType": args.scraped_video_type,
        "scrapedVideoUrl": args.scraped_video_url,
        "scrapedVideoUrls": scraped_video_urls or None,
        "ratio": args.ratio,
        "duration": args.duration,
        "resolution": args.resolution,
        "voiceType": args.voice_type,
        "voiceCandidates": voice_candidates or None,
        "generateDubbing": args.generate_dubbing,
        "generateSubtitle": args.generate_subtitle,
        "subtitleConfig": subtitle_config or None,
        "includeDisclaimerSubtitle": args.include_disclaimer_subtitle,
        "disclaimerText": args.disclaimer_text,
        "disclaimerConfig": disclaimer_config or None,
        "brandOverlay": brand_overlay or None,
    }

    if args.subtitle_position:
        generated["subtitleConfig"] = _merge_dict(
            generated.get("subtitleConfig") or {},
            {"position": args.subtitle_position},
        )
    if args.subtitle_font_size:
        generated["subtitleConfig"] = _merge_dict(
            generated.get("subtitleConfig") or {},
            {"fontSize": args.subtitle_font_size},
        )
    brand_subtitle_overrides = {
        "brandPrimaryColor": args.brand_primary_color,
        "brandOutlineColor": args.brand_outline_color,
        "brandFontScale": args.brand_font_scale,
    }
    brand_subtitle_overrides = {key: value for key, value in brand_subtitle_overrides.items() if value is not None}
    if brand_subtitle_overrides:
        generated["subtitleConfig"] = _merge_dict(
            generated.get("subtitleConfig") or {},
            brand_subtitle_overrides,
        )

    payload = _merge_dict(payload, {key: value for key, value in generated.items() if value is not None})
    payload = _merge_dict(payload, extra)

    if not any(str(payload.get(key) or "").strip() for key in ("scriptText", "promptText", "copyTemplateType")):
        raise SystemExit("Payload requires scriptText, promptText, or copyTemplateType")
    _validate_copy_text(payload.get("scriptText") or payload.get("promptText"), "scriptText/promptText")
    for text_value in _iter_text_values(payload.get("copyVariables") or {}):
        _validate_copy_text(text_value, "copyVariables")
    if payload.get("disclaimerText"):
        _validate_copy_text(payload.get("disclaimerText"), "disclaimerText")
    return payload


def _write_output(path: Optional[str], payload: Dict[str, Any]) -> None:
    if not path:
        return
    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _is_http_url(value: str) -> bool:
    normalized = (value or "").strip().lower()
    return normalized.startswith("http://") or normalized.startswith("https://")


def _resolve_video_source(outputs: Dict[str, Any]) -> Optional[str]:
    for key in ("finalVideoRemoteUrl", "generatedVideoUrl", "finalVideoUrl"):
        value = str(outputs.get(key) or "").strip()
        if value:
            return value
    return None


def _default_video_output_path(args: argparse.Namespace, task_id: str) -> Path:
    if args.video_output:
        path = Path(args.video_output)
        return path.expanduser().resolve() if path.is_absolute() else (Path.cwd() / path)

    if args.output:
        output_path = Path(args.output)
        output_path = output_path.expanduser().resolve() if output_path.is_absolute() else (Path.cwd() / output_path)
        return output_path.with_suffix(".mp4")

    return Path.cwd() / "pre_roll_outputs" / task_id / "final.mp4"


def _download_file(source: str, destination: Path, timeout: int = 300) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.exists():
        destination.unlink()

    source_path = Path(source)
    if source_path.exists():
        shutil.copy2(source_path, destination)
        return

    if not _is_http_url(source):
        raise SystemExit(f"Cannot download video from unsupported source: {source}")

    request = urllib.request.Request(
        source,
        headers={
            "Accept": "*/*",
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AIVideoEditor-PreRoll/1.0",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response, destination.open("wb") as file:
            shutil.copyfileobj(response, file)
    except urllib.error.URLError as exc:
        raise SystemExit(f"Failed to download final video from {source}: {exc}") from exc

    if not destination.exists() or destination.stat().st_size <= 0:
        raise SystemExit(f"Downloaded video is empty: {destination}")


def _download_final_video(args: argparse.Namespace, result: Dict[str, Any], task_id: str) -> Optional[Path]:
    data = result.get("resultData") if isinstance(result.get("resultData"), dict) else {}
    outputs = data.get("outputs") if isinstance(data, dict) and isinstance(data.get("outputs"), dict) else {}
    source = _resolve_video_source(outputs if isinstance(outputs, dict) else {})
    if not source:
        return None

    destination = _default_video_output_path(args, task_id)
    _download_file(source, destination)
    return destination


def main() -> int:
    parser = argparse.ArgumentParser(description="Submit and poll a remote AIVideoEditor pre-roll API task.")
    parser.add_argument("--base-url", default=os.getenv("AIVIDEOEDITOR_API_BASE_URL", ""))
    parser.add_argument("--api-prefix", default=os.getenv("AIVIDEOEDITOR_API_PREFIX", "/api/v1"))
    parser.add_argument("--user-id", default=os.getenv("AIVIDEOEDITOR_USER_ID", ""), help="Existing backend user id. Optional when login credentials or a JWT auth token are provided.")
    parser.add_argument("--auth-token", default=os.getenv("AIVIDEOEDITOR_AUTH_TOKEN", ""), help="Bearer token. If --user-id is omitted, the script tries to read sub/user_id from this JWT.")
    parser.add_argument("--login-account", default=os.getenv("AIVIDEOEDITOR_LOGIN_ACCOUNT", ""), help="Password-login account/username.")
    parser.add_argument("--login-password", default=os.getenv("AIVIDEOEDITOR_LOGIN_PASSWORD", ""), help="Password-login password.")
    parser.add_argument("--wechat-code", default=os.getenv("AIVIDEOEDITOR_WECHAT_CODE", ""), help="Enterprise WeChat OAuth code.")
    parser.add_argument("--browser-login-token", default=os.getenv("AIVIDEOEDITOR_BROWSER_LOGIN_TOKEN", ""), help="One-time browser login token to consume.")
    parser.add_argument("--config", default=None, help="Optional JSON body file")
    parser.add_argument("--script-text", default=None)
    parser.add_argument("--visual-template-id", default="decompression")
    parser.add_argument("--visual-prompt-text", default=None)
    parser.add_argument("--asset-strategy", default="generated")
    parser.add_argument("--scraped-video-type", default=None)
    parser.add_argument("--scraped-video-url", default=None)
    parser.add_argument("--scraped-video-urls-json", default=None)
    parser.add_argument("--ratio", default="9:16")
    parser.add_argument("--duration", type=int, default=8)
    parser.add_argument("--resolution", default="720p")
    parser.add_argument("--voice-type", default=None, help="TTS voice type. You can also use A|B|C to let the backend choose one.")
    parser.add_argument("--voice-candidates", default=None, help="Comma/pipe separated TTS voice candidates.")
    parser.add_argument("--generate-dubbing", dest="generate_dubbing", action="store_true")
    parser.add_argument("--no-generate-dubbing", dest="generate_dubbing", action="store_false")
    parser.set_defaults(generate_dubbing=True)
    parser.add_argument("--generate-subtitle", dest="generate_subtitle", action="store_true")
    parser.add_argument("--no-generate-subtitle", dest="generate_subtitle", action="store_false")
    parser.set_defaults(generate_subtitle=True)
    parser.add_argument("--subtitle-position", default="lower_center")
    parser.add_argument("--subtitle-font-size", type=int, default=None)
    parser.add_argument("--subtitle-config-json", default=None)
    parser.add_argument("--brand-primary-color", default=None, help="ASS/RGB fill color for 汽水音乐/汽水 subtitle text.")
    parser.add_argument("--brand-outline-color", default=None, help="ASS/RGB outline color for 汽水音乐/汽水 subtitle text.")
    parser.add_argument("--brand-font-scale", type=float, default=None, help="Scale for 汽水音乐/汽水 subtitle text, for example 1.18.")
    parser.add_argument("--include-disclaimer-subtitle", dest="include_disclaimer_subtitle", action="store_true")
    parser.add_argument("--no-include-disclaimer-subtitle", dest="include_disclaimer_subtitle", action="store_false")
    parser.set_defaults(include_disclaimer_subtitle=True)
    parser.add_argument("--disclaimer-text", default=DEFAULT_DISCLAIMER)
    parser.add_argument(
        "--disclaimer-config-json",
        default=(
            '{"position":"bottom_right","fontSize":22,"fontName":"Microsoft YaHei",'
            '"primaryColor":"&H00FFFFFF","outlineColor":"&H00000000","backColor":"&H00000000",'
            '"outline":1.4,"shadow":0}'
        ),
    )
    parser.add_argument("--logo-path", default=None, help="Real logo image path/url passed as brandOverlay.logoPath.")
    parser.add_argument("--logo-light-path", default=None, help="Logo for dark backgrounds.")
    parser.add_argument("--logo-dark-path", default=None, help="Logo for bright backgrounds.")
    parser.add_argument("--logo-luma-threshold", type=float, default=None, help="Brightness threshold for light/dark logo selection.")
    parser.add_argument("--subtitle-logo-enabled", dest="subtitle_logo_enabled", action="store_true")
    parser.add_argument("--no-subtitle-logo-enabled", dest="subtitle_logo_enabled", action="store_false")
    parser.set_defaults(subtitle_logo_enabled=None)
    parser.add_argument("--subtitle-logo-path", default=None, help="Real icon image path/url placed above subtitles when brand terms appear.")
    parser.add_argument("--subtitle-logo-terms", default=None, help="Comma/pipe separated terms that trigger the subtitle icon overlay.")
    parser.add_argument("--subtitle-logo-width-ratio", type=float, default=None)
    parser.add_argument("--subtitle-logo-gap-ratio", type=float, default=None)
    parser.add_argument("--subtitle-logo-opacity", type=float, default=None)
    parser.add_argument("--subtitle-logo-max-overlays", type=int, default=None)
    parser.add_argument("--extra-json", default=None, help="Extra body JSON merged last")
    parser.add_argument("--wait", action="store_true", help="Poll until terminal status")
    parser.add_argument("--poll-interval", type=float, default=5.0)
    parser.add_argument("--timeout-seconds", type=int, default=900)
    parser.add_argument("--request-timeout", type=int, default=60)
    parser.add_argument("--output", default=None, help="Write final response JSON to this file")
    parser.add_argument(
        "--video-output",
        default=None,
        help="Write the downloaded final video to this file. Defaults to a local path under the current working directory.",
    )
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    payload = _build_payload(args)
    if args.dry_run:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        _write_output(args.output, payload)
        return 0

    login_identity = _login(args)
    auth_token = login_identity.get("auth_token") or (args.auth_token or "").strip()
    user_id = login_identity.get("user_id") or _resolve_user_id(args.user_id, auth_token)

    create_url = _task_url(args.base_url, args.api_prefix, user_id)
    created = _request_json(
        "POST",
        create_url,
        body=payload,
        token=auth_token,
        timeout=args.request_timeout,
    )
    task_id = str(created.get("id") or "")
    if not task_id:
        print(json.dumps(created, ensure_ascii=False, indent=2))
        raise SystemExit("Create response has no id")

    result = created
    if args.wait:
        deadline = time.time() + args.timeout_seconds
        poll_url = _task_url(args.base_url, args.api_prefix, user_id, task_id=task_id)
        while time.time() < deadline:
            result = _request_json(
                "GET",
                poll_url,
                token=auth_token,
                timeout=args.request_timeout,
            )
            status = str(result.get("status") or "").lower()
            if status in TERMINAL_STATUSES:
                break
            time.sleep(args.poll_interval)
        else:
            result = dict(result)
            result["pollTimeout"] = True

    try:
        local_video = _download_final_video(args, result, task_id)
    except SystemExit as exc:
        print(str(exc), file=sys.stderr)
        return 1
    if local_video:
        result = dict(result)
        result["localVideoPath"] = str(local_video)
        result_data = result.get("resultData")
        if isinstance(result_data, dict):
            result_data = dict(result_data)
            outputs = result_data.get("outputs")
            if isinstance(outputs, dict):
                outputs = dict(outputs)
                outputs["localVideoPath"] = str(local_video)
                result_data["outputs"] = outputs
            result["resultData"] = result_data

    print(json.dumps(result, ensure_ascii=False, indent=2))
    _write_output(args.output, result)
    status = str(result.get("status") or "").lower()
    return 1 if status == "failed" or result.get("pollTimeout") else 0


if __name__ == "__main__":
    raise SystemExit(main())
