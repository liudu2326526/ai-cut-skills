from __future__ import annotations

import argparse
import asyncio
import json
import os
import re
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse
import urllib.request

DEFAULT_OUT_DIR = Path("downloads/douyin")
DEFAULT_USER_DATA_DIR = Path.home() / ".codex" / "skill-data" / "douyin-video-downloader-edge-profile"
DEFAULT_URLS: list[str] = []


def resolve_redirect_url(url: str) -> str:
    parsed = urlparse(url)
    if not parsed.netloc.endswith("v.douyin.com"):
        return url
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0.0.0 Safari/537.36"
            ),
        },
        method="GET",
    )
    with urllib.request.urlopen(req, timeout=20) as response:
        return response.geturl() or url


def video_id_from_url(url: str) -> str:
    parsed = urlparse(url)
    query = parse_qs(parsed.query)
    for key in ("modal_id", "gid", "video_id", "item_id", "aweme_id"):
        value = (query.get(key) or [""])[0]
        if value:
            return re.sub(r"[^A-Za-z0-9_-]+", "_", value)

    match = re.search(r"/(?:share/)?video/(\d+)", parsed.path)
    if match:
        return match.group(1)

    resolved = resolve_redirect_url(url)
    if resolved != url:
        return video_id_from_url(resolved)

    raise ValueError(f"Cannot find video id in URL: {url}")


def canonical_video_url(url: str) -> str:
    if is_chameleon_video_url(url):
        return url
    return f"https://www.douyin.com/video/{video_id_from_url(url)}"


def is_chameleon_video_url(url: str) -> bool:
    parsed = urlparse(url)
    return (
        parsed.netloc.endswith("chameleon.bytedance.com")
        and parsed.path == "/open_api/video"
        and bool(parse_qs(parsed.query).get("video_id", [""])[0])
    )


def looks_like_video_url(url: str, content_type: str = "") -> bool:
    if is_placeholder_video_url(url):
        return False
    if "video" in content_type.lower() and "mp4" in content_type.lower():
        return True
    return bool(
        re.search(
            r"(douyinvod|byted-vod|mime_type=video_mp4|/aweme/v1/play/|__vid=)",
            url,
            re.I,
        )
    )


def is_placeholder_video_url(url: str) -> bool:
    lowered = url.lower()
    return (
        "uuu_265.mp4" in lowered
        or "douyinstatic.com" in lowered
        or "lf-douyin-pc-web" in lowered
    )


def walk_json(value: Any):
    if isinstance(value, dict):
        yield value
        for child in value.values():
            yield from walk_json(child)
    elif isinstance(value, list):
        for child in value:
            yield from walk_json(child)


def collect_video_candidates(payload: dict[str, Any]) -> list[dict[str, Any]]:
    candidates: list[dict[str, Any]] = []

    for node in walk_json(payload):
        play_addr = node.get("play_addr")
        if isinstance(play_addr, dict):
            urls = play_addr.get("url_list")
            if isinstance(urls, list):
                for url in urls:
                    if isinstance(url, str) and looks_like_video_url(url):
                        candidates.append(
                            {
                                "url": url,
                                "source": "play_addr",
                                "bit_rate": node.get("bit_rate", 0),
                                "data_size": play_addr.get("data_size", 0),
                                "width": play_addr.get("width", 0),
                                "height": play_addr.get("height", 0),
                            }
                        )

        urls = node.get("url_list")
        if isinstance(urls, list):
            for url in urls:
                if isinstance(url, str) and looks_like_video_url(url):
                    candidates.append(
                        {
                            "url": url,
                            "source": "url_list",
                            "bit_rate": node.get("bit_rate", 0),
                            "data_size": node.get("data_size", 0),
                            "width": node.get("width", 0),
                            "height": node.get("height", 0),
                        }
                    )

    deduped: dict[str, dict[str, Any]] = {}
    for item in candidates:
        deduped[item["url"]] = item
    return list(deduped.values())


def choose_candidate(candidates: list[dict[str, Any]]) -> dict[str, Any] | None:
    candidates = [
        item for item in candidates if not is_placeholder_video_url(str(item.get("url") or ""))
    ]
    if not candidates:
        return None
    return max(
        candidates,
        key=lambda item: (
            int(item.get("data_size") or 0),
            int(item.get("bit_rate") or 0),
            int(item.get("height") or 0),
        ),
    )


