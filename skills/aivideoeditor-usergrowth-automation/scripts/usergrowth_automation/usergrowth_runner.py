from __future__ import annotations

import asyncio
from concurrent.futures import ThreadPoolExecutor, as_completed
import json
import threading
from datetime import datetime
from pathlib import Path
from typing import Callable

from .usergrowth_browser import UserGrowthBrowserClient
from .usergrowth_excel import write_back_results
from .usergrowth_models import (
    UserGrowthBatchResult,
    UserGrowthCancelled,
    UserGrowthOrderPlan,
    UserGrowthRunConfig,
    UserGrowthVideoItem,
)
from .usergrowth_planner import build_usergrowth_plan


ProgressCallback = Callable[[str], None]
_BACKFILL_LOCKS_GUARD = threading.Lock()
_BACKFILL_LOCKS: dict[str, threading.Lock] = {}


def run_usergrowth_batches(
        configs: list[UserGrowthRunConfig],
        *,
        concurrency: int = 10,
        progress: ProgressCallback | None = None,
        cancel_event: threading.Event | None = None,
) -> list[UserGrowthBatchResult]:
    """并发执行多批 UserGrowth 任务；每批独立浏览器，同一回填 Excel 串行写入。"""
    if not configs:
        return []
    try:
        requested_workers = int(concurrency or 1)
    except (TypeError, ValueError):
        requested_workers = 10
    worker_count = max(1, min(requested_workers, 10, len(configs)))
    results: list[UserGrowthBatchResult | None] = [None] * len(configs)

    def run_one(index: int, config: UserGrowthRunConfig) -> UserGrowthBatchResult:
        batch_label = _batch_label(index, config)

        def batch_progress(message: str) -> None:
            _emit(progress, f"[{batch_label}] {message}")

        if _is_cancelled(cancel_event):
            return UserGrowthBatchResult(
                index=index,
                order_id=config.order_id,
                video_folder=str(config.video_folder),
                status="cancelled",
                message="已取消",
            )
        batch_progress("开始执行")
        try:
            payload = run_usergrowth_task(config, batch_progress, cancel_event=cancel_event)
            summary = payload.get("summary", {})
            batch_progress("执行完成")
            return UserGrowthBatchResult(
                index=index,
                order_id=config.order_id,
                video_folder=str(config.video_folder),
                status="success",
                summary=summary,
                payload=payload,
                message="完成",
            )
        except UserGrowthCancelled as exc:
            batch_progress("执行已取消")
            return UserGrowthBatchResult(
                index=index,
                order_id=config.order_id,
                video_folder=str(config.video_folder),
                status="cancelled",
                message=str(exc) or "已取消",
            )
        except Exception as exc:  # noqa: BLE001
            batch_progress(f"执行失败：{exc}")
            return UserGrowthBatchResult(
                index=index,
                order_id=config.order_id,
                video_folder=str(config.video_folder),
                status="failed",
                message=str(exc),
            )

    with ThreadPoolExecutor(max_workers=worker_count) as executor:
        future_map = {
            executor.submit(run_one, index, config): index
            for index, config in enumerate(configs)
        }
        for future in as_completed(future_map):
            index = future_map[future]
            results[index] = future.result()

    return [result for result in results if result is not None]


