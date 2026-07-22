# 独立运行环境

## 依赖

- Python 3.10 或更高版本，仅使用标准库；
- `ffmpeg`，需要 `libx264`、`aac`、`subtitles/libass`、`loudnorm` 和 `ebur128`；
- `ffprobe`；
- 本地 `whisper` CLI 和已缓存 `tiny` 模型：无调用方台词时不可用可退化为多阈值音量检测；提供台词时必须可用并输出 `--word_timestamps True` 的词级 JSON，否则渲染失败；
- 输入视频、BGM、素材目录和时间轴 JSON。
- 必需安装 `manage-visual-asset-library`；它负责生成和校验工作区 `visual_assets_manifest.json`。汽水 `preflight`/`render` 只消费 Manifest 并执行最低契约门禁。
- 可选 `${CODEX_HOME:-$HOME/.codex}/skills/video-motion-effects`；启用时额外需要 Node.js、Chrome/Chromium 及该 Skill 已安装的 Remotion 依赖。

不需要任何业务项目、虚拟环境、数据库、API 服务或 Python 第三方包。

## BGM 响度

- `--bgm-target-lufs`：BGM 在混音前的目标综合响度，默认 `-28 LUFS`，允许范围 `-40` 到 `-18 LUFS`；
- `--bgm-volume`：完成 LUFS 归一化后的微调倍率，默认 `1.0`，允许范围 `0.5–1.5`；
- 旧流程中的 `--bgm-volume 0.22` 会被拒绝，因为它会在归一化后再次大幅衰减 BGM；
- 混音顺序为：裁切/循环 BGM → `loudnorm` 到目标 LUFS → 微调倍率 → 淡入淡出 → 与人声和提示音混合 → limiter 防峰值溢出。

## 素材输入

Skill 不保存默认素材目录、BGM 路径或现有素材文件名。视觉 Manifest 只收录图片和视频；用户未指定 BGM 时，执行模型从当前任务目录或调用方提供的音频候选中自行选择真实、可解码、适合口播且已纳入投放范围的文件，不向用户追问；没有真实候选才视为缺少必需素材。CLI 仍显式传入模型选定的路径：

```bash
python3 scripts/soda_pipeline.py preflight \
  --asset-root /absolute/path/assets \
  --bgm /absolute/path/background-music.mp3 \
  --timeline-json /absolute/path/timeline.json
```

时间轴 JSON 中的素材路径默认相对 `--asset-root`；也可以使用绝对路径。

`render` 和 `validate-rules` 的 `--channel` 同样保持必填，用于让合规报告记录已经确定的正式渠道。用户未指定时由执行模型根据口播、金额、金币/提现、歌单和素材线索从 `old-down`、`new-high-mid`、`free-listen`、`coin-non-down` 中自主选择；正式交付不使用 `general`。CLI 仍显式传入模型选定的 `--channel` 和 `--bgm`，这里的必填含义是“执行前必须得到确定值”，不是“必须询问用户”。

正式素材同步使用通用 Skill：

```bash
python3 "${CODEX_HOME:-$HOME/.codex}/skills/manage-visual-asset-library/scripts/asset_manifest.py" \
  --workspace /absolute/path/workspace \
  --asset-root /absolute/path/assets
```

Manifest 默认写入工作区的 `visual_assets_manifest.json`，只记录图片和视频。Read 理解、description 质量、effective_region 和普通候选输出全部遵循通用 Skill。汽水 `sync-assets` 仅是兼容转发入口；旧 `soda_assets_manifest.json` 仍可通过 `--asset-manifest` 显式传入。生成视频前，`preflight`/`render` 会阻止 Manifest 缺失、asset_root 不一致、description/effective_region 门禁失败或时间轴引用未入库视觉素材的任务。

## 时间轴 JSON

结构模板：`references/timeline-template.json`。

