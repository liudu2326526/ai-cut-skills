# Pre-roll Asset Manifest

## Purpose

`scripts/pre_roll_asset_manifest.py sync` scans the caller's asset folder into a workspace-local `pre_roll_assets_manifest.json`.

The Manifest is a runtime cache for project/workspace materials used by this render. Do not depend on a fixed material folder name. First search the caller's opened workspace/project for likely material roots, then sync the folder that actually contains usable Soda Music logos, fonts, reward screenshots, and overlay/insert media.

## What Sync Does

The sync command only records deterministic metadata:

- relative path under `asset_root`
- extension, kind, file size, modified time
- optional SHA-256 when `--checksum` is used
- media metadata from FFprobe when available
- a rough category inferred from the path

The rough category is only a starting hint. It is not visual understanding.

## Manifest Shape

```json
{
  "schema_version": 1,
  "workspace": "D:\\my-pre-roll-work",
  "asset_root": "D:\\my-pre-roll-work\\assets",
  "fingerprint_mode": "path-size-mtime",
  "metadata_mode": "ffprobe",
  "summary": {
    "total": 12,
    "by_kind": {
      "image": 4,
      "video": 5,
      "font": 3
    }
  },
  "assets": [
    {
      "relative_path": "logo/logo-dark.png",
      "kind": "image",
      "category": "brand_logo",
      "description": "左上角使用的汽水音乐官方深色底 logo，包含品牌图形和文字。",
      "effective_region": {
        "x": 0,
        "y": 0,
        "width": 420,
        "height": 128,
        "coordinate_space": "source_pixels"
      }
    }
  ]
}
```

## Required Understanding Fields

Every visual asset (`kind=image` or `kind=video`) must have:

- `description`: concrete Chinese description based on actually viewing the image/video.
- `effective_region`: the smallest useful source-pixel rectangle containing real visual content.

`effective_region` must use:

```json
{
  "x": 0,
  "y": 0,
  "width": 1080,
  "height": 1920,
  "coordinate_space": "source_pixels"
}
```

Transparent padding, blank canvas, and pure empty borders do not count as effective content.

## Commands

Sync:

```powershell
python scripts\pre_roll_asset_manifest.py sync --workspace "D:\work" --asset-root "D:\work\path\to\business-materials"
```

Validate:

```powershell
python scripts\pre_roll_asset_manifest.py validate `
  --asset-root "D:\work\assets" `
  --asset-manifest "D:\work\pre_roll_assets_manifest.json" `
  --required-path "D:\work\assets\logo\logo-dark.png"
```

Export representative video frames:

```powershell
python scripts\pre_roll_asset_manifest.py extract-frames `
  --asset-root "D:\work\assets" `
  --asset-manifest "D:\work\pre_roll_assets_manifest.json" `
  --output-dir "D:\work\asset_frames" `
  --only-missing
```

## Render Gate

Standalone render preflight fails when:

- the Manifest file is missing
- Manifest `asset_root` differs from the current `--asset-root`
- any image/video lacks `description`
- any image/video lacks valid `effective_region`
- a local visual path used by the render is not tracked
- a selected ordinary material lacks `semantic_role=benefit_point` or `matched_benefit_text`

Do not work around this by relying on filenames or folder names.
