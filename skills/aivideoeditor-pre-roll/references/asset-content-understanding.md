# Asset Content Understanding

## Principle

Do not call another model, API endpoint, or vector index to understand local pre-roll assets.

The model executing this skill is responsible for reading the files it can access:

- open each image that lacks understanding
- export and inspect representative frames for each video
- write the result back to `pre_roll_assets_manifest.json`

`sync-assets` only scans files. It does not decide what a picture or video means.

## Review Steps

1. Run `sync-assets`.
2. Read the Manifest and find assets in `changes.added`, `changes.modified`, or any image/video missing `description` or `effective_region`.
3. Open each image directly with an image viewing tool.
4. For each video, run `extract-frames`, then inspect the exported frames. Do not judge a video by filename or by its first frame only.
5. For transparent PNGs, view them on both light and dark backgrounds when needed.
6. Write a concrete Chinese `description`.
7. Write `effective_region` using source-pixel coordinates.
8. Save the Manifest and run `validate` again.

## Description Rules

Good descriptions mention:

- what the main visual subject is
- what action or UI state is visible
- any important visible text
- what narration meaning this asset can genuinely support

Good example:

```json
{
  "relative_path": "materials/coin-small-amount.png",
  "description": "一张通用金币到账截图，画面中心是小额金币增长提示和领取按钮，适合表达听歌后金币增加的小额福利。",
  "effective_region": {
    "x": 42,
    "y": 80,
    "width": 996,
    "height": 1560,
    "coordinate_space": "source_pixels"
  }
}
```

Bad descriptions:

- `一个素材`
- `福利图片`
- `和文件名一样`
- `可能是汽水音乐页面`

If you cannot verify the content, leave the field empty and report that manual review is needed.

## Effective Region Rules

`effective_region` is the rectangle containing useful visual information, not necessarily the whole canvas.

Include:

- visible UI/content
- logo graphics
- important text
- person/object/content areas
- screen content

Exclude:

- transparent padding
- blank margins
- pure background with no expressive content
- empty black borders from source video

Example: if a 1080x1920 PNG only has a centered 200x200 logo, use the 200x200 logo region, not the full 1080x1920 canvas.

## Semantic Matching

When choosing ordinary materials for insertion or overlay:

1. Split narration into benefit-point and non-benefit-point sentences.
2. Only benefit-point narration may trigger ordinary material matching.
3. Read Manifest `description` values and choose the asset that truly supports the sentence.
4. Do not match by filename, folder name, rough category, keywords, or hidden material pool.
5. In `materialSelectionJson`, record:

```json
{
  "path": "D:\\work\\assets\\materials\\coin-small-amount.png",
  "kind": "image",
  "semantic_role": "benefit_point",
  "matched_benefit_text": "每天听歌15分钟，你的余额就会一直涨"
}
```

If no suitable material exists, do not force a match.