- `time_mode=original`：时间点来自去气口前的原视频，使用 `removed_ranges` 重新映射；
- `time_mode=input`：默认新流程。时间点直接来自去气口后的当前输入视频；Whisper 字幕和全部素材共用这一 input 时钟，渲染时再统一除以 `speed`；
- `time_mode=output`：时间点已经是最终主片时间轴；
- `speed`：默认 `1.1`。通过 `render --speed <倍速>` 传入的值优先于时间线字段；
- 开场策略：固定从数字人口播第一帧直接开始。新时间轴不提供 `pre_roll_duration` 和 `hook`；旧时间轴中的同名字段会被忽略；
- `captions`：字幕入点、出点和文本；渲染时去除普通中英文标点，但保留并规范化数字内部小数点；过宽口播应先在 Whisper 对齐阶段按实际文字时间拆成多个 caption；
- `--script-file`：调用方提供口播文本时，作为字幕文案最高优先级；`render`/`repair-captions` 必须先对当前输入执行 Whisper `--word_timestamps True`，把台词填入真实词级时间戳后生成修正版时间轴，修正版顶层固定为 `time_mode=input`，不覆盖原始时间轴；
- `materials`：只允许利益点物料；除路径、类型、布局和时间外，必须包含 `semantic_role=benefit_point` 与 `matched_benefit_text`；可用条目级 `time_mode`；连续段用 `sequence_id` 标识；命中特殊规则时还必须包含合法的 `special_match_rule`，实际素材内容由执行模型 Read 确认，不使用 SHA-256 门禁；
- `materials` 的时间区间使用半开语义 `[start,end)`；Whisper 流程中每个素材的有效 `time_mode` 必须为 `input`，`start/end` 直接复用字幕 input 边界；同一 `sequence_id` 内上一条 `end` 必须严格等于下一条 `start`，禁止重叠和 0.2–0.3s 过渡缓冲；有意返回数字人时使用不同 `sequence_id`。
- `motion_effects`：可选 Remotion 随机入场动效策略；缺省按 `mode=auto` 处理。字段和回退行为见 [motion-effects.md](motion-effects.md)；
- `visual_policy`：必须启用 `match_materials_only_for_benefit_points`、`seamless_material_handoffs`、`align_material_cuts_to_caption_boundaries`、禁止背景承托层、要求字幕细描边且无阴影、强制 logo/警示语最高层，并要求有效内容区域避让品牌保护区；
- `font/logo/tail`：字体、黑白 logo 和尾帧路径；`font.body_color` 默认白色，`font.brand_color` 默认品牌绿 `#3BFD42`；
- `font.caption_style`：独立 renderer 的 ASS 字幕字号、横纵缩放、字间距、描边、阴影、对齐、位置和显式换行策略。新模板使用 `position_mode=center_offset`，以画布中心为原点、X 向右、Y 向上，`x=0,y=-500` 会映射到 1080×1920 画布的 `(540,1460)`；`wrap_mode=balanced_explicit`、`minimum_horizontal_margin=96`、`width_safety_ratio=0.92`、`preferred_max_lines=2`、`max_lines=3`。渲染器在添加 ASS 品牌字体标签前先写入显式 `\\N`，不依赖 libass 自动换行；旧时间轴缺少换行字段时使用同一安全默认值；
- 渲染时会把正文字体和 SodaFont 一并复制到临时 libass 字体目录，确保品牌词不会因为字体文件位于不同目录而回退为普通字体；
- `logo.mode=auto`：透明 logo 画布与目标视频同宽高比时自动整画布叠加，否则使用定位模式；
- `logo.mode=full_canvas`：整张 logo 画布缩放到输出尺寸并在 `(0,0)` 叠加，忽略 `width/x/y/crop`；
- `logo.mode=placed`：使用 `width/x/y`，可选 `crop`，适用于紧边或比例不同的 logo；

`phone`、`full_alpha` 和 `cta_icon` 默认按完整源文件的源像素尺寸与原始比例直接叠加；`full_alpha` 默认 `x=0,y=0`，`cta_icon` 默认水平居中且 `y=650`，不再固定拉伸到输出画布或 `300×300`。`icon` 先按 Manifest `effective_region` 裁去空白画布，默认以有效内容源像素尺寸 `1:1` 叠加，不再执行 `scale=230:-1`。`x` 定位裁切后内容的左边；未填 `y` 时，渲染器使用与 ASS 相同的最终显式换行结果计算字幕块上边界，将图标底边放在其上方 `72px`，并随字幕行数上移；显式 `y` 优先于自动位置。解析后位置记录在 `resolved_placement`，静态 FFmpeg 与 Remotion 动效共用该坐标，不对图标做缩放。所有布局都不绘制黑色背景板，也不在无碰撞时缩放。素材无需避让字幕区域。渲染器只用有效内容判断是否碰到 logo/警示语保护区；源画布、透明留白、纯色空白边距可以越界。有效内容碰撞时先移动，移动无法解决时才从源尺寸等比缩小到最大安全尺寸。Remotion 沿用相同规则：effective_region 只用于碰撞，只有 icon 裁切 effective_region，其他布局保留完整源文件。所有素材完成叠加后，先绘制已移除普通标点但保留数字内部小数点的 ASS 字幕与 CTA，再叠加 logo，最后绘制警示语。

`preflight` 和 `render` 使用同一字幕布局器。报告中的 `caption_layout` 必须记录标准化文本、最终分行、`line_count`、每行估算宽度和 `available_width`；超过三行或任一行越过安全宽度时直接失败。最终 QA 仍需抽取最长字幕帧复核真实字体渲染结果。

处理新视频时复制模板 JSON 到任务目录，填写实际素材路径、字幕和时间点，不要直接覆盖 Skill 内的结构模板。模板中的占位值必须全部替换后才能预检或渲染。

按默认流程先使用 `trim-pauses` 生成去气口中间文件，再对该文件执行 Whisper。修正版时间轴、字幕和所有素材统一使用 `time_mode=input`；执行模型直接把 Whisper 字幕 input `start/end` 写入素材，再传给 `render`。`time_mode=original` 仅保留给不使用 Whisper 新时间轴的旧兼容任务；Whisper 任务禁止字幕 input、素材 original 的混用方式。
