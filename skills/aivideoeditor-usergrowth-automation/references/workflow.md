# UserGrowth Workflow

## Inputs

A run is described by `UserGrowthRunConfig`:

- `video_folder`: folder scanned for `.mp4`, `.mov`, `.mkv`, `.avi`.
- `order_excel`: the backfill workbook.
- `song_excel`: the song library workbook.
- `output_root`: where task artifacts are written.
- `account`/`password`: only required for live upload.
- `order_id`: required; currently all active scanned items use this order ID.
- `task_name`, `month_tag`, `recursive`, `dry_run`, `headless`, `max_status_retries`, `refresh_interval_seconds`, `browser_slow_mo_ms`.

## Single Run

The standalone skill CLI uses `run_selected_usergrowth_task` in `scripts/usergrowth_upload.py` when specific videos are requested. The original desktop runner uses `run_usergrowth_task(config, progress, cancel_event)` for whole-folder runs.

The selected-video standalone flow performs:

1. Resolve selected files from `--video`, `--video-glob`, `--video-list`, manifest `videos`, or explicit `--all-videos`.
2. Create `<output_root>/<timestamp>_<safe_task_name>/`.
3. Create `debug/` and prepare `duplicate_songs.xlsx`.
4. Build a plan only for the selected paths.
5. Run dry-run or live browser upload.
6. Write `task.json` and `run.log`.

The original whole-folder flow performs:

1. Create `<output_root>/<timestamp>_<safe_task_name>/`.
2. Create `debug/` and prepare `duplicate_songs.xlsx`.
3. Call `build_usergrowth_plan(config, duplicate_song_output_path=...)`.
4. If no items were scanned, raise `未扫描到可处理视频`.
5. In dry-run mode, change pending items to `ready`, skip browser automation, and write `result.xlsx` with `include_ready=True`.
6. In live mode, create `UserGrowthBrowserClient`, upload active plans, and write successful orders back into the original backfill Excel after each order completes.
7. Write `task.json` and `run.log` under the task folder.

## Planning

`build_usergrowth_plan` scans videos, detects material type from filenames, extracts song names, loads song records, attaches song data, attaches order ID, and groups non-skipped items by order.

VIP/SVIP materials skip song matching and do not append a song ID tag. Blocked songs become `skipped`. Missing song ID or duplicate song candidates do not skip upload; they keep custom tags without the song ID and carry a warning message.

## Live Upload

Only plans whose status is not `skipped` are sent to the browser client. After a plan succeeds, `order_complete` calls:

```python
write_back_results(config.order_excel, config.order_excel, plan.items, include_ready=False)
```

The runner serializes writes per resolved Excel path, which protects same-process multi-batch writes. It does not protect against Excel/WPS having the file open.

## Batch Runs

`run_usergrowth_batches` uses `ThreadPoolExecutor`, clamps concurrency to `1..10`, gives each batch an independent browser run, and returns `UserGrowthBatchResult` in original batch order. If cancellation is set before a batch starts, that batch returns `cancelled`.

## Output Artifacts

- `task.json`: machine-readable config, summary, result path, duplicate song workbook path, and plans/items.
- `run.log`: summary and per-item status/type/song/CID/tags.
- `error.json` and `error.log`: task-level failure records when execution fails after the task folder is created.
- `<output_root>/_cli_errors/*.json` and `*.log`: early CLI failures before a task folder exists, when `output_root` was already parsed.
- `debug/run.log`: browser-level timing and error-snapshot metadata.
- `debug/*.txt` and `debug/*.png`: only written by error snapshots in current code because normal `_snapshot(..., screenshot=False)` returns early.

## Status Values

Common item statuses: `pending`, `ready`, `success`, `skipped`, `failed`, `cancelled`.

Common plan statuses: `pending`, `success`, `skipped`, `failed`, `cancelled`.
