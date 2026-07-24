# Excel And Song Matching Contract

## Song Library Loading

`load_song_records` reads all sheets and searches the first 50 rows for a header row. It accepts flexible aliases:

- Song name: `歌名`, `歌曲名`, `曲名`, `歌曲名称`, plus link-like columns when needed.
- Song ID: `标签ID`, `歌曲ID`, `ID`, `id`, `song_id`, `gq`, `gd`, or any header containing `id` as fallback.
- Link: `链接`, `歌名&链接`, `歌曲链接`, `song_link`, `url`.
- Artist: `歌手`, `歌手名`, `艺人`, `艺人名`, `演唱`, `演唱者`, `artist`, `singer`, `author`.
- Blocked: `禁投`, `是否禁投`, `备注`, `状态`, `是否制作`.

Song IDs are normalized by `normalize_song_id` to `gq_<digits>` for numeric, `gd_...`, or `gq_...` inputs. If the ID column is blank, the loader tries to extract a URL, follows redirects, and reads `track_id` or `trackId` from the final URL.

Rows missing song name or song ID after link resolution are skipped. Fully duplicate song names are removed from usable records. When `duplicate_output_path` is provided, duplicates relevant to the current batch can be exported to `duplicate_songs.xlsx`.

## Song Matching

`match_song_record` uses exact matching after text normalization and material-name extraction. A single exact match returns the record. Multiple exact matches return no record and a candidates list so a human can resolve ambiguity.

Planner behavior:

- VIP/SVIP items skip song matching and generate tags without a song ID.
- Missing or duplicate song IDs do not block upload. The item message explains that the song ID custom tag was not filled.
- A song record marked `禁投` marks the item `skipped`.

## Backfill Workbook Reading

Backfill aliases include:

- Order ID: `订单id`, `订单ID`, `订单 Id`, `order_id`, `orderId`, `订单号`.
- Material type: `素材类型`, `类型`, `功能卖点`, `分类标签`.
- Song name: `歌名`, `歌曲名`, `曲名`, `歌曲名称`.
- CID: `CID`, `cid`, `对象ID`, `对象id`, `creative_unit_id`.
- Backfill song ID: `标签ID`, `歌曲ID`, `歌曲 ID`, `song_id`, `gq`, `gd`.

`write_back_results(order_excel, output_path, items, include_ready=True)` loads the workbook, selects the sheet most likely to be the backfill template, and prepares headers.

## Backfill Writing

Current write behavior:

- If there is no existing song-name column and a CID column exists, insert `歌曲名称` immediately after `CID`.
- If the sheet is blank, create minimal headers: `素材类型`, `时间`, `CID`, `类型`.
- If any written non-VIP/SVIP item lacks `song_id`, ensure a `备注`/message column and append `未填写歌曲id自定义标签`.
- With `include_ready=True`, write `success` and `ready` items. With `include_ready=False`, write only `success`.
- Start from the first row whose CID cell is empty; never overwrite a row with an existing CID.
- Write CID, material type, type=`剪辑`, blank time, order ID, song name, song ID, file name, status, message, classification path, custom tags, and optional tags when matching columns exist.

Dry-run writes to `<task_root>/result.xlsx`. Live upload writes successful items directly back to the original backfill Excel, one successful order at a time.

## Style Repair And Locks

The loader retries with repaired workbook bytes when openpyxl cannot parse bad `.xlsx`/`.xlsm` styles. It rewrites minimal `styles.xml` in memory and strips worksheet style dependencies.

If save fails even after parsing, first check whether Excel/WPS has the workbook open or locked. The in-process lock only serializes runner threads; it cannot unlock files held by other processes.
