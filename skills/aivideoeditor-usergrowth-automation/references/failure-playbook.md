# Failure Playbook

Use the task folder and `debug/` artifacts first. Ask for or inspect `task.json`, `run.log`, `error.json`, `error.log`, `debug/run.log`, and the newest `debug/*.png`/`*.txt` when live automation fails.

## Where To Read Logs

- Normal dry-run success
  Read `<output-root>/<timestamp>_<task-name>/task.json`, `run.log`, and `result.xlsx`.

- Normal live success or per-order platform failure
  Read `<output-root>/<timestamp>_<task-name>/task.json` and `run.log`. For browser/platform failures, also read `debug/run.log` and the newest `debug/*.png`/`debug/*.txt`.

- Failure after a task folder has been created
  Read `<output-root>/<timestamp>_<task-name>/error.json` and `error.log`. These include error type, message, selected videos, sanitized config, and Python traceback. If the browser had already started, also read `debug/run.log` and error snapshots.

- Failure before task execution, such as unmatched video selectors
  Read the CLI stderr. If `output_root` was already parsed, also check `<output-root>/_cli_errors/*.json` and `*.log`.

- Hard kill, power loss, or process termination
  Only logs flushed before termination will exist. Check the latest task folder under `output_root`, then `error.*`, `task.json`, `run.log`, and `debug/` in that order.

## File Meanings

- `task.json`: final structured result when the task reaches normal completion; contains config, summary, selected videos, plans and item statuses.
- `run.log`: final human-readable summary when the task reaches normal completion.
- `error.json`: structured failure record for task-level exceptions.
- `error.log`: human-readable failure record and traceback.
- `debug/run.log`: browser timing, browser error snapshot metadata, exception type/message/traceback for `_snapshot_error`.
- `debug/<name>.txt`: page URL and body text at the failing browser step.
- `debug/<name>.png`: full-page screenshot at the failing browser step.
- `duplicate_songs.xlsx`: duplicate song-name records relevant to the selected batch, when duplicates are found.

## Common Failures

- `需要先安装 playwright，并执行 playwright install chromium`
  Check `material_remix_desktop_source/requirements.txt`, install dependencies in the desktop environment, then run browser install for Chromium if needed.

- `需要先安装 ddddocr 才能自动识别登录验证码`
  Install desktop dependencies including `ddddocr` and `onnxruntime`.

- Login fails after 5 attempts
  Inspect `login_failed_*` snapshots. Check account/password, captcha image detection, whether the login page changed, and whether `/home` still shows `墨攻AI` or `采购中心`.

- Cannot enter work order management
  Inspect `work_order_not_reached`. Confirm `墨攻AI`, `工单管理`, and `素材管理` labels still exist or update selectors/text.

- Order not found
  Inspect `order_<id>_not_found`. Verify the order ID, placeholder `订单名称或ID`, and whether search needs a different event than Enter.

- Cannot click `新建创意单元`
  Inspect `order_<id>_create_button_not_found` or `create_click_no_effect`. Check scoped row selection, exact text, nearby button logic, and coordinate fallback.

- Upload page/input missing
  Check `_looks_like_upload_page`, `input[type='file']`, `点击或拖拽`, `文件上传`, and `温馨提示`. Platform UI may have changed the upload control.

- Upload limit zero or too many files
  Compare `plan.upload_limit`, item count, and page text. The code recognizes `当前选择文件数量超过订单创意单元上限` and reads numeric limits from several patterns.

- Waiting upload cards forever
  Check whether success icons are still `span.arco-upload-list-success-icon`. If the platform changed icons, update `_wait_upload_cards_ready`.

- Chameleon modal validation fails
  Inspect `chameleon_delivery_*` snapshots. Check `投放产品`, `汽水音乐`, and `投放平台` dropdown behavior.

- Cascader selection fails
  Inspect console/debug output around `级联选择失败`. Confirm `LUNA_` labels and field names: `汽水音乐-素材类型`, `LUNA素材来源`, `LUNA功能卖点`.

- Task never becomes `全部成功`
  Inspect task row text and refresh behavior. `_wait_task_success` and `_wait_task_row_success` fail on `已失败`/`失败`.

- CID count mismatch
  Inspect `task_<id>_cid_count_mismatch`. Check material list search input, copy fallback, item order, and whether some uploads produced no CID.

- Excel read failure
  The code already attempts style repair for `.xlsx`/`.xlsm`. If it still fails, ask the user to open and resave the workbook as `.xlsx`.

- Excel save failure
  Check whether Excel/WPS has the workbook open. The runner lock does not solve external file locks.

## High-Risk Gotchas

- UI state currently persists `account` and `password`; avoid expanding this pattern.
- Live upload writes directly to the original backfill Excel after each successful order.
- Existing CID rows are intentionally preserved; new rows start at the first empty CID row.
- Browser defaults currently use the first item for all selected items via one-click reuse.
- Planner/backfill month tag can differ from live browser tags because `_fill_card_defaults` does not pass `config.month_tag`.
