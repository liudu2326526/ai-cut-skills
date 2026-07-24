# UserGrowth Code Map

The standalone runnable copy lives in this skill:

- `scripts/usergrowth_upload.py`: CLI entry for dry-run, selected videos, manifests, and live upload.
- `scripts/usergrowth_automation/`: vendored Python package copied from the desktop UserGrowth implementation.
- `scripts/requirements.txt`: runtime dependencies for the standalone tool.

The original source paths below are useful when comparing or syncing back to the AIVideoEditor backend repo.

Resolve original source paths from the AIVideoEditor backend repo root.

## Desktop Source

- `material_remix_desktop_source/app/tk_ui.py`
  Tk desktop entry. The `UserGrowth 自动上传` tab collects video folder, backfill Excel, song Excel, output dir, order ID, month tag, account/password, task name, concurrency, and dry-run/headless/recursive toggles. It previews via `build_usergrowth_plan`, runs one task via `run_usergrowth_task`, and runs queued batches via `run_usergrowth_batches`.

- `material_remix_desktop_source/app/usergrowth_models.py`
  Dataclasses and status carriers: `UserGrowthRunConfig`, `UserGrowthVideoItem`, `UserGrowthOrderPlan`, `UserGrowthBatchResult`, `UserGrowthCancelled`. Video suffixes: `.mp4`, `.mov`, `.mkv`, `.avi`.

- `material_remix_desktop_source/app/usergrowth_rules.py`
  Filename parsing and tag/classification rules. Material keywords include `金币音乐新high`, `金币音乐新mid`, `金币音乐新`, `金币音乐旧`, `金币下沉`, `金币VIP`, `金币SVIP`. Optional filename tags include `算法选歌`, `音综`, `衍生`, `量产`, `钩子`, `抖舞`. Classification paths currently use `LUNA_` prefixes.

- `material_remix_desktop_source/app/usergrowth_excel.py`
  Excel reader/writer. Loads song records from flexible headers, resolves song IDs from links, removes duplicate song names, writes duplicate songs to a separate workbook, and writes CID/material/song/tag results back to the backfill workbook. It ensures `歌曲名称` exists immediately after `CID` when no song-name column exists.

- `material_remix_desktop_source/app/usergrowth_planner.py`
  Builds upload plans from video files, song records, and the configured order ID. It attaches song ID/custom tags, skips blocked songs, skips files whose material type cannot be detected, and groups active items into `UserGrowthOrderPlan`.

- `material_remix_desktop_source/app/usergrowth_runner.py`
  Orchestrates one run or multiple batches. It creates the output task folder, writes `task.json`/`run.log`, separates dry-run from live browser upload, and serializes writes to the same backfill Excel path with an in-process lock.

- `material_remix_desktop_source/app/usergrowth_browser.py`
  Playwright client for UserGrowth. Handles login with OCR captcha, order search, creative-unit creation, upload, 录入变色龙, review submission, task polling, CID/material-type reading, error screenshots/text snapshots, and cancellation.

- `material_remix_desktop_source/app/usergrowth_captcha.py`
  Thin `ddddocr` wrapper. Raises `需要先安装 ddddocr 才能自动识别登录验证码` if the dependency is missing.

- `material_remix_desktop_source/requirements.txt`
  Desktop dependencies include `openpyxl`, `ddddocr`, `onnxruntime`, and `playwright`.

## Usual Edit Points

- Add or change filename/material/tag rules in `usergrowth_rules.py`; then verify planner and browser tag fill both use the intended month/tag behavior.
- Change song matching, CID backfill, or inserted Excel columns in `usergrowth_excel.py`; test with temporary workbooks.
- Change UI inputs or batch behavior in `tk_ui.py`, `usergrowth_models.py`, and `usergrowth_runner.py` together.
- Change browser selectors or live platform behavior in `usergrowth_browser.py`; use debug snapshots and avoid live upload unless explicitly authorized.
