# 通用视觉素材 Manifest 契约

## 目的

`visual_assets_manifest.json` 是通用素材 Skill 与消费项目之间的唯一数据契约。它只收录图片和视频；音频、字体、字幕和项目业务字段由消费方自行管理。

## Schema

```json
{
  "schema_version": 1,
  "generated_at": "2026-07-22T00:00:00+00:00",
  "workspace": "/absolute/path/workspace",
  "asset_root": "/absolute/path/assets",
  "fingerprint_mode": "path-size-mtime",
  "metadata_mode": "ffprobe",
  "fingerprint": "a1b2c3d4",
  "summary": {
    "total": 1,
    "total_size_bytes": 123456,
    "by_kind": {"image": 1}
  },
  "changes": {
    "status": "updated",
    "added": [],
    "removed": [],
    "modified": [],
    "reused_metadata_count": 1
  },
  "scan_errors": [],
  "assets": [
    {
      "relative_path": "ui/withdraw.png",
      "file_name": "withdraw.png",
      "extension": ".png",
      "kind": "image",
      "size_bytes": 123456,
      "mtime_ns": 123456789,
      "media": {
        "probe_ok": true,
        "width": 1080,
        "height": 1920
      },
      "description": "完整的手机页面，画面中清晰显示页面结构和当前状态。",
      "effective_region": {
        "x": 99,
        "y": 105,
        "width": 882,
        "height": 1743,
        "coordinate_space": "source_pixels"
      }
    }
  ]
}
```

## 字段规则

- `relative_path` 是素材在 `asset_root` 下的引用键；不要把绝对素材路径写进单条记录。
- `kind` 只允许 `image` 或 `video`。
- `media.width/height` 必须来自 FFprobe 等确定性媒体探测结果。
- `description` 必须来自执行模型实际查看的原图或视频代表帧。
- `effective_region` 必须使用 `source_pixels`，且完全落在源尺寸内。
- 不根据文件名或目录名推断语义类别；文件名只用于定位真实文件。
- 只保存 description 和 effective_region 作为模型理解结果，不保存 `keywords`、`recommended_usage`、向量索引或模型调用配置。
- 允许消费方读取旧 Manifest 中的额外字段或非视觉记录，但通用同步的新记录不生成这些字段。

## 增量更新

- 默认以相对路径、大小和修改时间生成指纹。
- `--checksum` 可用 SHA-256 加强变化检测，但哈希不得用于判断视觉内容、特殊素材或业务合规。
- 未变化记录保留已有 description/effective_region。
- 新增或变化记录不复用旧理解字段，必须重新 Read。
- 删除文件必须从新 Manifest 移除。
- 指纹完全一致时返回 `status=unchanged`，不重写 Manifest。

## 完整性门禁

正式检索前必须满足：

1. Manifest 的 `asset_root` 与当前根目录一致；
2. 根目录中所有支持的图片和视频均被记录，记录指向的文件也真实存在；
3. 每条视觉记录都有可读取的源尺寸；
4. 每条视觉记录都有非空 description；
5. 每条视觉记录都有合法的 source-pixel effective_region；
6. description 已由执行模型按内容理解清单复核，而不只是程序判定非空。

`--quick` 生成的记录可能缺少媒体尺寸，只能用于快速盘点，不能通过正式完整性门禁。
