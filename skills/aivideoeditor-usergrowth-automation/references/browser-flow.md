# Browser Automation Flow

## Dependencies And Launch

`UserGrowthBrowserClient.run` lazily imports Playwright. Missing Playwright raises `需要先安装 playwright，并执行 playwright install chromium`. The client launches Chromium with local browser channels in this order: `msedge`, then `chrome`. Viewport is `1440x1000`; slow motion is controlled by `browser_slow_mo_ms` and `USERGROWTH_OPERATION_SPEED_FACTOR`.

Login uses `https://usergrowth.com.cn/open/login`, then navigates/checks `https://usergrowth.com.cn/home`. Captcha recognition uses `UserGrowthCaptchaSolver` and `ddddocr`. Login retries up to 5 times and considers `/home`, `墨攻AI`, or `采购中心` as logged-in signals. After login, image/font/favicon requests are blocked.

## Per-Order Flow

`_process_order` handles one `UserGrowthOrderPlan`:

1. Filter out skipped items.
2. Enter `墨攻AI` and then `工单管理`.
3. Search by `订单名称或ID`.
4. Open `新建创意单元` for the searched order, with scoped, exact-text, nearby, and coordinate click fallbacks.
5. Read upload limit from text such as `最多上传 N`, `最多 N 个`, or `上限 N`; skip plan if active items exceed the limit.
6. Upload files and enter 录入变色龙 with retry.
7. Read current task ID from a task input.
8. Wait for `全部成功`, fail on `已失败`.
9. Submit review.
10. Open material list/detail, read CIDs, read material type by CID, and mark items success.

## Upload

`_upload_files` waits for `input[type='file']`, clicking `点击或拖拽文件至此区域` or `上传` while waiting. It sets all item paths at once with `set_input_files`, clicks `点我开始上传` if present, and checks page text for limit-zero and upload failure messages.

Upload retry has two layers:

- `_upload_files` retries up to 6 attempts and can reload/reopen the creative-unit page.
- `_upload_and_enter_chameleon_with_retry` retries the upload plus enter-chameleon sequence up to `max_status_retries` when the failure looks transient.

## Chameleon Entry And Tags

After upload cards are ready, the browser clicks `继续编辑`, `确认提交`, selects all creative units, clicks `录入素材`, waits for a page containing `投放平台`/`汽水音乐`, confirms the delivery modal, then calls `_fill_card_defaults(page, items[0])`.

Important current assumptions:

- Only `items[0]` drives the card defaults; `一键复用` applies that same setup to the whole selected batch.
- `_fill_card_defaults` recomputes `classification_path_for_material(item.file_name)` and `custom_tags_for_material(item.material_type, item.song_id, item.file_name)` instead of using `item.classification_path` and `item.custom_tags`.
- Because no `month_tag` is passed in `_fill_card_defaults`, live browser tags use the current default month, while planner/preview/backfill can use `config.month_tag`. Fix this before relying on a custom month tag.

Default form choices:

- `请选择UGC内容` -> `不包含`.
- Cascader `汽水音乐-素材类型` -> `汽水音乐-素材类型 / LUNA_剪辑制作 / LUNA_自产`.
- Cascader `LUNA素材来源` -> `LUNA素材来源 / LUNA_千沧代理`.
- Cascader `LUNA功能卖点` -> `LUNA功能卖点 / <classification_path_for_material(file)>`.
- Custom tags from `custom_tags_for_material`.
- Radio `未成年人内容` -> `已授权`.
- Radio `影视内容` -> `已授权`.
- `一键复用` -> `全选` -> `一键复用` -> `提交` -> `查看任务详情`.

## Review And CID Backfill

`_submit_review` clicks `送审`, confirms `确定`, then optionally clicks `查看任务详情`.

`_fill_cids_for_task` searches the task by ID, waits for row success, opens `素材/文案列表查看` or related text, reads CIDs from the global search input, and requires at least as many CIDs as items. It zips item order with CID order.

Fallback CID reading clicks `查看详情`, tries `一键复制对象id`, then extracts CIDs from body text. `_read_material_type_by_cid` opens `查看素材` for the CID row and extracts `分类标签` for backfill material type.

## Debug And Cancellation

`_snapshot_error` writes `debug/<name>.txt`, `debug/<name>.png`, and details to `debug/run.log`. Normal snapshots currently return early unless called with `screenshot=True`.

Cancellation is a threading event watched by `_watch_cancel`; when set, the browser is closed so Playwright waits are interrupted and item/plan statuses become `cancelled`.
