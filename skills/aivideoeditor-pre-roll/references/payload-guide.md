# Payload Guide

Map user-friendly requests to the remote pre-roll API body.

## Copy

Use `scriptText` when the user provides exact copy. This text becomes voiceover and the main subtitle.

Use `copyTemplateType` plus `copyVariables` only when the user wants template-driven copy generation. If both `scriptText` and `copyTemplateType` are present, prefer `scriptText` for predictable output.

Avoid putting disclaimer text into `scriptText`; disclaimer text should be visual-only.

Reject or ask the user to rewrite copy that contains `红包` or `花不完`; these words must not appear in subtitles or voiceover.

Use `voiceType` for one fixed voice. Use `voiceCandidates` when the caller wants voice variety; the backend can choose one candidate per task. The remote helper also accepts `--voice-type A|B|C` or `--voice-candidates A,B,C`.

## Visual Type

Use `visualTemplateId` for normal requests:

- `decompression`: ASMR/decompression background.
- `scenery`: scenery background.
- `ai_lifestyle`: adult lifestyle/music-use scene.
- `ai_beauty_image`: generated adult female lifestyle image base.
- `presenter_finance`: dashboard/reward-growth visual.
- `gold_reward`: coins/reward visual.
- `chinese_fortune`: red-gold fortune visual.
- `pet_funny`: pet/funny visual.

Use `visualPromptText` only when the user gives a custom image/video prompt.

All visual prompts should keep material safe: no watermark or AI watermark, suggestive imagery, real visible faces, tattoos, known IP, film/TV stills, license plates, military/political content, QR codes, or arrow icons.

## Brand Assets

Logo must come from a real caller-provided image or a real server-side logo asset. Do not use typed text as the logo. For automatic contrast, pass both:

```json
{
  "brandOverlay": {
    "logoLightPath": "D:\\path\\to\\汽水logo-白色竖版.png",
    "logoDarkPath": "D:\\path\\to\\汽水logo-黑色竖版.png",
    "logoLumaThreshold": 0.56
  }
}
```

Bright backgrounds should use the dark logo; dark backgrounds should use the light logo.

## Coin Materials

For `金币音乐旧` / old balance screenshots, use big amounts over 10 yuan by default. If the copy mentions `下载汽水音乐之前`, `三毛`, `五毛`, `3毛`, `5毛`, `0.3`, `0.5`, or similar small-before-download wording, small amount screenshots are allowed.

For `金币音乐新` screenshots, use small amounts under 10 yuan. Coin arrival visuals can mention coins, but a single large amount and accumulated displayed amount should stay under 50,000 coins.

## Asset Strategy

- `generated`: Use AI video generation.
- `scraped`: Use a provided source video URL list or a direct source URL.
- `hybrid`: Try scraped source video and allow generated fallback if implemented by the server, but still provide scraped URLs yourself.
- `generated_image`: Generate a still image and turn it into a video background.

For standalone/local runs, local visual files should be paired with `assetRoot` and `assetManifest` so the caller can run the Manifest understanding gate first. The remote backend payload does not read a local manifest on another computer, so keep this as a standalone workflow detail unless the backend explicitly exposes manifest upload support.

For `scraped`, include at least `scrapedVideoType` and one of:

- `scrapedVideoUrl`
- `scrapedVideoUrls`

Example:

```json
{
  "assetStrategy": "scraped",
  "scrapedVideoType": "decompression",
  "scrapedVideoUrls": {
    "decompression": ["https://example.com/source.mp4"],
    "decompressionFallback": ["https://example.com/fallback.mp4"]
  }
}
```

## Subtitle

Common `subtitleConfig.position` values:

- `lower_center`: recommended default.
- `bottom_center`: lower than `lower_center`.
- `middle_center`: centered.
- `top_center`: top.
- `bottom_right`: small note/disclaimer.

Safe default:

```json
{
  "position": "lower_center",
  "fontName": "FZLanTingHeiS-DB1-GB",
  "brandFontName": "Soda Font",
  "brandPrimaryColor": "&H0042FD3B",
  "brandOutlineColor": "&H00000000",
  "brandFontScale": 1.18,
  "fontSize": 46,
  "maxLines": 2,
  "safeMarginRatio": 0.12,
  "bottomMarginRatio": 0.22
}
```

`汽水音乐` and `汽水` should render with `brandFontName`, `brandPrimaryColor`, `brandOutlineColor`, and `brandFontScale`; other main subtitle text should render with `fontName` and the main subtitle colors. The disclaimer is visual-only and defaults to clear white `Microsoft YaHei` with a black outline, unless `disclaimerConfig.fontName` overrides it.

Standalone mode auto-discovers `SodaFont-Regular.otf`, 方正兰亭, Soda Music logos, and the subtitle icon from bundled `assets/汽水物料-新` first. If the rendered video still falls back to ordinary fonts, pass `fontsDir`, or pass both `bodyFontPath` and `brandFontPath`.

If the user says subtitles overflow, lower `fontSize`, use `maxLines: 2`, and increase `safeMarginRatio`.

For standalone audio/subtitle sync, prefer the default automatic mode:

```json
{
  "subtitleAudioSync": "auto"
}
```

If a specific generated voice still feels early or late, set `subtitleOffsetSeconds` manually. Positive values delay the main subtitle; negative values show it earlier. The small disclaimer stays visual-only and is not shifted.

## Disclaimer

Default ad disclaimer:

```json
{
  "includeDisclaimerSubtitle": true,
  "disclaimerText": "本视频为广告创意\n具体奖励金额以实际情况为准",
  "disclaimerConfig": {
    "position": "bottom_right",
    "fontSize": 22,
    "fontName": "Microsoft YaHei",
    "primaryColor": "&H00FFFFFF",
    "outlineColor": "&H00000000",
    "backColor": "&H00000000",
    "outline": 1.4,
    "shadow": 0
  }
}
```

Do not include the disclaimer in voiceover.
