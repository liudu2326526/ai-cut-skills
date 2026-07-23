# Pre-roll Asset Requirements

## Allowed Local Asset Types

Use local files the caller provides:

- logo images
- background videos
- background images
- overlay images / cutout images
- insert clips
- BGM
- voiceover audio
- fonts

## Visual Safety

Do not use:

- placeholder footage such as color blocks, procedural test animations, blank clips, or fake UI filler
- watermark or AI watermark
- suggestive or borderline imagery
- clear real faces
- tattoos
- known IP
- film / TV stills
- license plates
- military or political content
- arrows as icons

## Brand Assets

The logo must be a real image asset.

If the background is bright, use the dark logo.
If the background is dark, use the light logo.

Use `--logo-path` for one logo. Use `--logo-light-path` plus `--logo-dark-path` when both variants are available.

## Fonts

- `汽水音乐` and `汽水` use SodaFont.
- Other main subtitle text uses 方正兰亭.
- Disclaimer text uses clear white Microsoft YaHei by default.

## Material Strategy

This skill embeds the fixed business package `assets/汽水物料-新`. The bundled package is used by standalone mode for default Soda Music logos, the subtitle-triggered icon, and bundled fonts.

Extra caller-provided materials are still external. They must use:

If the caller wants extra local materials to participate in insertion or overlay matching, they must provide:

- `--asset-root`
- `--asset-manifest`
- optional `--material-selection-json`

The workflow should then use Manifest descriptions instead of filenames.

## Preflight Expectations

Before render:

- every local visual asset must be in the Manifest
- every visual asset must have `description`
- every visual asset must have valid `effective_region`
- every selected ordinary material must carry `semantic_role=benefit_point` and `matched_benefit_text`

If any of these are missing, stop and fix the Manifest first.
