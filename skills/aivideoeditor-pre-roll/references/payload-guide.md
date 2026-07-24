# Payload Guide

Map user-friendly requests to the local pre-roll runner config.

## Copy

Use `scriptText` when the user provides exact copy. This text becomes voiceover and the main subtitle.

Main voiceover text and main subtitle text must stay identical after basic cleanup such as removing emphasis markers. Do not replace subtitle text with provider-normalized TTS frontend text; frontend/timestamp data is only for timing. The disclaimer is visual-only and must not be included in the voiceover.

Use `copyTemplateType` plus `copyVariables` only when the user wants template-driven copy generation. If both `scriptText` and `copyTemplateType` are present, prefer `scriptText` for predictable output.

Avoid putting disclaimer text into `scriptText`; disclaimer text should be visual-only.

Reject or ask the user to rewrite copy that contains `红包` or `花不完`; these words must not appear in subtitles or voiceover.

Use `voiceType` for one fixed voice. Use `voiceCandidates` when the caller wants voice variety; the runner can choose one candidate per task. Prefer a small candidate pool for batches unless the user explicitly requests a fixed voice.

In standalone local TTS mode, use `voiceName` for one Windows SAPI voice or `VoiceA|VoiceB` for a local voice pool. If local TTS is enabled and no `voiceName` is supplied, the runner will sample from installed Chinese SAPI voices when possible.

For a faster-sounding ad read, compact long silent pauses in the generated voiceover instead of increasing speech speed. This pause-compaction pass is required for deliverables; if it fails, stop instead of using the raw paused voiceover. After pause compaction, use the compacted audio duration for main subtitle timing.

## Visual Type

Use `visualTemplateId` for normal requests:

- `decompression`: ASMR/decompression background.
- `animal_grooming`: animal grooming / fur trimming / hoof trimming decompression background. Prefer scraped original clips for this type.
- `scenery`: scenery background.
- `ai_beauty_image`: generated static adult female welfare poster/image base. This type must use `assetStrategy=generated_image`; the image may show an AI-generated front-facing adult woman, but must not use a real identifiable person, headphones, listening-to-music action, suggestive styling, watermark, QR code, or brand UI.
- `presenter_finance`: dashboard/reward-growth visual.
- `gold_reward`: coins/reward visual.
- `chinese_fortune`: red-gold fortune visual.
- `mythic_fortune`: gold peacock / phoenix / dragon red-gold fortune visual.
- `pet_funny`: clean pet/funny visual. Do not use pet-touching-music-card scenes or pet-watching-coin-growth overlays.

Use `visualPromptText` only when the user gives a custom image/video prompt.

All visual prompts should keep material safe: no watermark or AI watermark, suggestive imagery, real visible faces, tattoos, known IP, film/TV stills, license plates, military/political content, QR codes, or arrow icons.

## Brand Assets

Logo must come from a real project/workspace image asset or a real server-side logo asset. Do not use typed text as the logo. Do not assume the material folder name is fixed; search the opened project/workspace by content and prefer folders that include Soda Music logo variants, app icons, SodaFont/方正兰亭 fonts, and reward/coin materials. For automatic contrast, pass both:

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

The persistent top-left logo has fixed placement and size:

```json
{
  "position": "top_left",
  "width": 190,
  "x": 40,
  "y": 40,
  "opacity": 1.0
}
```

Do not set `brandOverlay.position`, `brandOverlay.widthRatio`, `brandOverlay.marginRatio`, or `brandOverlay.opacity` to vary the persistent logo. Do not set `brandOverlay.enabled=false` to remove it. Those fields are legacy compatibility inputs and should not affect deliverable pre-roll videos.

Every deliverable must contain the top-left Soda Music logo. If a custom config tries to omit or disable it, override that before rendering; the runner will force it back on.

## Coin Materials

For `金币音乐旧` / old balance screenshots, use big amounts over 10 yuan by default. If the copy mentions `下载汽水音乐之前`, `三毛`, `五毛`, `3毛`, `5毛`, `0.3`, `0.5`, or similar small-before-download wording, small amount screenshots are allowed.

For `金币音乐新` screenshots, use small amounts under 10 yuan. Coin arrival visuals can mention coins, but a single large amount and accumulated displayed amount should stay under 50,000 coins.

## Asset Strategy

