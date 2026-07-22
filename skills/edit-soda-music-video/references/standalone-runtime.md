# 独立运行环境

## 依赖

- Python 3.10 或更高版本，仅使用标准库；
- `ffmpeg`，需要 `libx264`、`aac`、`subtitles/libass`、`loudnorm` 和 `ebur128`；
- `ffprobe`；
- 本地 `whisper` CLI 和已缓存 `tiny` 模型：无调用方台词时不可用可退化为多阈值音量检测；提供台词时必须可用并输出 `--word_timestamps True` 的词级 JSON，否则渲染失败；
- 输入视频、BGM、素材目录和时间轴 JSON。
- 工作区素材 Manifest 由 `sync-assets` 按需生成，不是 Skill 内置文件；`preflight`/`render` 必须显式或按默认位置找到它，并验证所有图片/视频已有模型写入的 `description`。
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

Manifest 默认写入工作区的 `soda_assets_manifest.json`；它记录相对路径、类型、推断类别、大小、修改时间和可探测的媒体元数据。路径、大小和修改时间未变化时不会重写；需要内容级变化检测时使用 `--checksum`。执行 Skill 的模型直接用 Read 工具查看原图和视频代表帧，为每条图片/视频补充中文 `description` 和源像素 `effective_region`。生成视频前，`preflight`/`render` 会阻止缺少 Manifest、asset_root 不一致、description 非空/effective_region 结构门禁未通过或时间轴引用未入库视觉素材的任务；description 是否为准确中文并覆盖完整语义仍由执行模型 Read 自检，不由确定性程序判断。

## 时间轴 JSON

结构模板：`references/timeline-template.json`。

- `time_mode=original`：时间点来自去气口前的原视频，使用 `removed_ranges` 重新映射；
- `time_mode=input`：默认新流程。时间点直接来自去气口后的当前输入视频；Whisper 字幕和全部素材共用这一 input 时钟，渲染时再统一除以 `speed`；
- `time_mode=output`：时间点已经是最终主片时间轴；
- `speed`：默认 `1.1`。通过 `render --speed <倍速>` 传入的值优先于时间线字段；
- 开场策略：固定从数字人口播第一帧直接开始。新时间轴不提供 `pre_roll_duration` 和 `hook`；旧时间轴中的同名字段会被忽略；
- `captions`：字幕入点、出点和文本；渲染时统一去除中英文标点；
- `--script-file`：调用方提供口播文本时，作为字幕文案最高优先级；`render`/`repair-captions` 必须先对当前输入执行 Whisper `--word_timestamps True`，把台词填入真实词级时间戳后生成修正版时间轴，修正版顶层固定为 `time_mode=input`，不覆盖原始时间轴；
- `materials`：只允许利益点物料；除路径、类型、布局和时间外，必须包含 `semantic_role=benefit_point` 与 `matched_benefit_text`；可用条目级 `time_mode`；连续段用 `sequence_id` 标识；命中特殊规则时还必须包含合法的 `special_match_rule`，实际素材内容由执行模型 Read 确认，不使用 SHA-256 门禁；
- `materials` 的时间区间使用半开语义 `[start,end)`；Whisper 流程中每个素材的有效 `time_mode` 必须为 `input`，`start/end` 直接复用字幕 input 边界；同一 `sequence_id` 内上一条 `end` 必须严格等于下一条 `start`，禁止重叠和 0.2–0.3s 过渡缓冲；有意返回数字人时使用不同 `sequence_id`。
- `motion_effects`：可选 Remotion 随机入场动效策略；缺省按 `mode=auto` 处理。字段和回退行为见 [motion-effects.md](motion-effects.md)；
- `visual_policy`：必须启用 `match_materials_only_for_benefit_points`、`seamless_material_handoffs`、`align_material_cuts_to_caption_boundaries`、禁止背景承托层、要求字幕细描边且无阴影、强制 logo/警示语最高层，并要求有效内容区域避让品牌保护区；
- `font/logo/tail`：字体、黑白 logo 和尾帧路径；`font.body_color` 默认白色，`font.brand_color` 默认品牌绿 `#3BFD42`；
- `font.caption_style`：独立 renderer 的 ASS 字幕字号、横纵缩放、字间距、描边、阴影、对齐和位置。新模板使用 `position_mode=center_offset`，以画布中心为原点、X 向右、Y 向上，`x=0,y=-500` 会映射到 1080×1920 画布的 `(540,1460)`；旧时间轴未提供该字段时继续使用原有边距定位；
- 渲染时会把正文字体和 SodaFont 一并复制到临时 libass 字体目录，确保品牌词不会因为字体文件位于不同目录而回退为普通字体；
- `logo.mode=auto`：透明 logo 画布与目标视频同宽高比时自动整画布叠加，否则使用定位模式；
- `logo.mode=full_canvas`：整张 logo 画布缩放到输出尺寸并在 `(0,0)` 叠加，忽略 `width/x/y/crop`；
- `logo.mode=placed`：使用 `width/x/y`，可选 `crop`，适用于紧边或比例不同的 logo；

`phone`、`full_alpha` 和 `cta_icon` 默认按完整源文件的源像素尺寸与原始比例直接叠加；`full_alpha` 默认 `x=0,y=0`，`cta_icon` 默认水平居中且 `y=650`，不再固定拉伸到输出画布或 `300×300`。`icon` 先按 Manifest `effective_region` 裁去空白画布，默认以有效内容源像素尺寸 `1:1` 叠加，不再执行 `scale=230:-1`；`x/y` 定位裁切后内容的左上角。所有布局都不绘制黑色背景板，也不在无碰撞时缩放。素材无需避让字幕区域。渲染器只用有效内容判断是否碰到 logo/警示语保护区；源画布、透明留白、纯色空白边距可以越界。有效内容碰撞时先移动，移动无法解决时才从源尺寸等比缩小到最大安全尺寸。Remotion 沿用相同规则：effective_region 只用于碰撞，只有 icon 裁切 effective_region，其他布局保留完整源文件。所有素材完成叠加后，先绘制去标点 ASS 字幕与 CTA，再叠加 logo，最后绘制警示语。

处理新视频时复制模板 JSON 到任务目录，填写实际素材路径、字幕和时间点，不要直接覆盖 Skill 内的结构模板。模板中的占位值必须全部替换后才能预检或渲染。

按默认流程先使用 `trim-pauses` 生成去气口中间文件，再对该文件执行 Whisper。修正版时间轴、字幕和所有素材统一使用 `time_mode=input`；执行模型直接把 Whisper 字幕 input `start/end` 写入素材，再传给 `render`。`time_mode=original` 仅保留给不使用 Whisper 新时间轴的旧兼容任务；Whisper 任务禁止字幕 input、素材 original 的混用方式。
