# 可选 Remotion 入场动效

## 接入规则

渲染器检查 `${CODEX_HOME:-$HOME/.codex}/skills/video-motion-effects`。当 Skill、Node、Chrome、Remotion 和 `@vysmo/transitions` 固定依赖均可用时，从其 `list-effects` 返回值中随机选择效果；当前正式效果包括 `dynamic_shrink`、`bottom_rise`、`perspective_settle`、`flash_stretch` 和 `page_curl`。选中效果后默认使用目录返回的 `defaultPreset`、`defaultDuration` 和适用时的 `defaultSamples`；兼容 preset 不参与随机选择。

Remotion 只生成短透明 ProRes 4444 入场片段。入口素材读取 Manifest 的 `effective_region` 做品牌区域碰撞计算，但只有 `icon` 裁切 effective_region；`phone`、`full_alpha` 和 `cta_icon` 必须把完整源文件按源像素尺寸送入动效。源画布和空白留边不触发碰撞。只有有效内容真实碰到 logo/警示语保护区且移动无法解决时才缩放整个素材到最大安全尺寸。随后在动效素材上方绘制字幕与 CTA，再叠加 logo，最后绘制警示语。

动效层完全继承素材的 `[start,end)` 半开区间。同一 `sequence_id` 的下一个素材在字幕切换点直接接管，不为 Remotion 入场效果额外添加 0.2–0.3 秒缓冲、交叉淡化或重叠帧。

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
    "min_visible_duration": 0.8
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
- `effect_duration`：可选全局覆盖。省略时每个效果使用 `list-effects.defaultDuration`；只有明确要求统一重定时才填写。
- `samples`：可选全局覆盖，只作用于目录声明 `defaultSamples` 的效果。省略时使用各效果目录默认值。

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
