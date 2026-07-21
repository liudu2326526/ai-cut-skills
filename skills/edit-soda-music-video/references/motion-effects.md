# 可选 Remotion 入场动效

## 接入规则

渲染器检查 `${CODEX_HOME:-$HOME/.codex}/skills/video-motion-effects`。当 Skill、Node、Chrome 和 Remotion 固定依赖均可用时，从其 `list-effects` 返回值中随机选择效果；当前正式效果包括 `dynamic_shrink`、`bottom_rise`、`perspective_settle`、`flash_stretch` 和 `page_curl`。

Remotion 只生成短透明 ProRes 4444 入场片段。物料稳定布局默认保持原尺寸，只有在确实碰到 logo/警示语保护区且平移无法解决时才缩放到不遮挡品牌区域的最大等比尺寸；不设置固定缩放上限或下限。FFmpeg 合成时再把整个 Alpha 动效层裁切到素材可用区并透明补回全画布，防止放大、拖影、透视或卷页过程进入 logo 和警示语保护区。随后在动效素材上方绘制字幕与 CTA，再叠加 logo，最后绘制警示语。

## 时间线配置

```json
{
  "motion_effects": {
    "mode": "auto",
    "selection": "random",
    "seed": null,
    "apply_probability": 1.0,
    "max_events": 3,
    "eligible_layouts": ["full_alpha", "phone", "cta_icon"],
    "min_visible_duration": 0.8,
    "effect_duration": 0.333333,
    "samples": 48
  }
}
```

- `mode=auto`：已安装且可用时应用；不可用时记录警告并回退静态素材。
- `mode=off`：禁用所有入场动效。
- `mode=required`：Skill 缺失或任一入场动效渲染失败时终止成片。
- `selection=random`：从已安装 Skill 返回的效果列表中随机选择。
- `seed`：显式随机种子。省略时使用时间线、输出路径和物料信息生成稳定种子。
- `apply_probability`：每个合格物料进入候选池的概率。
- `max_events`：单条视频最多应用的物料数；默认 `3`，`0` 表示不限制。
- `eligible_layouts`：允许应用动效的布局。默认排除短时小图标。
- `min_visible_duration`：物料最短可见时间。
- `effect_duration`：Remotion 入场阶段时长。
- `samples`：支持该参数的效果所使用的亚帧采样层数。

当前只处理 `kind=image`。视频物料继续使用原 FFmpeg 叠加，不交给 Remotion。

## 随机与复现

默认种子绑定时间线绝对路径、输出绝对路径和物料时间信息。同一输出路径重复 dry-run 和正式渲染会得到相同选择；更换输出路径可生成另一随机版本。正式投放报告必须保留 `motion_effects.seed`、`planned`、`rendered` 和失败回退记录。

## CLI 覆盖

```bash
python3 scripts/soda_pipeline.py render \
  ... \
  --motion-effects auto \
  --motion-seed version-a
```

CLI 参数覆盖时间线中的 `mode` 和 `seed`。需要绝对稳定的人工版本时提供固定 `--motion-seed`；排查问题时使用 `--motion-effects off` 对照静态版本。
