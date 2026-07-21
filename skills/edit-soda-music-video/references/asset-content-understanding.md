# 素材内容理解与 description 匹配

## 目标

在现有素材 Manifest 的基础上，可选调用一个 OpenAI-compatible 多模态模型，为图片和视频素材生成一段中文 `description`。只保存这一个语义理解字段，不生成或保存 `keywords`、`recommended_usage` 或其他重复的语义字段。

现有的路径、类型、FFprobe 元数据、合规状态和时间轴路径继续作为规则字段保留。

## 内容理解

基础素材扫描和内容理解分开执行：

```bash
python3 scripts/soda_pipeline.py sync-assets \
  --workspace /absolute/path/workspace \
  --asset-root /absolute/path/assets

python3 scripts/soda_pipeline.py understand-assets \
  --manifest /absolute/path/workspace/soda_assets_manifest.json \
  --model <multimodal-model>
```

`understand-assets` 只处理图片和视频。图片直接发送给模型；视频先用 FFmpeg 抽取代表帧，再把代表帧和媒体信息发送给模型。字体、字幕、音频和 logo/尾帧等非普通视觉素材不会被强制理解。

模型只需要返回：

```json
{"description":"一段自然、具体、可检索的中文描述"}
```

描述应合并说明画面主体、场景、动作、界面或物料展示的信息、可见文字和适合表达的口播语义。不得根据文件名臆测画面内容，透明区域不得描述为黑色背景。

Manifest 中的记录形态：

```json
{
  "content_understanding": {
    "description": "这是一段手机录屏，展示用户进入汽水音乐播放设置页面并切换播放模式，适合用于介绍播放模式和播放设置功能。",
    "status": "ready",
    "model": "<configured-model>",
    "prompt_version": "asset-understanding-v1",
    "source_fingerprint": "<sha256>",
    "analyzed_at": "<ISO-8601>"
  }
}
```

`status/model/prompt_version/source_fingerprint/analyzed_at` 只用于缓存和故障追踪，不是额外的语义字段。

## 增量和失败处理

- 素材内容指纹、模型和 Prompt 版本都未变化时复用已有 description；
- 新增、替换、内容变化或 Prompt 版本变化时重新理解；
- `--force` 强制重新调用模型；
- 模型失败时写入 `status=failed` 和错误信息，不把失败素材当作已理解素材参与匹配；
- Manifest 仍是工作区缓存，不复制回 Skill 目录。

模型配置可以通过命令行或环境变量提供：

```bash
export OPENAI_BASE_URL="https://api.openai.com/v1"
export OPENAI_API_KEY="<key>"
export OPENAI_MODEL="<multimodal-model>"
```

实现使用标准库 HTTP 请求，不绑定某一个 SDK 或向量数据库。

## description 匹配

匹配入口：

```bash
python3 scripts/soda_pipeline.py match-materials \
  --manifest /absolute/path/workspace/soda_assets_manifest.json \
  --query "介绍播放模式功能" \
  --output-json /absolute/path/material_candidates.json \
  --model <text-or-multimodal-model>
```

匹配只读取 `content_understanding.description`，不读取或生成关键词数组。流程是：

1. 先按 `kind`、`category`、解析状态等硬条件过滤；
2. 用 description 做本地文本预筛选，限制候选数量；
3. 把口播查询和候选 description 交给模型排序；
4. 输出候选 path、分数、理由和首选素材；
5. 人工或上层 Agent 确认后，才把首选 path 写入时间轴的 `materials[].path`。

模型只能从候选 path 中选择，不能凭文件名创造新路径。没有可靠匹配时返回空候选，不得为了填满画面强行选素材。

没有模型配置时可使用 `--no-llm` 做 description 文本重叠的离线回退；正式制作优先使用模型匹配，并保留匹配报告。
