# Standalone CLI

Use `scripts/usergrowth_upload.py` when the user wants the skill itself to perform UserGrowth planning or upload. The script vendors the UserGrowth automation package inside this skill, so it does not import from the project repo at runtime.

## Install Runtime Dependencies

Use the Python environment that will run the automation:

```powershell
python -m pip install -r C:\Users\Donson\.codex\skills\aivideoeditor-usergrowth-automation\scripts\requirements.txt
python -m playwright install chromium
```

The live browser flow prefers local Edge/Chrome channels, but installing Chromium is still a useful fallback for Playwright environments.

## Dry-Run With Explicit Videos

```powershell
$script = 'C:\Users\Donson\.codex\skills\aivideoeditor-usergrowth-automation\scripts\usergrowth_upload.py'
$argList = @(
    $script,
    '--video-folder', 'D:\path\videos',
    '--video', 'dxzc-001-汽水音乐-LUNA_金币音乐新-歌曲A.mp4',
    '--video', 'subfolder\dxzc-002-汽水音乐-LUNA_金币音乐旧-歌曲B.mp4',
    '--backfill-excel', 'D:\path\backfill.xlsx',
    '--song-excel', 'D:\path\songs.xlsx',
    '--output-root', 'D:\path\outputs',
    '--order-id', '123456',
    '--task-name', 'usergrowth_selected',
    '--month-tag', '26年7月dxqs'
)
& python @argList
```

Dry-run writes `<output-root>/<timestamp>_<task-name>/result.xlsx`, `task.json`, and `run.log`. It does not open the browser.

On failure after a task folder is created, read `<output-root>/<timestamp>_<task-name>/error.json` and `error.log`. On early CLI failures such as unmatched video selectors, check stderr and `<output-root>/_cli_errors/` when `output_root` was available.

## Selectors

Video selection supports:

- `--video <absolute path>`
- `--video <relative path under video-folder>`
- `--video <exact file name>`
- `--video <file stem without suffix>`
- `--video-glob '*金币音乐新*.mp4'`
- `--video-list selected.txt`, one selector per line
- `--all-videos`, explicit opt-in to scan everything

If a selector does not match, the script fails instead of silently uploading the wrong set.

## Manifest

For repeated tasks, create a JSON manifest:

```json
{
  "video_folder": "D:/path/videos",
  "videos": [
    "dxzc-001-汽水音乐-LUNA_金币音乐新-歌曲A.mp4",
    "subfolder/dxzc-002-汽水音乐-LUNA_金币音乐旧-歌曲B.mp4"
  ],
  "backfill_excel": "D:/path/backfill.xlsx",
  "song_excel": "D:/path/songs.xlsx",
  "output_root": "D:/path/outputs",
  "order_id": "123456",
  "task_name": "usergrowth_selected",
  "month_tag": "26年7月dxqs",
  "recursive": true,
  "dry_run": true
}
```

Run it:

```powershell
& python 'C:\Users\Donson\.codex\skills\aivideoeditor-usergrowth-automation\scripts\usergrowth_upload.py' --manifest 'D:\path\manifest.json'
```

Do not put passwords in manifests unless the user explicitly asks for that storage pattern. Prefer environment variables.

## Live Upload

Live upload writes successful orders directly back to the original backfill Excel and submits review on UserGrowth. Only run live after explicit user confirmation:

```powershell
$env:USERGROWTH_ACCOUNT = '<account>'
$env:USERGROWTH_PASSWORD = '<password>'
& python 'C:\Users\Donson\.codex\skills\aivideoeditor-usergrowth-automation\scripts\usergrowth_upload.py' `
  --manifest 'D:\path\manifest.json' `
  --live `
  --confirm-live
```

Use `--headless` only after visible browser mode has been validated.
