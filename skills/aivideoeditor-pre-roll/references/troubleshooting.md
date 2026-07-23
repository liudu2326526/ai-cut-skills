# Troubleshooting

Use this guide for the standalone local runner. The skill should not require any server connection, account login, user ID, auth token, queue, or external project.

## Runner Does Not Start

Check:

- Python is available in the current IDE terminal.
- `ffmpeg` and `ffprobe` are on PATH, or pass `--ffmpeg` and `--ffprobe`.
- The command is run from the skill directory or uses absolute paths.
- The output folder is writable.

## Missing Real Video Content

Deliverables cannot use placeholders. Provide one of:

- `--background-video`
- `--background-image`
- `--background-url`
- `--asset-strategy generated` with `--ark-api-key`

If generated video is unavailable, use a clean local or scraped source video instead.

## Asset Manifest Problems

When extra local visual materials are used, run `sync-assets`, inspect missing assets, fill `description` and `effective_region`, then run `validate`.

If validation fails, fix the Manifest before rendering. Do not bypass the Manifest for selected overlay/insert materials.

## Logo Or Disclaimer Missing

Treat the render as invalid. Every deliverable must have:

- fixed top-left Soda Music logo from a real bundled or caller-provided image
- bottom-right visual-only disclaimer

`--no-include-disclaimer-subtitle` is compatibility-only and should not remove the mandatory disclaimer.

## Duplicate Logo, Subtitle, Disclaimer, Or Effects

This usually means a revision used the previous `final.mp4` as the new background. Rerun from the clean source instead: `revisionSourcePath`, `baseVideoPath`, `generatedVideoPath`, `scrapedVideoPath`, `imageVideoPath`, the original `backgroundVideo`/`backgroundImage`, or the original source URL.

Do not reprocess a file that already contains baked-in subtitles, top-left logo, subtitle-triggered icon, disclaimer text, BGM mix, or overlay/insert materials.

## Subtitle Problems

If subtitles are missing, confirm the runner received `--script-text`.

If subtitles overflow or touch the edge, adjust:

- `subtitleConfig.fontSize`
- `subtitleConfig.maxLines`
- `subtitleConfig.safeMarginRatio`
- `subtitleConfig.bottomMarginRatio`

Use `lower_center` for the main subtitle and `bottom_right` for the small disclaimer.

If subtitles appear before the voice starts, standalone mode detects leading silence automatically with `subtitleAudioSync: "auto"`. Check the output JSON under `steps.subtitleSync.offsetSeconds`.

If subtitles still feel early or late for a specific voice, set `subtitleOffsetSeconds`, for example `0.25` to delay subtitles by 0.25 seconds or `-0.15` to show them earlier.
