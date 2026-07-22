---
name: manage-visual-asset-library
description: Use when a task needs a reusable image/video asset manifest, Read-based visual understanding, source-pixel effective-region annotation, incremental asset synchronization, or description-based semantic candidate retrieval across projects.
---

# 通用视觉素材库

## 核心边界

使用独立 Manifest 管理图片和视频，执行模型直接用 Read 查看真实画面并完成语义理解。脚本只执行文件扫描、媒体探测、代表帧导出和结构校验，不得调用另一个大模型理解或匹配素材。

本 Skill 只输出候选素材及匹配理由，不选择最终素材，不修改调用方时间轴，也不保存任何项目的业务、品牌、合规、布局或特殊匹配规则。BGM、字体和字幕不属于本 Skill。

同步或校验素材前阅读 [manifest-contract.md](references/manifest-contract.md)。理解图片或视频前阅读 [content-understanding.md](references/content-understanding.md)。根据文案查找素材前阅读 [semantic-matching.md](references/semantic-matching.md)。

## 工作流

1. 运行 `asset_manifest.py`，把素材根目录中的全部图片和视频同步到工作区 `visual_assets_manifest.json`。
2. 检查 `changes.added`、`changes.modified` 以及缺少 `description` 或 `effective_region` 的记录。
3. 对图片逐张使用 Read 查看原图；对视频先运行 `extract_video_frames.py`，再使用 Read 查看全部代表帧。
4. 把准确中文 `description` 和源像素坐标 `effective_region` 写回对应记录。不要添加 `keywords`、`recommended_usage`、向量或模型配置字段。
5. 运行 `validate_manifest.py`。未通过时先完成或修正素材理解，不得继续检索。
6. 接收调用方的查询文本，执行模型逐条比较 Manifest description，最多写出三个候选、匹配等级和基于画面事实的理由。
7. 没有真正匹配时返回 `no_match`；Manifest 未完成理解时返回 `needs_understanding`。不要用弱相关素材充数。

## 命令入口

```bash
ASSET_SKILL_DIR="${CODEX_HOME:-$HOME/.codex}/skills/manage-visual-asset-library"
PY=python3
```

### 同步素材

```bash
"$PY" "$ASSET_SKILL_DIR/scripts/asset_manifest.py" \
  --workspace /absolute/path/workspace \
  --asset-root /absolute/path/assets
```

默认只用路径、大小和修改时间检测变化。需要更严格的内容变化检测时可增加 `--checksum`；SHA-256 只参与增量同步，不得用于视觉相似性、业务规则或合规判断。`--quick` 只适合快速盘点，正式检索前必须完成可读取尺寸的完整扫描。

### 导出视频代表帧

```bash
"$PY" "$ASSET_SKILL_DIR/scripts/extract_video_frames.py" \
  --input /absolute/path/assets/demo.mp4 \
  --output-dir /absolute/path/workspace/asset_frames/demo \
  --output-json /absolute/path/workspace/asset_frames/demo.json
```

代表帧脚本只导出画面，不生成 description，不判断有效区域，也不做语义匹配。

### 校验 Manifest

```bash
"$PY" "$ASSET_SKILL_DIR/scripts/validate_manifest.py" \
  --manifest /absolute/path/workspace/visual_assets_manifest.json \
  --asset-root /absolute/path/assets \
  --output-json /absolute/path/workspace/asset_manifest_validation.json
```

必须确认 `ok=true` 后再执行语义检索。确定性校验只能确认字段存在且坐标合法；中文描述是否准确、具体和完整，仍由执行模型按照内容理解清单逐项复核。

## 检索输出

执行模型直接读取查询文本和 Manifest，不调用素材匹配脚本或外部模型端点。把结果写入工作区 `asset_candidates.json`，格式见 [semantic-matching.md](references/semantic-matching.md)。

候选报告只是一组可审查建议。调用方负责最终选择、业务规则、时间范围、布局、缩放、动效、品牌保护和渲染。

## 交付

最终说明列出素材根目录、Manifest、同步状态、理解完成数量、校验报告、查询文本、候选报告以及需要人工确认的素材。不得把工作区 Manifest、代表帧或具体素材复制回 Skill 目录。