- `generated`: Use AI video generation.
- `scraped`: Use a provided source video URL list or a direct source URL.
- `hybrid`: Try scraped source video and allow generated fallback if implemented by the server, but still provide scraped URLs yourself.
- `generated_image`: Generate a still image and turn it into a video background. In standalone mode this needs `imageApiKey`/`--image-api-key`, or a caller-provided `backgroundImage`.

When `visualTemplateId=ai_beauty_image`, force `assetStrategy=generated_image`. The output background should be based on a static AI-generated image, not Seedance/AI video generation.

For `ai_beauty_image`, a minimal standalone config looks like:

```json
{
  "scriptText": "每天听歌15分钟，你的余额就会一直涨",
  "visualTemplateId": "ai_beauty_image",
  "assetStrategy": "generated_image",
  "imageModel": "doubao-seedream-5-0-260128",
  "imageSize": "864x1536"
}
```

For revisions, choose the cleanest visual source from the previous result and submit that again. Prefer `revisionSourcePath`, `baseVideoPath`, `generatedVideoPath`, `scrapedVideoPath`, `imageVideoPath`, `backgroundVideo`, `backgroundImage`, or the original source URL. Do not pass `finalVideoPath`/`final.mp4` back as `backgroundVideo`, because the final file already has baked-in subtitles, logos, disclaimer text, motion effects, audio mix, and overlays.

For standalone/local runs, local visual files should be paired with `assetRoot` and `assetManifest` so the caller can run the Manifest understanding gate first. `assetRoot` should point to the discovered project/workspace material folder; it does not need to have a specific folder name.

For `scraped`, include at least `scrapedVideoType` and one of:

- `scrapedVideoUrl`
- `scrapedVideoUrls`

Supported scraped video types include `decompression`, `animal_grooming`, `scenery`, and `pet_funny`. Use `animal_grooming` for decompression-style clips such as pet grooming, animal fur trimming, hoof trimming, or shearing. Useful search terms are `宠物修毛`, `动物剃毛`, `修毛`, `马蹄修剪`, `蹄甲修剪`, and `羊毛修剪`. Use `pet_funny` for clean pet/funny clips without UI overlays.

Example:

```json
{
  "assetStrategy": "scraped",
  "scrapedVideoType": "animal_grooming",
  "scrapedVideoUrls": {
    "animal_grooming": ["https://example.com/source.mp4"],
    "decompression": ["https://example.com/decompression-fallback.mp4"],
    "decompressionFallback": ["https://example.com/fallback.mp4"]
  }
}
```

## Keyword Material Overlay

When using `keywordMaterialOverlay`, ordinary materials should be composited below main subtitles and the visual-only disclaimer. That layer order is the default fix for caption blocking.

Only enable spatial avoidance when the material should also stay physically away from the caption area:

```json
{
  "keywordMaterialOverlay": {
    "enabled": true,
    "avoidSubtitleArea": false,
    "subtitleSafePosition": "middle_center",
    "subtitleGuardGapRatio": 0.035
  }
}
```

If subtitles are still hard to read because the background/material is visually busy, keep the same layer order and either add stronger subtitle outline/shadow, lower `widthRatio`/`heightRatio`, or set `avoidSubtitleArea:true`. Do not solve it by moving main subtitles to the edge.

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

For standalone mode, first search the current project/workspace for `SodaFont-Regular.otf`, 方正兰亭, Soda Music logos, and the subtitle icon, then pass the discovered paths explicitly. If the material root has an unusual name, that is fine; identify it by its contents. If the rendered video still falls back to ordinary fonts, pass `fontsDir`, or pass both `bodyFontPath` and `brandFontPath`.

If the user says subtitles overflow, lower `fontSize`, use `maxLines: 2`, and increase `safeMarginRatio`.

For standalone audio/subtitle sync, prefer the default automatic mode:

```json
{
  "subtitleAudioSync": "auto"
}
```

If a specific generated voice still feels early or late, set `subtitleOffsetSeconds` manually. Positive values delay the main subtitle; negative values show it earlier. The small disclaimer stays visual-only and is not shifted.

## Disclaimer

The bottom-right ad disclaimer is mandatory and visual-only. Keep `includeDisclaimerSubtitle: true`; if a caller sends `false` or an empty `disclaimerText`, force it back to the default before rendering.

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
