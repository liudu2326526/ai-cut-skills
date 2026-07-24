# Capture Model

Use this reference when modifying or troubleshooting `scripts/download_douyin_share_videos.py`.

## Supported Inputs

- `https://www.douyin.com/video/<gid>`
- `https://www.douyin.com/share/video/<gid>`
- Pages with `modal_id`, `gid`, `video_id`, `item_id`, or `aweme_id`
- `https://v.douyin.com/...` short links after redirect resolution
- `https://chameleon.bytedance.com/open_api/video?video_id=...`

## Candidate Sources

Collect candidates from:

- Network responses whose URL or content type looks like MP4 video.
- JSON payloads containing `play_addr.url_list`.
- JSON payloads containing generic `url_list`.
- `video.bit_rate[].play_addr` when present in nested JSON.

Ignore placeholders such as `douyinstatic.com`, `lf-douyin-pc-web`, and `uuu_265.mp4`.

## Selection Heuristic

Choose the candidate with the greatest tuple:

1. `data_size`
2. `bit_rate`
3. `height`

This favors the highest quality candidate while keeping behavior deterministic.

## Diagnostics

Keep `_captures/*.json` because they are the fastest way to debug failures. The JSON should include source URL, canonical URL, final page URL, video ID, title, candidate count, selected candidate, and error when present.

