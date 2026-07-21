# 独立运行环境

## 依赖

- Python 3.10 或更高版本，仅使用标准库；
- `ffmpeg`，需要 `libx264`、`aac`、`subtitles/libass`、`loudnorm` 和 `ebur128`；
- `ffprobe`；
- 可选本地 `whisper` CLI 和已缓存模型，用于逐词时间戳；不可用时退化为多阈值音量检测；
- 输入视频、BGM、素材目录和时间轴 JSON。
- 工作区素材 Manifest 由 `sync-assets` 按需生成，不是 Skill 内置文件。
- 可选 `${CODEX_HOME:-$HOME/.codex}/skills/video-motion-effects`；启用时额外需要 Node.js、Chrome/Chromium 及该 Skill 已安装的 Remotion 依赖。

不需要任何业务项目、虚拟环境、数据库、API 服务或 Python 第三方包。

## BGM 响度

- `--bgm-target-lufs`：BGM 在混音前的目标综合响度，默认 `-28 LUFS`，允许范围 `-40` 到 `-18 LUFS`；
- `--bgm-volume`：完成 LUFS 归一化后的微调倍率，默认 `1.0`，允许范围 `0.5–1.5`；
- 旧流程中的 `--bgm-volume 0.22` 会被拒绝，因为它会在归一化后再次大幅衰减 BGM；
- 混音顺序为：裁切/循环 BGM → `loudnorm` 到目标 LUFS → 微调倍率 → 淡入淡出 → 与人声和提示音混合 → limiter 防峰值溢出。

## 素材输入

Skill 不保存默认素材目录、BGM 路径或现有素材文件名。每次运行必须显式传入：

```bash
python3 scripts/soda_pipeline.py preflight \
  --asset-root /absolute/path/assets \
  --bgm /absolute/path/background-music.mp3 \
  --timeline-json /absolute/path/timeline.json
```

时间轴 JSON 中的素材路径默认相对 `--asset-root`；也可以使用绝对路径。

素材清单同步示例：

```bash
python3 scripts/soda_pipeline.py sync-assets \
  --workspace /absolute/path/workspace \
  --asset-root /absolute/path/assets
```

Manifest 默认写入工作区的 `soda_assets_manifest.json`；它记录相对路径、类型、推断类别、大小、修改时间和可探测的媒体元数据。路径、大小和修改时间未变化时不会重写；需要内容级变化检测时使用 `--checksum`。需要大模型理解图片/视频时，由执行 Skill 的模型直接用 Read 工具查看原图和视频代表帧，并把一段中文 `description` 写回 Manifest。

## 时间轴 JSON

结构模板：`references/timeline-template.json`。

- `time_mode=original`：时间点来自去气口前的原视频，使用 `removed_ranges` 重新映射；
- `time_mode=input`：时间点来自当前输入视频，渲染时再除以 `speed`；
- `time_mode=output`：时间点已经是最终主片时间轴；
- `speed`：默认 `1.1`。通过 `render --speed <倍速>` 传入的值优先于时间线字段；
- 开场策略：固定从数字人口播第一帧直接开始。新时间轴不提供 `pre_roll_duration` 和 `hook`；旧时间轴中的同名字段会被忽略；
- `captions`：字幕入点、出点和文本；渲染时统一去除中英文标点；
- `--script-file`：调用方提供口播文本时，作为字幕文案最高优先级；`render` 自动生成修正版时间轴，不覆盖原始时间轴；
- `materials`：物料相对路径、类型、布局和时间；
- `motion_effects`：可选 Remotion 随机入场动效策略；缺省按 `mode=auto` 处理。字段和回退行为见 [motion-effects.md](motion-effects.md)；
- `visual_policy`：禁止渲染器生成背景黑条/黑框/半透明黑色承托层，要求字幕使用 `2–3px` 黑色细描边且阴影为 `0`，强制 logo 和警示语处于最高层，强制素材避让两者的保护区，并要求源视频素材固定黑边检查按预检错误处理；
- `font/logo/tail`：字体、黑白 logo 和尾帧路径；`font.body_color` 默认白色，`font.brand_color` 默认品牌绿 `#3BFD42`；
- `font.caption_style`：独立 renderer 的 ASS 字幕字号、横纵缩放、字间距、描边、阴影、对齐和位置。新模板使用 `position_mode=center_offset`，以画布中心为原点、X 向右、Y 向上，`x=0,y=-500` 会映射到 1080×1920 画布的 `(540,1460)`；旧时间轴未提供该字段时继续使用原有边距定位；
- 渲染时会把正文字体和 SodaFont 一并复制到临时 libass 字体目录，确保品牌词不会因为字体文件位于不同目录而回退为普通字体；
- `logo.mode=auto`：透明 logo 画布与目标视频同宽高比时自动整画布叠加，否则使用定位模式；
- `logo.mode=full_canvas`：整张 logo 画布缩放到输出尺寸并在 `(0,0)` 叠加，忽略 `width/x/y/crop`；
- `logo.mode=placed`：使用 `width/x/y`，可选 `crop`，适用于紧边或比例不同的 logo；

`phone` 素材只做等比缩放和直接叠加，不绘制黑色背景板。素材无需避让字幕区域，但必须限制在 `visual_policy.material_safe_area` 内；默认四边距为左/右 `48px`、上 `320px`、下 `180px`。渲染器默认保持素材原尺寸，先平移避让 logo/警示语区域；只有平移仍无法解决时，才计算不遮挡品牌区域的最大等比尺寸，不设置固定缩放上限或下限。透明图片按 alpha 可见边界判断越界；视频和无透明图片按完整画面处理。Remotion Alpha 层在合成前再次裁切并透明补边到安全区，防止动效超出。所有素材完成叠加后，先绘制去标点 ASS 字幕与 CTA，再叠加 logo，最后绘制警示语。

处理新视频时复制模板 JSON 到任务目录，填写实际素材路径、字幕和时间点，不要直接覆盖 Skill 内的结构模板。模板中的占位值必须全部替换后才能预检或渲染。

按默认流程先使用 `trim-pauses` 生成去气口中间文件，再把该文件传给 `render`。若字幕和物料时间来自原视频，使用 `time_mode=original` 并填写实际 `removed_ranges`；若时间已经重算到中间文件，使用 `time_mode=input`。