async def download_bytes(context, url: str, referer: str, out_path: Path) -> int:
    response = await context.request.get(
        url,
        headers={
            "Referer": referer,
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0.0.0 Safari/537.36"
            ),
        },
        timeout=120000,
    )
    if not response.ok:
        raise RuntimeError(f"Download failed: HTTP {response.status}")
    body = await response.body()
    out_path.write_bytes(body)
    return len(body)


def download_http_file(url: str, referer: str, out_path: Path) -> int:
    req = urllib.request.Request(
        url,
        headers={
            "Referer": referer,
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0.0.0 Safari/537.36"
            ),
        },
    )
    size = 0
    with urllib.request.urlopen(req, timeout=180) as response:
        status = getattr(response, "status", 200)
        if status >= 400:
            raise RuntimeError(f"Download failed: HTTP {status}")
        with open(out_path, "wb") as f:
            while True:
                chunk = response.read(1024 * 1024)
                if not chunk:
                    break
                f.write(chunk)
                size += len(chunk)
    return size


async def capture_one(context, source_url: str, index: int, out_dir: Path, capture_dir: Path) -> dict[str, Any]:
    video_id = video_id_from_url(source_url)
    page_url = canonical_video_url(source_url)

    if is_chameleon_video_url(source_url):
        out_path = out_dir / f"{index:02d}_{video_id}.mp4"
        try:
            size = await asyncio.to_thread(download_http_file, source_url, source_url, out_path)
            result = {
                "source_url": source_url,
                "canonical_url": page_url,
                "final_page_url": source_url,
                "video_id": video_id,
                "title": "",
                "file": str(out_path),
                "size": size,
                "candidate": {
                    "url": source_url,
                    "source": "chameleon_open_api",
                    "bit_rate": 0,
                    "data_size": size,
                    "width": 0,
                    "height": 0,
                },
                "ok": True,
            }
        except Exception as exc:
            result = {
                "source_url": source_url,
                "canonical_url": page_url,
                "video_id": video_id,
                "title": "",
                "error": str(exc),
                "ok": False,
            }

        (capture_dir / f"{index:02d}_{video_id}.json").write_text(
            json.dumps([{"result": result}], ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        return result

    page = await context.new_page()
    records: list[dict[str, Any]] = []
    candidates: list[dict[str, Any]] = []
    title = ""

    async def on_response(response):
        nonlocal title
        url = response.url
        content_type = response.headers.get("content-type", "")
        if looks_like_video_url(url, content_type):
            candidates.append(
                {
                    "url": url,
                    "source": "network",
                    "bit_rate": 0,
                    "data_size": 0,
                    "width": 0,
                    "height": 0,
                }
            )

        if "aweme/detail" not in url or f"aweme_id={video_id}" not in url:
            return

        item = {"status": response.status, "content_type": content_type, "url": url}
        try:
            body = await response.text()
            payload = json.loads(body)
            detail = payload.get("aweme_detail") or {}
            title = detail.get("item_title") or detail.get("desc") or ""
            candidates.extend(collect_video_candidates(payload))
            item["title"] = title
            item["candidate_count"] = len(candidates)
        except Exception as exc:
            item["error"] = str(exc)
        records.append(item)

    page.on("response", on_response)

    try:
        await page.goto(page_url, wait_until="domcontentloaded", timeout=60000)
        try:
            await page.wait_for_response(
                lambda r: "aweme/detail" in r.url and f"aweme_id={video_id}" in r.url,
                timeout=45000,
            )
        except Exception:
            pass

        await page.wait_for_timeout(8000)

        if not title:
            title = await page.title()

        await page.screenshot(path=str(capture_dir / f"{index:02d}_{video_id}.png"), full_page=True)
        chosen = choose_candidate(candidates)
        if not chosen:
            raise RuntimeError("No video candidate found")

        out_path = out_dir / f"{index:02d}_{video_id}.mp4"
        size = await download_bytes(context, chosen["url"], page.url, out_path)
        result = {
            "source_url": source_url,
            "canonical_url": page_url,
            "final_page_url": page.url,
            "video_id": video_id,
            "title": title,
            "file": str(out_path),
            "size": size,
            "candidate": chosen,
            "ok": True,
        }
    except Exception as exc:
        result = {
            "source_url": source_url,
            "canonical_url": page_url,
            "video_id": video_id,
            "title": title,
            "error": str(exc),
            "ok": False,
        }
    finally:
        records.append({"result": result, "candidate_count": len(candidates)})
        (capture_dir / f"{index:02d}_{video_id}.json").write_text(
            json.dumps(records, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        await page.close()

    return result


def detect_start_index(out_dir: Path, start_index: int) -> int:
    if start_index > 0:
        return start_index

    max_index = 0
    for path in out_dir.glob("*.mp4"):
        match = re.match(r"(\d+)_", path.name)
        if match:
            max_index = max(max_index, int(match.group(1)))
    return max_index + 1 if max_index else 1


def load_existing_results(summary_path: Path) -> list[dict[str, Any]]:
    if not summary_path.exists():
        return []
    try:
        data = json.loads(summary_path.read_text(encoding="utf-8"))
    except Exception:
        return []
    return data if isinstance(data, list) else []


def detect_linux_chromium_executable() -> Path | None:
    cache_root = Path.home() / ".cache" / "ms-playwright"
    candidates = sorted(cache_root.glob("chromium-*/chrome-linux/chrome"), reverse=True)
    for path in candidates:
        if path.exists():
            return path
    return None


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Batch download Douyin share videos with Playwright.")
    parser.add_argument("--out-dir", type=Path, default=DEFAULT_OUT_DIR, help="Directory for MP4 files and summary.json")
    parser.add_argument("--url", action="append", dest="urls", default=[], help="Share URL to download. Can be passed multiple times.")
    parser.add_argument("--urls-file", type=Path, help="UTF-8 text file containing one share URL per line.")
    parser.add_argument(
        "--user-data-dir",
        type=Path,
        default=DEFAULT_USER_DATA_DIR,
        help="Persistent Edge profile directory for Playwright.",
    )
    parser.add_argument("--headed", action="store_true", help="Run Edge with a visible window.")
    parser.add_argument(
        "--start-index",
        type=int,
        default=0,
        help="Starting sequence number for output filenames. Default 0 means auto-continue from existing files.",
    )
    parser.add_argument(
        "--browser-channel",
        choices=["auto", "msedge", "chromium"],
        default="auto",
        help="Browser channel to use. 'auto' uses msedge on Windows and bundled Chromium elsewhere.",
    )
    parser.add_argument(
        "--executable-path",
        type=Path,
        help="Optional browser executable path. Useful on Linux/WSL when reusing an existing Chromium binary.",
    )
    return parser.parse_args()


def load_urls(args: argparse.Namespace) -> list[str]:
    urls = list(args.urls)
    if args.urls_file:
        lines = args.urls_file.read_text(encoding="utf-8").splitlines()
        urls.extend(line.strip() for line in lines if line.strip())
    return urls or DEFAULT_URLS


async def main() -> None:
    try:
        from playwright.async_api import async_playwright
    except ImportError as exc:
        raise RuntimeError("Playwright is required. Install with: python -m pip install playwright") from exc

    args = parse_args()
    urls = load_urls(args)
    if not urls:
        raise RuntimeError("No URLs provided. Use --url or --urls-file.")

    out_dir = args.out_dir
    capture_dir = out_dir / "_captures"
    summary_path = out_dir / "summary.json"
    user_data_dir = args.user_data_dir

    out_dir.mkdir(parents=True, exist_ok=True)
    capture_dir.mkdir(parents=True, exist_ok=True)
    user_data_dir.mkdir(parents=True, exist_ok=True)

    start_index = detect_start_index(out_dir, args.start_index)
    existing_results = load_existing_results(summary_path)
    results: list[dict[str, Any]] = []

    browser_channel = args.browser_channel
    launch_kwargs = {
        "headless": not args.headed,
        "viewport": {"width": 1365, "height": 900},
        "locale": "zh-CN",
        "args": ["--disable-blink-features=AutomationControlled"],
    }
    if browser_channel == "auto":
        browser_channel = "msedge" if os.name == "nt" else "chromium"
    if browser_channel == "msedge":
        launch_kwargs["channel"] = "msedge"
    elif args.executable_path:
        launch_kwargs["executable_path"] = str(args.executable_path)
    else:
        chromium_path = detect_linux_chromium_executable()
        if chromium_path is not None:
            launch_kwargs["executable_path"] = str(chromium_path)

    async with async_playwright() as p:
        context = await p.chromium.launch_persistent_context(
            str(user_data_dir),
            **launch_kwargs,
        )
        for offset, url in enumerate(urls, start=0):
            index = start_index + offset
            print(f"[{offset + 1}/{len(urls)}] #{index:02d} {url}")
            result = await capture_one(context, url, index, out_dir, capture_dir)
            results.append(result)
            print("  ok" if result["ok"] else f"  failed: {result['error']}")
        await context.close()

    merged_results = existing_results + results
    summary_path.write_text(json.dumps(merged_results, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"wrote {summary_path}")


if __name__ == "__main__":
    asyncio.run(main())
