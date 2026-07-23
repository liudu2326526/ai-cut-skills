---
name: aivideoeditor-pre-roll
description: Create pre-roll videos with the standalone local runner. Use when Codex needs to preview, troubleshoot, or locally render a pre-roll/front-ad video from ad copy, visual type, asset strategy, subtitle placement, disclaimer text, required project/workspace logo image assets, auto-selecting light/dark logo variants from background brightness, local asset manifest understanding, or optional Ark/Seedance/TTS credentials and voice choices.
---

# AIVideoEditor Pre-roll

Use the standalone local runner bundled with this skill. This skill is designed for local rendering without any server connection or login.

Material assets should come from the caller's current project/workspace first. Do not assume the material folder has any fixed name; search the opened workspace/project and common roots such as `storage/temp`, `assets`, `materials`, `素材`, and `物料` for folders containing real Soda Music logos, SodaFont/方正兰亭 fonts, coin/reward screenshots, and body/overlay materials. Pass the discovered project paths explicitly through `--logo-light-path`, `--logo-dark-path`, `--subtitle-logo-path`, `--fonts-dir`, `--asset-root`, and `--asset-manifest`. Any material package inside the skill directory is only a compatibility fallback for local experiments, not the normal source of business material.

## Hard Rules

- Logo must come from a real image asset. Do not use typed text as a logo substitute.
- The persistent Soda Music logo is required and fixed at the top-left: crop transparent padding, render the real logo at 190px wide, x=40, y=40, opacity 1.0. Do not disable it or vary its size/position per request.
- Every deliverable video must include the persistent top-left Soda Music logo and the bottom-right visual-only disclaimer. These two layers are mandatory even when the user only asks for a quick test, disables main subtitles, or provides a custom payload.
- Deliverable videos must have real visual content. Do not use color blocks, procedural test animations, blank clips, or other placeholder footage as the main video.
- When revising an unsatisfactory video, always restart from a clean/uncomposited source video such as `baseVideoPath`, `revisionSourcePath`, `generatedVideoPath`, `scrapedVideoPath`, `imageVideoPath`, `backgroundVideo`, or `backgroundImage`. Do not use `finalVideoPath`, `final.mp4`, or any clip that already contains subtitles, logos, disclaimers, motion effects, BGM mixing, or overlays as the next input.
- Copy/subtitles must not contain `红包` or `花不完`; do not send those words to voiceover.
- Main subtitles must render `汽水音乐` and `汽水` with SodaFont, brand green `#3BFD42`, black outline, and a slightly larger scale by default. Other main subtitle text should use 方正兰亭.
- The visual-only disclaimer defaults to clear white `Microsoft YaHei` with a black outline. Do not apply subtitle motion effects to the disclaimer.
- When main subtitles contain `汽水音乐` or `汽水`, keep the normal subtitle font rule and additionally place a real logo/icon above that subtitle line.
- Ordinary overlay/insert materials should render below the main subtitle/disclaimer layers. Prefer fixing layer order over moving captions; only use `keywordMaterialOverlay.avoidSubtitleArea=true` when the material should also stay physically away from the caption area.
- Do not use arrow icons.
- Do not use unsafe source material: watermark or AI watermark, suggestive imagery, real visible faces, tattoos, known IP, film/TV stills, license plates, military/political content, or similar risky material.
- For old coin/reward screenshots, prefer big amounts over 10 yuan, except copy such as `下载汽水音乐之前`, `三毛`, or `五毛` can use small amounts. For new coin screenshots, use small amounts under 10 yuan; coin arrival amounts should stay under 50,000 coins.

## Material Understanding

For local visual materials, use the same scheme as the main-video Soda Music skill:

1. Locate the caller's project/workspace material folder by content, not by folder name. Prefer folders that contain logo images, SodaFont/方正兰亭 fonts, reward screenshots, and usable image/video overlay materials.
2. Run `sync-assets` to scan the caller's asset folder into `pre_roll_assets_manifest.json`.
3. The executing model must open/read every image and representative video frame that lacks understanding.
4. Write a concrete Chinese `description` and source-pixel `effective_region` back to each image/video record in the Manifest.
5. Run `validate` or standalone render preflight. Do not render while the Manifest is missing, `asset_root` differs, a visual asset lacks `description`, a visual asset lacks valid `effective_region`, or a referenced local visual path is not tracked.
6. When choosing ordinary overlay/insert materials, match by the Manifest `description`, not by filename, folder name, keywords, vectors, or a hidden material pool.
7. Only match ordinary materials to benefit-point narration. Each selected material item must record `semantic_role=benefit_point` and `matched_benefit_text`.

Read these before working with local materials:

- [references/asset-manifest.md](references/asset-manifest.md)
- [references/asset-content-understanding.md](references/asset-content-understanding.md)
- [references/asset-requirements.md](references/asset-requirements.md)

## Quick Start

Run from the skill directory.

Sync a caller-provided asset folder:

```powershell
python scripts\pre_roll_asset_manifest.py sync `
  --workspace "D:\my-pre-roll-work" `
  --asset-root "D:\my-pre-roll-work\assets"
```

If the Manifest reports missing understanding, inspect the assets yourself. For videos, export frames to view:

```powershell
python scripts\pre_roll_asset_manifest.py extract-frames `
  --asset-root "D:\my-pre-roll-work\assets" `
  --asset-manifest "D:\my-pre-roll-work\pre_roll_assets_manifest.json" `
  --output-dir "D:\my-pre-roll-work\asset_frames" `
  --only-missing
```

After filling `description` and `effective_region`, validate:

