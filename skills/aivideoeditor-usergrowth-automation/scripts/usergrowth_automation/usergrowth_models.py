from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


VIDEO_SUFFIXES = {".mp4", ".mov", ".mkv", ".avi"}


class UserGrowthCancelled(BaseException):
    """UserGrowth 任务被用户取消。"""


@dataclass
class UserGrowthVideoItem:
    """单个待上传视频在预检、上传、回填过程中的状态载体。"""

    path: Path
    file_name: str
    material_type: str
    song_name: str
    song_id: str = ""
    order_id: str = ""
    custom_tags: list[str] = field(default_factory=list)
    classification_path: list[str] = field(default_factory=list)
    optional_tags: list[str] = field(default_factory=list)
    blocked: bool = False
    status: str = "pending"
    message: str = ""
    cid: str = ""
    cid_material_type: str = ""

    def to_dict(self) -> dict[str, Any]:
        """把视频条目转换为可写入日志和 task.json 的字典。"""
        return {
            "path": str(self.path),
            "file_name": self.file_name,
            "material_type": self.material_type,
            "song_name": self.song_name,
            "song_id": self.song_id,
            "order_id": self.order_id,
            "custom_tags": self.custom_tags,
            "classification_path": self.classification_path,
            "optional_tags": self.optional_tags,
            "blocked": self.blocked,
            "status": self.status,
            "message": self.message,
            "cid": self.cid,
            "cid_material_type": self.cid_material_type,
        }


@dataclass
class UserGrowthOrderRow:
    """回填 Excel 中与订单/素材/CID 相关的一行数据。"""

    order_id: str
    material_type: str = ""
    song_name: str = ""
    cid: str = ""
    sheet_name: str = ""
    row_number: int = 0


@dataclass
class UserGrowthSongRecord:
    """歌曲库 Excel 中用于匹配歌名、歌曲 ID 和禁投状态的一行数据。"""

    song_name: str
    song_id: str
    artist_name: str = ""
    link: str = ""
    blocked: bool = False
    sheet_name: str = ""
    row_number: int = 0


@dataclass
class UserGrowthOrderPlan:
    """同一个订单下的一组待上传素材及其执行结果。"""

    order_id: str
    items: list[UserGrowthVideoItem] = field(default_factory=list)
    task_id: str = ""
    upload_limit: int | None = None
    status: str = "pending"
    message: str = ""

    def to_dict(self) -> dict[str, Any]:
        """把订单执行计划转换为可序列化字典。"""
        return {
            "order_id": self.order_id,
            "task_id": self.task_id,
            "upload_limit": self.upload_limit,
            "status": self.status,
            "message": self.message,
            "items": [item.to_dict() for item in self.items],
        }


@dataclass
class UserGrowthRunConfig:
    """客户端发起一次 UserGrowth 预检或上传任务所需的配置。"""

    video_folder: Path
    order_excel: Path
    song_excel: Path
    output_root: Path
    account: str
    password: str
    order_id: str = ""
    task_name: str = "usergrowth_upload"
    month_tag: str = ""
    recursive: bool = True
    dry_run: bool = True
    headless: bool = False
    max_status_retries: int = 3
    refresh_interval_seconds: float = 12.0
    browser_slow_mo_ms: int = 600


@dataclass
class UserGrowthBatchResult:
    """多批次并发执行中的单批结果。"""

    index: int
    order_id: str
    video_folder: str
    status: str
    summary: dict[str, Any] = field(default_factory=dict)
    payload: dict[str, Any] = field(default_factory=dict)
    message: str = ""
