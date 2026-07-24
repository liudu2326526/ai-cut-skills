---
name: aivideoeditor-usergrowth-automation
description: "Standalone UserGrowth automation skill for AIVideoEditor desktop upload workflows. Use when Codex needs to select specific videos and run UserGrowth 自动上传 by skill scripts only, including dry-run planning, song-library matching, 回填 Excel, CID 后歌曲名称列, Playwright upload/录入变色龙/送审/CID 回填, 素材分类标签/自定义标签, ddddocr 验证码, task.json/run.log/debug snapshots, or debugging the copied automation implementation."
---

# AIVideoEditor UserGrowth Automation

## Overview

Use this skill to run the UserGrowth automation as a standalone skill. The runnable implementation lives in `scripts/`: it vendors the UserGrowth automation package and provides a CLI that can select exact videos, do dry-run planning, or perform live browser upload after explicit confirmation.

The original repo can still be inspected for comparison, but execution should use this skill's scripts first.

This skill intentionally excludes PyInstaller/exe packaging and release tasks unless the user explicitly asks for packaging again.

## Before Acting

1. For any run or "指定视频上传" request, read `references/standalone-cli.md` and use `scripts/usergrowth_upload.py`.
2. Prefer dry-run first. Live upload requires an explicit user request and both CLI flags `--live --confirm-live` in the current command. Manifest fields cannot enable live mode or supply the confirmation.
3. Do not store or echo credentials. Prefer `USERGROWTH_ACCOUNT` and `USERGROWTH_PASSWORD`.
4. If modifying the standalone implementation, edit files under `scripts/usergrowth_automation/` and then run the validation guidance.

## Task Routing

- Running the standalone tool, selecting exact videos, manifests, dependency setup: read `references/standalone-cli.md`.
- Workflow, task outputs, batch behavior, dry-run/live split: read `references/workflow.md`.
- Excel backfill, CID, song-name column, song library, duplicate/blocked songs: read `references/excel-contract.md`.
- Browser upload, login, order search, 录入变色龙, review, CID scraping: read `references/browser-flow.md`.
- Errors, flaky selectors, missing dependencies, locked Excel, debug screenshots/logs: read `references/failure-playbook.md`.
- Test selection and verification expectations: read `references/validation.md`.

## Script Entry

Primary CLI:

```powershell
python C:\Users\Donson\.codex\skills\aivideoeditor-usergrowth-automation\scripts\usergrowth_upload.py --help
```

The CLI supports `--video`, `--video-glob`, `--video-list`, `--all-videos`, and JSON manifests. It fails when a requested selector does not match any video.

## Safety Rules

- Do not run a real UserGrowth upload, submit review, or write production Excel unless the user explicitly asks for a live run and provides the target inputs.
- Do not echo, persist, or add hard-coded credentials.
- Live mode writes successful orders directly to the original backfill Excel and submits review on UserGrowth.
- Group items by order ID plus their planned classification/custom-tag profile before upload. `一键复用` may only apply within one homogeneous group.
- Browser entry must use the classification path and custom tags already stored on each planned item; do not recompute them from the filename during live upload.
- Keep standalone execution changes scoped to this skill unless the user asks to sync changes back into the project.
