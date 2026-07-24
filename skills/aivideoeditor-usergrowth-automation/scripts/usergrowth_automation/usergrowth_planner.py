from __future__ import annotations

from pathlib import Path

from .usergrowth_excel import load_song_records, match_song_record
from .usergrowth_models import UserGrowthOrderPlan, UserGrowthRunConfig, UserGrowthVideoItem, VIDEO_SUFFIXES
from .usergrowth_rules import (
    classification_path_for_material,
    custom_tags_for_material,
    detect_material_type,
    extract_song_name,
    optional_tags_for_file,
)


def scan_video_files(folder: Path, recursive: bool = True) -> list[Path]:
    """扫描视频文件夹，返回可处理的视频文件列表。"""
    if not folder.is_dir():
        return []
    iterator = folder.rglob("*") if recursive else folder.iterdir()
    return sorted(path for path in iterator if path.is_file() and path.suffix.lower() in VIDEO_SUFFIXES)


def build_usergrowth_plan(
        config: UserGrowthRunConfig,
        *,
        duplicate_song_output_path: Path | None = None,
) -> tuple[list[UserGrowthOrderPlan], list[UserGrowthVideoItem]]:
    """根据视频文件、歌曲库和订单 ID 生成上传计划。"""
    scanned_videos = [
        (path, detect_material_type(path.name))
        for path in scan_video_files(config.video_folder, recursive=config.recursive)
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

    return group_usergrowth_items(items), items


def group_usergrowth_items(items: list[UserGrowthVideoItem]) -> list[UserGrowthOrderPlan]:
    """按订单和整卡默认值分批，避免“一键复用”覆盖异构素材。"""
    grouped: dict[
        tuple[str, tuple[str, ...], tuple[str, ...]],
        list[UserGrowthVideoItem],
    ] = {}
    skipped_items: list[UserGrowthVideoItem] = []
    for item in items:
        if item.status == "skipped" or not item.order_id:
            skipped_items.append(item)
            continue
        profile = (
            item.order_id,
            tuple(item.classification_path),
            tuple(item.custom_tags),
        )
        grouped.setdefault(profile, []).append(item)

    plans = [
        UserGrowthOrderPlan(order_id=order_id, items=group_items)
        for (order_id, _classification_path, _custom_tags), group_items in grouped.items()
    ]
    if skipped_items:
        plans.append(
            UserGrowthOrderPlan(
                order_id="未分配/跳过",
                items=skipped_items,
                status="skipped",
                message="这些素材不会进入上传流程",
            )
        )
    return plans


def _attach_song(item: UserGrowthVideoItem, song_records, month_tag: str) -> None:
    """为视频条目匹配歌曲 ID，并生成自定义标签和禁投状态。"""
    if item.material_type in {"金币VIP", "金币SVIP"}:
        item.custom_tags = custom_tags_for_material(item.material_type, "", item.file_name, month_tag=month_tag)
        return

    record, candidates = match_song_record(item.song_name, song_records)
    if not record:
        if candidates:
            item.message = f"歌曲名匹配到多个候选，未填写歌曲 ID 自定义标签：{', '.join(candidate.song_name for candidate in candidates[:5])}"
        else:
            item.message = "歌曲库中未匹配到歌曲 ID，未填写歌曲 ID 自定义标签"
        item.custom_tags = custom_tags_for_material(item.material_type, "", item.file_name, month_tag=month_tag)
        return

    item.song_name = record.song_name
    item.song_id = record.song_id
    item.blocked = record.blocked
    item.custom_tags = custom_tags_for_material(item.material_type, item.song_id, item.file_name, month_tag=month_tag)
    if record.blocked:
        item.status = "skipped"
        item.message = "歌曲库标记禁投，已跳过"


def _attach_order(item: UserGrowthVideoItem, order_id: str) -> None:
    """把客户端输入的订单 ID 绑定到可上传素材上。"""
    if item.status == "skipped":
        return
    if not item.material_type:
        item.status = "skipped"
        item.message = "文件名未识别到素材类型"
        return

    if order_id:
        item.order_id = order_id
        return

    item.status = "skipped"
    item.message = "请填写订单ID"
