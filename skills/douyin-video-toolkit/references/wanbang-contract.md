# Wanbang Contract

Use this reference when modifying `scripts/wanbang_douyin_batch_download.py`.

## Environment

- `WANBANG_API_KEY`
- `WANBANG_API_SECRET`
- `WANBANG_DOUYIN_BASE_URL`

The base URL should be the service root that exposes `item_get_video/` and `item_search_video/`.

## item_get_video

Request:

`GET {base}/item_get_video/?key=...&secret=...&item_id=<gid>&cache=no&result_type=json`

Successful responses may expose the direct video URL at:

- `item.video.url`
- `item.video.video_url`
- `video.url`
- `video.video_url`

Treat any non-empty `error_code` other than `0000` as a failure.

## item_search_video

Request:

`GET {base}/item_search_video/?key=...&secret=...&q=<keyword>&page=1&cache=no&result_type=json`

Search items may be present at:

- `items.item`
- `item`

Extract GID from `num_iid` or `item_id`, then build `https://www.douyin.com/video/<gid>`.

## Output Semantics

Use status values:

- `downloaded`: MP4 was downloaded in this run.
- `reused`: existing `<gid>.mp4` passed validation and was reused.
- `resolved`: `--no-download` was used.
- `failed`: API or download failed.

## Download Integrity

- Stream bytes into `<gid>.mp4.part`, never directly into the final path.
- Require a nontrivial file size and an MP4 `ftyp` header. When `ffprobe` exists, also require a readable positive duration.
- Rename the validated `.part` file to `<gid>.mp4` atomically.
- Delete `.part` after any exception or interruption.
- With `--skip-existing`, redownload a nonempty final file that fails validation.
