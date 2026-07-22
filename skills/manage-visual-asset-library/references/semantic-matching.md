# 基于 description 的语义候选检索

## 边界

执行模型直接读取调用方查询文本和已通过校验的 Manifest，比较 description 和确定性媒体事实。不调用匹配脚本、额外模型端点或向量库。

本 Skill 只返回候选及匹配理由，不选择最终素材，不修改调用方时间轴。调用方负责业务判断、最终采用、时间范围、合规、布局和渲染。

## 匹配流程

1. 运行 Manifest 校验；未完成理解时停止检索。
2. 应用调用方提供的通用媒体事实过滤条件，例如 `kind`、横竖方向、最小分辨率或时长范围。
3. 阅读剩余记录的完整 description。
4. 比较查询与画面的主体、动作、功能、状态、场景、可见文字和数字。
5. 排除只有文件名、目录名或单个关键词相似，但画面语义不一致的素材。
6. 最多返回三个真正相关的候选，按 `strong`、`medium`、`weak` 排序。
7. 每个候选给出基于 description 画面事实的明确理由。
8. 没有匹配时返回空数组，不使用弱相关素材凑数。

## 候选报告

默认写入工作区 `asset_candidates.json`：

```json
{
  "schema_version": 1,
  "generated_at": "2026-07-22T00:00:00+00:00",
  "manifest": "/absolute/path/visual_assets_manifest.json",
  "query": "打开播放模式并切换为随机播放",
  "status": "matched",
  "candidates": [
    {
      "rank": 1,
      "relative_path": "ui/play-mode.mp4",
      "kind": "video",
      "description": "手机录屏展示进入播放模式页面并切换为随机播放。",
      "match_level": "strong",
      "reason": "画面主体、操作动作和最终随机播放状态均与查询一致。"
    }
  ],
  "no_match_reason": null
}
```

不要添加最终采用标记、时间范围、布局、位置或项目业务字段。

## 状态

- `matched`：至少有一个具有清晰画面证据的候选；
- `no_match`：Manifest 完整但没有合适素材，`candidates` 为空并填写 `no_match_reason`；
- `needs_understanding`：存在缺失或无效理解字段，不执行语义比较；
- `error`：Manifest 不可读、根目录不一致或存在结构错误。

匹配等级是可审查的语义分级，不伪造精确数值分数。即使第一个候选为 `strong`，最终采用权也始终属于调用方。
