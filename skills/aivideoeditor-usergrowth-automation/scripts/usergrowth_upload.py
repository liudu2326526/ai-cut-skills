from __future__ import annotations

import argparse
import asyncio
from collections import defaultdict
from datetime import datetime
import fnmatch
import json
import os
from pathlib import Path
import sys
from typing import Any, Iterable

from usergrowth_automation.usergrowth_browser import UserGrowthBrowserClient
from usergrowth_automation.usergrowth_excel import load_song_records, write_back_results
from usergrowth_automation.usergrowth_models import (
    VIDEO_SUFFIXES,
    UserGrowthOrderPlan,
    UserGrowthRunConfig,
    UserGrowthVideoItem,
)
from usergrowth_automation.usergrowth_planner import _attach_order, _attach_song, scan_video_files
from usergrowth_automation.usergrowth_rules import (
    classification_path_for_material,
    detect_material_type,
    extract_song_name,
    optional_tags_for_file,
)
from usergrowth_automation.usergrowth_runner import _backfill_lock, _build_payload, _emit, _safe_name, _write_log


ProgressCallback = Any


def main(argv: list[str] | None = None) -> int:
    _configure_stdio()
    args = parse_args(argv)
    try:
        manifest_path = Path(args.manifest).resolve() if args.manifest else None
        manifest = _read_manifest(manifest_path)
        base_dir = manifest_path.parent if manifest_path else Path.cwd()
        config = _config_from_args(args, manifest, base_dir)
        selectors = _video_selectors_from_args(args, manifest)
        video_paths = resolve_video_selection(
            config.video_folder,
            selectors=selectors,
            glob_patterns=_list_value(args.video_glob) + _list_from_manifest(manifest, "video_globs"),
            recursive=config.recursive,
            all_videos=bool(args.all_videos or manifest.get("all_videos")),
        )
        if not video_paths:
            raise RuntimeError("没有选中任何视频。请使用 --video/--video-glob/--video-list，或显式传 --all-videos。")
        if not config.dry_run and not (args.confirm_live or manifest.get("confirm_live")):
            raise RuntimeError("正式上传需要同时传 --live --confirm-live。")
        if not config.dry_run and (not config.account or not config.password):
            raise RuntimeError("正式上传需要账号密码。可用 --account/--password 或 USERGROWTH_ACCOUNT/USERGROWTH_PASSWORD。")

        payload = run_selected_usergrowth_task(
            config,
            video_paths,
            progress=lambda message: print(message, flush=True),
        )
        print(json.dumps(_public_payload(payload), ensure_ascii=False, indent=2), flush=True)
        return 0
    except Exception as exc:  # noqa: BLE001
        print(f"ERROR: {exc}", file=sys.stderr, flush=True)
        return 1


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Standalone UserGrowth upload runner bundled with the Codex skill.",
    )
    parser.add_argument("--manifest", help="JSON config file. Relative paths inside it resolve from the manifest folder.")
    parser.add_argument("--video-folder", help="Folder containing source videos.")
    parser.add_argument("--video", action="append", default=[], help="Selected video path/name/stem. Can be repeated.")
    parser.add_argument("--video-glob", action="append", default=[], help="Glob matched against relative path and file name.")
    parser.add_argument("--video-list", help="Text file with one selected video path/name per line.")
    parser.add_argument("--all-videos", action="store_true", help="Select all videos in video-folder.")
    parser.add_argument("--backfill-excel", help="Backfill Excel path.")
    parser.add_argument("--song-excel", help="Song library Excel path.")
    parser.add_argument("--output-root", help="Output folder for task.json, logs, dry-run result.xlsx, and debug files.")
    parser.add_argument("--order-id", help="UserGrowth order ID.")
    parser.add_argument("--task-name", default=None, help="Task folder name suffix.")
    parser.add_argument("--month-tag", default=None, help="Custom month tag, e.g. 26年7月dxqs.")
    parser.add_argument("--recursive", dest="recursive", action="store_true", default=None)
    parser.add_argument("--no-recursive", dest="recursive", action="store_false")
    parser.add_argument("--live", action="store_true", help="Run real browser upload. Omit for dry-run.")
    parser.add_argument("--confirm-live", action="store_true", help="Required with --live to allow real upload/review/backfill.")
    parser.add_argument("--headless", action="store_true", help="Run browser headless in live mode.")
    parser.add_argument("--account", help="UserGrowth account. Prefer USERGROWTH_ACCOUNT env var.")
    parser.add_argument("--password", help="UserGrowth password. Prefer USERGROWTH_PASSWORD env var.")
    parser.add_argument("--max-status-retries", type=int, default=None)
    parser.add_argument("--refresh-interval-seconds", type=float, default=None)
    parser.add_argument("--browser-slow-mo-ms", type=int, default=None)
    return parser.parse_args(argv)