def run_usergrowth_task(
        config: UserGrowthRunConfig,
        progress: ProgressCallback | None = None,
        *,
        cancel_event: threading.Event | None = None,
) -> dict:
    """执行一次 UserGrowth 任务：预检、浏览器上传、回填 Excel、写日志。"""
    _raise_if_cancelled(cancel_event)
    task_id = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    safe_task_name = _safe_name(config.task_name or "usergrowth_upload")
    task_root = config.output_root / f"{task_id}_{safe_task_name}"
    debug_dir = task_root / "debug"
    duplicate_song_excel = task_root / "duplicate_songs.xlsx"
    task_root.mkdir(parents=True, exist_ok=True)

    _emit(progress, "正在扫描视频文件夹并读取 Excel")
    _raise_if_cancelled(cancel_event)
    plans, items = build_usergrowth_plan(config, duplicate_song_output_path=duplicate_song_excel)
    _raise_if_cancelled(cancel_event)
    if not items:
        raise RuntimeError("未扫描到可处理视频")

    ready_count = sum(1 for item in items if item.status != "skipped")
    skipped_count = sum(1 for item in items if item.status == "skipped")
    _emit(progress, f"预检完成：待上传 {ready_count} 个，跳过 {skipped_count} 个")

    if config.dry_run:
        _raise_if_cancelled(cancel_event)
        for item in items:
            if item.status == "pending":
                item.status = "ready"
                item.message = "预检通过，未执行上传"
        _emit(progress, "当前是预检模式，不会打开浏览器上传")
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
            cancel_event=cancel_event,
        )
        _raise_if_cancelled(cancel_event)
        asyncio.run(browser.run(active_plans, progress))

    if config.dry_run:
        result_excel = task_root / "result.xlsx"
        write_back_results(config.order_excel, result_excel, items, include_ready=True)
    else:
        result_excel = config.order_excel
    payload = _build_payload(config, task_id, task_root, plans, items, result_excel, duplicate_song_excel)
    (task_root / "task.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    _write_log(task_root, payload)
    if config.dry_run:
        _emit(progress, f"任务完成，预检结果已保存：{result_excel}")
    else:
        _emit(progress, f"任务完成，CID 已写回：{result_excel}")
    return payload


def _is_cancelled(cancel_event: threading.Event | None) -> bool:
    return bool(cancel_event and cancel_event.is_set())


def _raise_if_cancelled(cancel_event: threading.Event | None) -> None:
    if _is_cancelled(cancel_event):
        raise UserGrowthCancelled("任务已取消")


def _build_payload(
    config: UserGrowthRunConfig,
    task_id: str,
    task_root: Path,
    plans: list[UserGrowthOrderPlan],
    items: list[UserGrowthVideoItem],
    result_excel: Path,
    duplicate_song_excel: Path,
) -> dict:
    """组装 task.json 中保存的任务配置、统计和明细。"""
    return {
        "task_id": task_id,
        "task_root": str(task_root),
        "mode": "dry_run" if config.dry_run else "browser_upload",
        "config": {
            "video_folder": str(config.video_folder),
            "backfill_excel": str(config.order_excel),
            "song_excel": str(config.song_excel),
            "output_root": str(config.output_root),
            "order_id": config.order_id,
            "task_name": config.task_name,
            "month_tag": config.month_tag,
            "recursive": config.recursive,
            "dry_run": config.dry_run,
            "headless": config.headless,
            "refresh_interval_seconds": config.refresh_interval_seconds,
            "browser_slow_mo_ms": config.browser_slow_mo_ms,
        },
        "summary": {
            "total": len(items),
            "ready": sum(1 for item in items if item.status in {"ready", "pending"}),
            "success": sum(1 for item in items if item.status == "success"),
            "skipped": sum(1 for item in items if item.status == "skipped"),
            "failed": sum(1 for item in items if item.status == "failed"),
        },
        "result_excel": str(result_excel),
        "duplicate_song_excel": str(duplicate_song_excel),
        "plans": [plan.to_dict() for plan in plans],
    }


def _write_log(task_root: Path, payload: dict) -> None:
    """把任务摘要和每个素材的执行结果写入 run.log。"""
    lines = [
        f"task_id: {payload['task_id']}",
        f"mode: {payload['mode']}",
        f"video_folder: {payload['config']['video_folder']}",
        f"backfill_excel: {payload['config']['backfill_excel']}",
        f"song_excel: {payload['config']['song_excel']}",
        f"order_id: {payload['config']['order_id']}",
        f"refresh_interval_seconds: {payload['config']['refresh_interval_seconds']}",
        f"browser_slow_mo_ms: {payload['config']['browser_slow_mo_ms']}",
        f"result_excel: {payload['result_excel']}",
        f"duplicate_song_excel: {payload.get('duplicate_song_excel', '')}",
        "",
        "[summary]",
    ]
    lines.extend(f"{key}: {value}" for key, value in payload["summary"].items())
    lines.append("")
    lines.append("[items]")
    for plan in payload["plans"]:
        lines.append(f"order_id: {plan['order_id']} | status={plan['status']} | {plan.get('message', '')}")
        for item in plan["items"]:
            lines.append(
                f"  {item['status']} | {item['file_name']} | order={item['order_id']} | "
                f"type={item['material_type']} | song={item['song_name']} | id={item['song_id']} | "
                f"cid={item['cid']} | {item['message']}"
            )
            lines.append(f"    分类标签: {' / '.join(item.get('classification_path') or [])}")
            lines.append(f"    自定义标签: {'、'.join(item.get('custom_tags') or [])}")
            lines.append(f"    选填标签: {'、'.join(item.get('optional_tags') or [])}")
    (task_root / "run.log").write_text("\n".join(lines) + "\n", encoding="utf-8")


def _safe_name(value: str) -> str:
    """把任务名转换为可用于文件夹名称的安全字符串。"""
    cleaned = "".join(ch if ch.isalnum() or ch in "-_." else "_" for ch in value.strip())
    return cleaned[:48].strip("_") or "usergrowth_upload"


def _batch_label(index: int, config: UserGrowthRunConfig) -> str:
    order = config.order_id or f"批次{index + 1}"
    return f"{index + 1}:{order}"


def _backfill_lock(path: Path) -> threading.Lock:
    key = str(path.resolve()).lower()
    with _BACKFILL_LOCKS_GUARD:
        lock = _BACKFILL_LOCKS.get(key)
        if lock is None:
            lock = threading.Lock()
            _BACKFILL_LOCKS[key] = lock
        return lock


def _emit(progress: ProgressCallback | None, message: str) -> None:
    """向 UI 或调用方发送任务进度消息。"""
    if progress:
        progress(message)
