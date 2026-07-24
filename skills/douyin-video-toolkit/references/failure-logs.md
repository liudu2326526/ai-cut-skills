# Failure Logs

Use this reference when a Douyin video toolkit task fails, is interrupted, or produces incomplete output.

## First Files To Check

For CLI runs, always start in the `--out-dir` directory:

1. `run.log`: chronological run events, item starts, item failures, summary writes, and interruption markers.
2. `summary.json`: structured result list. For interrupted batch runs, it contains completed items up to the most recent successful summary write.
3. `summary.csv`: Wanbang/GID batch only; spreadsheet-friendly copy of `summary.json`.
4. `_captures/*.json`: Playwright page capture only; per-video network responses, candidate counts, selected candidate, final page URL, and error.
5. `_captures/*.png`: Playwright page screenshots created before selecting/downloading a candidate.

## Playwright Page Capture

Expected files:

- `<out-dir>/run.log`
- `<out-dir>/summary.json`
- `<out-dir>/_captures/NN_<video_id>.json`
- `<out-dir>/_captures/NN_<video_id>.png` when the page reached screenshot stage
- `<out-dir>/NN_<video_id>.mp4` for successful downloads

Read `_captures/NN_<video_id>.json` when:

- `summary.json` has `"ok": false`
- `run.log` says `item_failed`
- the MP4 is missing or tiny
- the tool reports `No video candidate found`

Important fields:

- `final_page_url`: confirm redirects and page context.
- `candidate_count`: zero means no usable stream was captured.
- `result.error`: direct failure reason.
- `result.candidate`: chosen video URL and quality metadata.

If interrupted during a page capture, the per-item capture JSON may contain `"capture interrupted before result was produced"` and `summary.json` may not include that in-flight item.

## Wanbang/GID Batch

Expected files:

- `<out-dir>/run.log`
- `<out-dir>/summary.json`
- `<out-dir>/summary.csv`
- `<out-dir>/<gid>.mp4` for `downloaded` or `reused` items

Read `summary.json` when:

- a subset failed and the batch continued
- the run was interrupted
- you need to retry only failed GIDs

Important fields:

- `status`: `downloaded`, `reused`, `resolved`, or `failed`
- `gid`: canonical item ID
- `video_url`: canonical Douyin page URL
- `path`: local MP4 path when available
- `error`: Wanbang/API/download failure reason

If preparation fails before references are built, `run.log` contains `prepare_failed`.

## Browser Collector Extension

Browser extension runs do not write files into the skill directory. Check:

- The extension side panel status text for download and record failures.
- Chrome/Edge `chrome://downloads` or `edge://downloads` for local file success/failure.
- Extension service worker DevTools console for background capture logs.
- Current Douyin tab DevTools console for `[douyin-main]` and `[douyin-bridge]` logs.
- Network panel for CDN responses that returned HTML, 403, 416, or partial content.

Common extension log prefixes:

- `[capture]`: active-tab video/mp4 response capture.
- `[referer-injector]`: dynamic Referer injection rules.
- `[douyin-main]`: page-world Douyin aweme/video URL extraction.
- `[douyin-bridge]`: forwarding extracted mappings to the extension.
- `[aweme-map]`: aweme ID to video URL mapping updates.
- `[download]`: blob size mismatch or incomplete local downloads.
- `[record]`: optional backend record sync failures.

If local download succeeds but record sync fails, keep the downloaded browser file and inspect the side panel/console error before retrying backend recording.

## Retry Guidance

- For stale CDN URLs, replay/refresh the Douyin page and recapture.
- For login/captcha/session issues, rerun Playwright with `--headed` or use the browser collector.
- For Wanbang API failures, retry failed GIDs from `summary.json`; keep the previous summary for audit.
- For incomplete MP4 files, compare file size with `summary.json` or extension candidate size, then recapture at the desired player quality.