def _read_manifest(path: Path | None) -> dict[str, Any]:
    if not path:
        return {}
    with path.open("r", encoding="utf-8") as fp:
        payload = json.load(fp)
    if not isinstance(payload, dict):
        raise RuntimeError("manifest 必须是 JSON object。")
    return payload


def _config_from_args(args: argparse.Namespace, manifest: dict[str, Any], base_dir: Path) -> UserGrowthRunConfig:
    video_folder = _required_path(_pick(args.video_folder, manifest, "video_folder"), base_dir, "video_folder")
    backfill_excel = _required_path(
        _pick(args.backfill_excel, manifest, "backfill_excel", "order_excel"),
        base_dir,
        "backfill_excel",
    )
    song_excel = _required_path(_pick(args.song_excel, manifest, "song_excel"), base_dir, "song_excel")
    output_root = _required_path(_pick(args.output_root, manifest, "output_root"), base_dir, "output_root")
    dry_run = not bool(args.live or manifest.get("live") or manifest.get("dry_run") is False)
    recursive = args.recursive if args.recursive is not None else bool(manifest.get("recursive", True))
    return UserGrowthRunConfig(
        video_folder=video_folder,
        order_excel=backfill_excel,
        song_excel=song_excel,
        output_root=output_root,
        account=_pick(args.account, manifest, "account") or os.environ.get("USERGROWTH_ACCOUNT", ""),
        password=_pick(args.password, manifest, "password") or os.environ.get("USERGROWTH_PASSWORD", ""),
        order_id=str(_pick(args.order_id, manifest, "order_id") or "").strip(),
        task_name=str(_pick(args.task_name, manifest, "task_name") or "usergrowth_upload").strip() or "usergrowth_upload",
        month_tag=str(_pick(args.month_tag, manifest, "month_tag") or "").strip(),
        recursive=recursive,
        dry_run=dry_run,
        headless=bool(args.headless or manifest.get("headless", False)),
        max_status_retries=int(_pick(args.max_status_retries, manifest, "max_status_retries") or 3),
        refresh_interval_seconds=float(_pick(args.refresh_interval_seconds, manifest, "refresh_interval_seconds") or 12.0),
        browser_slow_mo_ms=int(_pick(args.browser_slow_mo_ms, manifest, "browser_slow_mo_ms") or 600),
    )


def _pick(value: Any, manifest: dict[str, Any], *keys: str) -> Any:
    if value not in (None, ""):
        return value
    for key in keys:
        if manifest.get(key) not in (None, ""):
            return manifest[key]
    return None


def _required_path(value: Any, base_dir: Path, name: str) -> Path:
    if value in (None, ""):
        raise RuntimeError(f"缺少 {name}。")
    path = Path(str(value))
    if not path.is_absolute():
        path = base_dir / path
    return path.resolve()


def _video_selectors_from_args(args: argparse.Namespace, manifest: dict[str, Any]) -> list[str]:
    selectors = [*_list_value(args.video), *_list_from_manifest(manifest, "videos")]
    video_list = _pick(args.video_list, manifest, "video_list")
    if video_list:
        list_path = Path(str(video_list))
        if not list_path.is_absolute() and args.manifest:
            list_path = Path(args.manifest).resolve().parent / list_path
        selectors.extend(_read_video_list(list_path))
    return selectors


def _read_video_list(path: Path) -> list[str]:
    lines = path.read_text(encoding="utf-8").splitlines()
    return [line.strip() for line in lines if line.strip() and not line.lstrip().startswith("#")]


