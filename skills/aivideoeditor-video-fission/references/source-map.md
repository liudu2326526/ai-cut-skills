# Source Map

This skill consolidates the local material-remix capabilities extracted from `material_remix_desktop_source/`.

Original source files:

- `material_remix_desktop_source/app/variant_engine.py`
  - frame variation: `build_multi_variants`, `choose_deleted_frames_per_second`, `choose_auto_cover`
  - folder combo: `build_folder_combinations`, `collect_folder_permutation_chains`
  - paired media: `scan_pairable_media_folder`, `build_paired_media_outputs`
- `material_remix_desktop_source/app/ffmpeg_utils.py`
  - frame-drop render with cover intro
  - concat rendering
  - paired media stream-copy/reencode fallback
- `material_remix_desktop_source/app/media_analysis.py`
  - source video probing
  - cover quality/hash checks
- `material_remix_desktop_source/app/exporters.py`
  - manifest columns and CSV/XLSX export
- `app/api/v1/endpoints/material_remix_tool.py`
  - backend release/latest/download endpoint
- `app/services/material_remix_tool_service.py`
  - configured desktop package metadata

The bundled scripts under this skill are the runtime source of truth for standalone execution.
