---
name: aivideoeditor-video-fission
description: "Complete standalone AIVideoEditor video fission/material remix production skill. Use when Codex needs to generate or debug 视频裂变, 素材裂变, 多视频抽帧裂变, 单视频抽帧裂变, 前贴排列组合, 文件夹组合, 音视频配对输出, local ffmpeg material variant generation, manifest/task.json/task.log exports, desktop material remix tool release metadata, or any combination of these workflows without depending on the backend repo."
---

# AIVideoEditor Video Fission

## Purpose

Use this single skill as the full local “视频裂变 / 素材裂变” toolbox. It is self-contained and can run without importing the AIVideoEditor backend repo.

The skill covers four related capabilities:

1. **抽帧裂变**: generate multiple variants from one or more source videos by deleting random discrete frames per second and adding distinct cover intro frames.
2. **前贴排列组合**: generate ordered folder-combo videos, taking one clip from each folder with per-folder usage limits.
3. **音视频配对输出**: scan one folder, classify pure video/pure audio by ffprobe, pair by normalized filename ID, and render MP4 outputs.
4. **发布包辅助**: create/verify desktop tool zip release metadata, SHA256, file size, and backend `.env` lines.

For UserGrowth browser upload, use `$aivideoeditor-usergrowth-automation` after local fission outputs are generated and verified. This skill does not run live uploads.

## Runtime Requirements

- Python 3.10+
- `ffmpeg` and `ffprobe` on `PATH`, or pass `--ffmpeg` / `--ffprobe`
- Optional: `Pillow` for better cover sharpness/brightness/hash evaluation in frame variation
- Optional: `openpyxl` for `.xlsx` manifest exports

Every production script writes a timestamped task folder containing `videos/`, `manifest.csv`, optional `manifest.xlsx`, `task.json`, `task.log`, and incremental `run.log`. If a task fails or is interrupted after the task folder is created, it also writes `error.json`.

## Workflow Selection

Use the narrowest script that matches the job:

- If the user has original clips and wants many variants: run `scripts/frame_variation.py`.
- If the user has several ordered material folders and wants combination chains: run `scripts/folder_combo.py`.
- If the user has separate pure-video and pure-audio files that need muxing: run `scripts/paired_media.py`.
- If the user has a desktop tool package/folder and needs release metadata: run `scripts/release_package.py`.
- If the user asks for a full batch pipeline, run the scripts in the needed order and keep each stage's task folder as an audit artifact.

## Quick Commands

### 抽帧裂变

```powershell
python C:\Users\Donson\.codex\skills\aivideoeditor-video-fission\scripts\frame_variation.py `
  --source D:\videos\a.mp4 D:\videos\b.mp4 `
  --output-root D:\outputs `
  --target-count 5 `
  --frames-per-second-drop 1 `
  --width 720 --height 1280 --resize-mode crop
```

### 前贴排列组合

```powershell
python C:\Users\Donson\.codex\skills\aivideoeditor-video-fission\scripts\folder_combo.py `
  --folders D:\front\a D:\front\b D:\front\c `
  --folder-usage-limits 2,2,5 `
  --output-root D:\outputs `
  --task-name combo_batch
```

### 音视频配对输出

```powershell
python C:\Users\Donson\.codex\skills\aivideoeditor-video-fission\scripts\paired_media.py `
  --input-folder D:\media_pairs `
  --output-root D:\outputs `
  --task-name pair_batch
```

### 发布包元数据

```powershell
python C:\Users\Donson\.codex\skills\aivideoeditor-video-fission\scripts\release_package.py `
  --zip-path D:\release\material-remix-tool_v1.0.2_win64.zip `
  --version 1.0.2 `
  --download-url https://static.example.com/tools/material-remix/material-remix-tool_v1.0.2_win64.zip
```

## Behavior Contracts

### 抽帧裂变

- Generate `target-count` variants per source video.
- Delete random discrete frames per second, not a continuous time span.
- Avoid duplicate frame signatures per source when possible.
- Pick cover candidates from separated timestamps and prepend a short still intro segment.
- Prefer distinct covers using average-hash distance when `Pillow` is available.

### 前贴排列组合

- Keep folder order exactly as provided.
- Build each result from one video per folder.
- Enforce per-folder per-video usage limits such as `2,2,2,5,5`.
- Avoid duplicate chains and prefer balanced/randomized selection.
- Render normalized portrait MP4 outputs and synthesize silent audio for clips without audio.

### 音视频配对

- Classify files by actual streams, not extension.
- Pair `video_only` with `audio_only` using filename stem after removing a trailing `(number)` suffix.
- Report unmatched, invalid, and `av_both` conflict files in `task.json`.
- Prefer stream copy; fall back to H.264/AAC re-encode with `-shortest`.

### 发布包

- Compute SHA256 in uppercase.
- Emit both JSON metadata and `MATERIAL_REMIX_TOOL_*` `.env` lines.
- Do not upload packages or change production release URLs unless explicitly asked.

## Failure And Log Reading

For `frame_variation.py`, `folder_combo.py`, and `paired_media.py`, locate the latest timestamped folder under the `--output-root` used by the command.

Read files in this order:

1. `run.log`: incremental timeline. It records task start, config, planned counts, per-item start/done events, and the final failure/success line.
2. `error.json`: exists only after an overall failure or interruption. Read `error_type`, `error_message`, `interrupted`, `completed_count`, `generated_outputs`, and `traceback`.
3. `task.json`: exists after normal completion, or paired-media completion with per-pair failures. Read `status`, `variants`, and mode-specific sections.
4. `task.log`: human-readable summary of completed variants.
5. `manifest.csv` / `manifest.xlsx`: generated output ledger for completed variants.
6. `videos/`: partial outputs may remain here if a later item failed or the process was interrupted.

Mode-specific notes:

- 抽帧裂变: if failure happens while rendering a variant, previously completed variants are listed in `error.json.generated_outputs`; the currently rendering output may be incomplete.
- 前贴排列组合: `run.log` records each combination chain before rendering, so the last `variant_start` line identifies the failing chain.
- 音视频配对: individual pair failures do not abort the whole task. They are recorded in `task.json.failures`, with failed rows also appearing in `manifest.csv`. Overall scan/render setup failures create `error.json`.
- 发布包辅助: there is no task folder. Logs are written next to the zip path as `<zip-name>.run.log`, `<zip-name>.error.json`, and `<zip-name>.metadata.json`.

If no task folder or zip-side log exists, the failure happened before argument parsing or before the script could create its output path. In that case, inspect the command-line stderr/stdout, verify paths, and rerun with an existing writable output directory and explicit `--ffmpeg` / `--ffprobe` if needed.

## Validation

For script-only checks:

```powershell
python -m py_compile `
  C:\Users\Donson\.codex\skills\aivideoeditor-video-fission\scripts\frame_variation.py `
  C:\Users\Donson\.codex\skills\aivideoeditor-video-fission\scripts\folder_combo.py `
  C:\Users\Donson\.codex\skills\aivideoeditor-video-fission\scripts\paired_media.py `
  C:\Users\Donson\.codex\skills\aivideoeditor-video-fission\scripts\release_package.py
```

For real batches, start with a one-output smoke job, inspect `task.log`, `manifest.csv`, and probe one generated MP4 with `ffprobe`.

## Source Context

Read `references/source-map.md` only when you need to compare this standalone skill to the original desktop source files in the AIVideoEditor backend repo.
