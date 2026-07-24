---
name: douyin-video-toolkit
description: Standalone Douyin video toolkit for downloading, browser-capturing, batch-processing, and diagnosing Douyin videos. Use when Codex needs to download one or many Douyin URLs, modal_id/gid/v.douyin.com short links, capture browser video/mp4 streams with a Chrome/Edge MV3 extension, package the collector extension, call Wanbang item_get_video or item_search_video for GID/keyword batch downloads, process TXT/CSV/XLSX URL or keyword lists, inspect run.log/summary.json/_captures failure logs after failed or interrupted tasks, or troubleshoot Douyin CDN Referer, aweme ID mapping, stale stream, incomplete MP4, and capture diagnostics without depending on the AIVideoEditor backend.
---

# Douyin Video Toolkit

## Overview

Use this skill as a self-contained toolkit for three Douyin video workflows:

- Page capture download: `scripts/download_douyin_share_videos.py`
- Browser-side stream collection: `assets/aivideo-collector-extension` plus `scripts/package_extension.py`
- Wanbang/GID batch download: `scripts/wanbang_douyin_batch_download.py`

The scripts and extension do not import the AIVideoEditor backend. Backend recording is optional for the browser extension only.

## Choose A Path

Use Playwright page capture when the user has one or more Douyin page/share URLs and wants MP4 files without Wanbang credentials.

Use the browser collector when the video plays in the user's Chrome/Edge session, when login/captcha/session state matters, or when the user wants local browser downloads from current-tab video streams.

Use Wanbang/GID batch when the user has many URLs/GIDs, an Excel/CSV/TXT list, or keywords, and has Wanbang credentials for API-based resolution and download.

Use Playwright page capture as fallback when Wanbang does not return a usable direct URL. Use browser collector as fallback when server-side/browser-automation capture is blocked but the user's own browser can play the video.

## Playwright Page Download

Install dependencies if needed:

```powershell
python -m pip install playwright
python -m playwright install chromium
```

Download one URL:

```powershell
python C:\Users\Donson\.codex\skills\douyin-video-toolkit\scripts\download_douyin_share_videos.py --url "https://www.douyin.com/video/7380000000000000001" --out-dir "downloads\douyin"
```

Download many URLs:

```powershell
python C:\Users\Donson\.codex\skills\douyin-video-toolkit\scripts\download_douyin_share_videos.py --urls-file ".\douyin-urls.txt" --out-dir "downloads\douyin"
```

Use `--headed` for login, captcha, or visual debugging. The script supports `/video/<id>`, `/share/video/<id>`, `modal_id`, `gid`, `video_id`, `item_id`, `aweme_id`, `v.douyin.com` redirects, and Chameleon open API video URLs.

Outputs include MP4 files, `run.log`, `summary.json`, and `_captures/*.json` diagnostics. Read `references/capture-model.md` before changing candidate extraction or quality selection.

## Browser Collector Extension

Package the extension:

```powershell
python C:\Users\Donson\.codex\skills\douyin-video-toolkit\scripts\package_extension.py --output ".\aivideo-collector-extension.zip"
```

Package with custom optional backend settings:

```powershell
python C:\Users\Donson\.codex\skills\douyin-video-toolkit\scripts\package_extension.py `
  --output ".\aivideo-collector-extension.zip" `
  --api-base "https://api.example.com/api/v1" `
  --app-origins "https://app.example.com,http://127.0.0.1:5176" `
  --self-hostnames "api.example.com,127.0.0.1"
```

For manual install, load `assets/aivideo-collector-extension` unpacked in Chrome/Edge developer mode. Open the video page, play it once, open the side panel, select captured candidates, and download.

Local browser download happens before optional backend recording. If no backend/login exists, files can still download locally while record sync fails. Read `references/record-protocol.md` before changing the optional backend payload or capture filters.

## Wanbang/GID Batch

Set credentials when doing keyword search or real downloads:

```powershell
$env:WANBANG_API_KEY = "..."
$env:WANBANG_API_SECRET = "..."
$env:WANBANG_DOUYIN_BASE_URL = "https://..."
```

Install XLSX support only when reading Excel:

```powershell
python -m pip install openpyxl
```

Download URLs/GIDs:

```powershell
python C:\Users\Donson\.codex\skills\douyin-video-toolkit\scripts\wanbang_douyin_batch_download.py `
  --url "https://www.douyin.com/video/7380000000000000001" `
  --gid "7390000000000000002" `
  --out-dir ".\downloads\douyin-gid"
```

Download from XLSX:

```powershell
python C:\Users\Donson\.codex\skills\douyin-video-toolkit\scripts\wanbang_douyin_batch_download.py `
  --urls-file ".\douyin_urls.xlsx" `
  --url-column "抖音链接" `
  --out-dir ".\downloads\douyin-gid"
```

Search by keyword:

```powershell
python C:\Users\Donson\.codex\skills\douyin-video-toolkit\scripts\wanbang_douyin_batch_download.py `
  --keyword "美甲" `
  --max-per-keyword 12 `
  --out-dir ".\downloads\douyin-keyword"
```

Use `--no-download` to resolve/query only, `--skip-existing` to reuse an existing `<gid>.mp4` only after MP4 validation, and `--sleep` to wait between videos. Downloads first write `<gid>.mp4.part`; only a validated complete file is atomically renamed to `<gid>.mp4`. Outputs are `<gid>.mp4`, `run.log`, `summary.json`, and `summary.csv`. Read `references/wanbang-contract.md` before changing API parsing.

## Failure And Logs

For CLI runs, inspect the selected `--out-dir` first. Start with `run.log`, then `summary.json`, then any workflow-specific files:

- Playwright page capture: `_captures/NN_<video_id>.json` and `_captures/NN_<video_id>.png`.
- Wanbang/GID batch: `summary.csv` and each `<gid>.mp4`.
- Browser collector: extension side panel status, browser downloads page, extension service worker console, and current tab DevTools console.

Read `references/failure-logs.md` whenever a task fails, is interrupted, or produces incomplete output.

## Safety And Limits

Use only content the user is authorized to download. These tools capture normal browser-accessible streams or normal API/video URLs and do not bypass DRM.