def _list_value(value: Any) -> list[str]:
    if not value:
        return []
    if isinstance(value, str):
        return [value]
    return [str(item) for item in value if str(item).strip()]


def _list_from_manifest(manifest: dict[str, Any], key: str) -> list[str]:
    return _list_value(manifest.get(key))


def resolve_video_selection(
    video_folder: Path,
    *,
    selectors: Iterable[str],
    glob_patterns: Iterable[str],
    recursive: bool,
    all_videos: bool,
) -> list[Path]:
    if not video_folder.is_dir():
        raise RuntimeError(f"视频文件夹不存在：{video_folder}")
    scanned = scan_video_files(video_folder, recursive=recursive)
    if all_videos:
        return scanned

    selected: list[Path] = []
    missing: list[str] = []
    scanned_by_name = defaultdict(list)
    scanned_by_stem = defaultdict(list)
    scanned_by_rel = {}
    for path in scanned:
        rel = _rel_key(path, video_folder)
        scanned_by_rel[rel] = path
        scanned_by_name[path.name.lower()].append(path)
        scanned_by_stem[path.stem.lower()].append(path)

    for selector in selectors:
        matches = _match_selector(selector, video_folder, scanned_by_rel, scanned_by_name, scanned_by_stem)
        if matches:
            selected.extend(matches)
        else:
            missing.append(selector)

    for pattern in glob_patterns:
        selected.extend(_match_glob(pattern, video_folder, scanned))

    deduped = _dedupe_paths(selected)
    if missing:
        raise RuntimeError("以下视频没有匹配到：" + "；".join(missing))
    return deduped


def _match_selector(
    selector: str,
    video_folder: Path,
    scanned_by_rel: dict[str, Path],
    scanned_by_name: dict[str, list[Path]],
    scanned_by_stem: dict[str, list[Path]],
) -> list[Path]:
    value = str(selector or "").strip().strip('"')
    if not value:
        return []
    if any(char in value for char in "*?[]"):
        return _match_glob(value, video_folder, scanned_by_rel.values())
    path = Path(value)
    if not path.is_absolute():
        path = video_folder / path
    if path.is_file():
        if path.suffix.lower() not in VIDEO_SUFFIXES:
            return []
        return [path.resolve()]
    rel_key = value.replace("\\", "/").lower()
    if rel_key in scanned_by_rel:
        return [scanned_by_rel[rel_key]]
    return [*scanned_by_name.get(Path(value).name.lower(), []), *scanned_by_stem.get(Path(value).stem.lower(), [])]


def _match_glob(pattern: str, video_folder: Path, scanned: Iterable[Path]) -> list[Path]:
    wanted = str(pattern or "").replace("\\", "/").lower()
    matches = []
    for path in scanned:
        rel = _rel_key(path, video_folder)
        name = path.name.lower()
        if fnmatch.fnmatch(rel, wanted) or fnmatch.fnmatch(name, wanted):
            matches.append(path)
    return matches


def _rel_key(path: Path, video_folder: Path) -> str:
    try:
        return path.resolve().relative_to(video_folder.resolve()).as_posix().lower()
    except ValueError:
        return path.name.lower()


def _dedupe_paths(paths: Iterable[Path]) -> list[Path]:
    deduped: list[Path] = []
    seen: set[str] = set()
    for path in paths:
        key = str(path.resolve()).lower()
        if key not in seen:
            seen.add(key)
            deduped.append(path.resolve())
    return deduped