```powershell
python scripts\pre_roll_asset_manifest.py validate `
  --asset-root "D:\my-pre-roll-work\assets" `
  --asset-manifest "D:\my-pre-roll-work\pre_roll_assets_manifest.json" `
  --required-path "D:\my-pre-roll-work\assets\logo\logo-dark.png"
```

Standalone dry-run with Manifest preflight:

```powershell
python scripts\run_pre_roll_standalone.py --dry-run `
  --script-text "每天听歌15分钟，你的余额就会一直涨" `
  --visual-template-id decompression `
  --asset-strategy generated `
  --subtitle-position lower_center `
  --asset-preflight off
```

Subtitle logo trigger example:

```powershell
python scripts\run_pre_roll_standalone.py --script-text "打开汽水音乐，每天听歌15分钟" `
  --visual-template-id decompression `
  --asset-strategy generated `
  --ark-api-key "$env:ARK_API_KEY" `
  --logo-light-path "D:\assets\logo\汽水logo-白色竖版.png" `
  --logo-dark-path "D:\assets\logo\汽水logo-黑色竖版.png" `
  --subtitle-logo-path "D:\assets\logo\汽水图标.png" `
  --subtitle-logo-width-ratio 0.18
```

## Minimal Inputs

Prefer these as the default user-facing form:

- `scriptText`: spoken copy and main subtitle text.
- `visualTemplateId`: `decompression`, `scenery`, `gold_reward`, `chinese_fortune`, `pet_funny`, `ai_lifestyle`, or `ai_beauty_image`.
- `assetStrategy`: `generated`, `local_video`, `local_image`, or `scraped`.
- `subtitleConfig.position`: usually `lower_center`.
- `assetRoot` and `assetManifest`: required when the caller wants project/workspace materials to participate in overlay/insert matching, or when logo/font/icon discovery is ambiguous. The folder name is not fixed; use the discovered material root.

## Standalone Mode

Read and use [scripts/run_pre_roll_standalone.py](scripts/run_pre_roll_standalone.py) for local rendering.

Standalone mode can:

- use a caller-supplied background video or image
- preserve the clean background as the revision source so later edits can recompose from a fresh base
- optionally call Ark/Seedance with `--ark-api-key`
- generate subtitles and a visual-only disclaimer locally
- overlay a caller-supplied logo image on every render
- render the persistent top-left logo with fixed placement and fixed size
- force the visual-only bottom-right disclaimer on every render, falling back to the default text when a caller passes an empty value
- use project/workspace Soda Music logos/fonts/icons by passing the discovered real asset paths explicitly
- optionally place a second logo/icon above subtitle lines that contain `汽水音乐` or `汽水`
- choose `dark` or `light` logo automatically from the rendered background's overall brightness
- validate local visual assets against `pre_roll_assets_manifest.json`
- let you vary narration voices with `--voice-name`; you can pass multiple candidates separated by `|`
- render brand words with SodaFont and normal main subtitle text with 方正兰亭
- block forbidden copy terms before voiceover/subtitle generation
- use `--ffmpeg` and `--ffprobe` when FFmpeg is not on PATH

Recommended inputs:

- `--script-text`
- `--visual-template-id`
- `--asset-strategy generated` with `--ark-api-key`, or `--asset-strategy local_video/local_image/scraped` with a real background source
- `--background-video` or `--background-image` or `--background-url`
- `--asset-root` and `--asset-manifest` when extra local visual files are used
- `--asset-preflight required` for production renders; dry-run will return the preflight report without stopping
- `--material-selection-json` when the caller has chosen insert/overlay materials that need semantic gate checks
- `--voiceover-path` or `--local-tts`
- `--logo-path`, or `--logo-light-path` plus `--logo-dark-path`
- `--subtitle-logo-path` when you want a specific real icon above subtitles that contain `汽水音乐` or `汽水`
- `--no-bundled-assets` only as a compatibility/debug option; normal renders should first find project/workspace material paths and pass them explicitly
- `--no-subtitle-logo-enabled` to disable that subtitle-triggered logo layer
- `--fonts-dir`, or `--body-font-path` plus `--brand-font-path`
- `--voice-name` if you want one voice or a small voice pool, for example `VoiceA|VoiceB`
- `--subtitle-position`
- `--brand-primary-color`, `--brand-outline-color`, and `--brand-font-scale` when overriding the Soda Music word highlight
- `--subtitle-audio-sync auto`
- `--subtitle-offset-seconds 0.2` when a specific voice still feels early or late
- `--disclaimer-text`; this customizes the mandatory bottom-right disclaimer text and cannot disable it
- `--output`

Before rendering, search the current project/workspace for real Soda Music logo variants and the subtitle-triggered icon, then pass those paths explicitly. If both light and dark logo variants are available, pass `--logo-light-path` and `--logo-dark-path` so the runner can pick the right one for the background. The selected caller-provided logo path must exist in the Manifest when `--asset-preflight required` is active. Use skill-directory assets only as a last-resort compatibility fallback for local experiments.

Do not use `--brand-text` as a logo replacement.

Do not use `--no-include-disclaimer-subtitle` for deliverables. The runner keeps that option only so old commands do not fail, but production output must still include the right-bottom disclaimer.

Do not use `assetStrategy=procedural`. The standalone runner only accepts real visual sources: generated, local video, local image, or scraped/direct video URL.

For revisions, keep the first clean source and rerun composition from it. The final deliverable is only for review/delivery; it should not be used as a background for another render, because logos, subtitles, disclaimers, and animation layers would be baked in twice.

Always start from the standalone runner. Local files are read from the current machine only, so keep assets under the workspace and run the Manifest workflow before rendering.

## Troubleshooting

Use [references/troubleshooting.md](references/troubleshooting.md) for task failures, missing URLs, auth errors, and subtitle issues.