def run_selected_usergrowth_task(
    config: UserGrowthRunConfig,
    video_paths: list[Path],
    progress: ProgressCallback | None = None,
) -> dict:
    task_id = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    safe_task_name = _safe_name(config.task_name or "usergrowth_upload")
    task_root = config.output_root / f"{task_id}_{safe_task_name}"
    debug_dir = task_root / "debug"
    duplicate_song_excel = task_root / "duplicate_songs.xlsx"
    task_root.mkdir(parents=True, exist_ok=True)

    _emit(progress, f"已选中 {len(video_paths)} 个视频，开始读取歌曲库和回填模板")
    plans, items = build_selected_usergrowth_plan(
        config,
        video_paths,
        duplicate_song_output_path=duplicate_song_excel,
    )
    if not items:
        raise RuntimeError("没有可处理的视频")

    ready_count = sum(1 for item in items if item.status != "skipped")
    skipped_count = sum(1 for item in items if item.status == "skipped")
    _emit(progress, f"预检完成：待上传 {ready_count} 个，跳过 {skipped_count} 个")

    if config.dry_run:
        for item in items:
            if item.status == "pending":
                item.status = "ready"
                item.message = "预检通过，未执行上传"
        result_excel = task_root / "result.xlsx"
        write_back_results(config.order_excel, result_excel, items, include_ready=True)
        _emit(progress, f"预检结果已写入：{result_excel}")
    else:
        active_plans = [plan for plan in plans if plan.status != "skipped"]

        def write_order_backfill(plan: UserGrowthOrderPlan) -> None:
            with _backfill_lock(config.order_excel):
                write_back_results(config.order_excel, config.order_excel, plan.items, include_ready=False)
            _emit(progress, f"订单 {plan.order_id} 已写回回填 Excel")

        browser = UserGrowthBrowserClient(
            config.account,
            config.password,
            headless=config.headless,
            debug_dir=debug_dir,
            refresh_interval_seconds=config.refresh_interval_seconds,
            max_status_retries=config.max_status_retries,
            browser_slow_mo_ms=config.browser_slow_mo_ms,
            order_complete=write_order_backfill,
        )
        asyncio.run(browser.run(active_plans, progress))
        result_excel = config.order_excel
        _emit(progress, f"正式上传完成，CID 已写回：{result_excel}")

    payload = _build_payload(config, task_id, task_root, plans, items, result_excel, duplicate_song_excel)
    payload["selected_videos"] = [str(path) for path in video_paths]
    (task_root / "task.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    _write_log(task_root, payload)
    return payload


def build_selected_usergrowth_plan(
    config: UserGrowthRunConfig,
    video_paths: list[Path],
    *,
    duplicate_song_output_path: Path | None = None,
) -> tuple[list[UserGrowthOrderPlan], list[UserGrowthVideoItem]]:
    scanned_videos = [
        (path, detect_material_type(path.name))
        for path in _dedupe_paths(video_paths)
    ]
    batch_song_names = [
        extract_song_name(path.name, material_type)
        for path, material_type in scanned_videos
        if material_type not in {"金币VIP", "金币SVIP"}
    ]
    song_records = load_song_records(
        config.song_excel,
        duplicate_output_path=duplicate_song_output_path,
        duplicate_song_names=batch_song_names,
    )
    default_order_id = config.order_id.strip()
    if not default_order_id:
        raise ValueError("请填写订单ID。")

    items: list[UserGrowthVideoItem] = []
    for path, material_type in scanned_videos:
        song_name = extract_song_name(path.name, material_type)
        item = UserGrowthVideoItem(
            path=path,
            file_name=path.name,
            material_type=material_type,
            song_name=song_name,
            classification_path=classification_path_for_material(path.name),
            optional_tags=optional_tags_for_file(path.name),
        )
        _attach_song(item, song_records, config.month_tag)
        _attach_order(item, default_order_id)
        items.append(item)

    grouped: dict[str, list[UserGrowthVideoItem]] = defaultdict(list)
    skipped_items: list[UserGrowthVideoItem] = []
    for item in items:
        if item.status == "skipped" or not item.order_id:
            skipped_items.append(item)
            continue
        grouped[item.order_id].append(item)

    plans = [UserGrowthOrderPlan(order_id=order_id, items=group_items) for order_id, group_items in grouped.items()]
    if skipped_items:
        plans.append(
            UserGrowthOrderPlan(
                order_id="未分配/跳过",
                items=skipped_items,
                status="skipped",
                message="这些素材不会进入上传流程",
            )
        )
    return plans, items


def _public_payload(payload: dict) -> dict:
    public = dict(payload)
    config = dict(public.get("config") or {})
    config.pop("account", None)
    config.pop("password", None)
    public["config"] = config
    return public


def _configure_stdio() -> None:
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8")
        except Exception:
            pass


if __name__ == "__main__":
    raise SystemExit(main())
