---
name: subtitle-motion-effects
description: Create, validate, render, or integrate animated subtitle effect layers for videos using a bundled Remotion renderer. Use when Codex needs 字幕动效, 落字入场, 从上往下出现的字幕, 逐字弹跳, 卡拉 OK 高亮, 字上方爱心/金币跳动, 抖音风字幕, transparent ProRes 4444 subtitle layers, ASS-to-JSON style planning, subtitle overlays for pre-roll/front-ad videos, or reusable subtitle motion assets for main video workflows.
---

# 字幕动效渲染

这个 skill 使用内置 Remotion 项目渲染字幕动效。默认输出透明 ProRes 4444 `.mov` 字幕层，再由前贴或正文工作流用 FFmpeg 叠加到主视频；需要人工预览时可以用 `composite` 模式直接输出 `.mp4`。

## 关键规则

- 输入统一用 JSON 时间线。ASS/SRT/VTT 可以作为上游来源，但进入本 skill 前建议转成 JSON。
- 警示语、免责声明默认不加动效。把 cue 标成 `role: "disclaimer"` / `"warning"` / `"legal"` 即可。
- 渲染出来的主字幕必须去掉标点符号。去标点只发生在最终显示层，不要提前改口播文本、时间戳、cue 顺序或分段。
- 主字幕只能出现一层。给前贴视频叠字幕动效前，必须先用 `aivideoeditor-pre-roll` 的 `--subtitle-render-mode motion` 生成不含普通主字幕的底片；不要把已经烧了普通主字幕的 `final.mp4` 当作 composite 输入。
- 前贴里提到 `汽水音乐` 或 `汽水` 时必须走 `branding.words`，并设置 SodaFont、品牌绿、黑色描边和更大的字号。
- Skill 已内置 `assets/fonts/SodaFont-Regular.otf` 和 `assets/fonts/FZLanTingHei-Medium.ttf`；默认模板会加载它们，外部流程也可以用 `fonts[]` 覆盖。
- 用户要的“字从上往下出现”使用 `drop_in` 或 `drop_bounce`，不要用 `stack_pop`。`stack_pop` 是叠影弹出，保留兼容但不是这类效果。
- 爱心跳字使用 `heart_jump`，现在会像参考短视频一样在每个字之间丝滑跳动，并带旋转和残影。
- 金币跳字使用 `coin_jump`，现在使用金色圆片高光样式。
- 歌词/高亮可用 `lyrics_gold`、`lyrics_cyan`、`lyrics_green`、`lyrics_pink`、`lyrics_orange`、`lyrics_violet`。

## 命令入口

```bash
SKILL_DIR="${CODEX_HOME:-$HOME/.codex}/skills/subtitle-motion-effects"
CLI="$SKILL_DIR/scripts/remotion/render.mjs"
```

在本仓库调试时：

```powershell
$SKILL_DIR="D:\linan\pro\aivideoeditor-backend\ai-cut-skills\skills\subtitle-motion-effects"
$CLI="$SKILL_DIR\scripts\remotion\render.mjs"
```

安装依赖：

```bash
node "$CLI" setup
```

查看内置效果：

```bash
node "$CLI" list-effects
```

查看样式和动效预设：

```bash
node "$CLI" list-presets
```

校验时间线：

```bash
node "$CLI" validate \
  --asset-root /absolute/path/workspace \
  --timeline-json /absolute/path/subtitle-timeline.json \
  --mode alpha
```

渲染透明字幕层：

```bash
node "$CLI" render \
  --asset-root /absolute/path/workspace \
  --timeline-json /absolute/path/subtitle-timeline.json \
  --output /absolute/path/subtitles.mov \
  --report /absolute/path/subtitles.motion.json \
  --mode alpha
```

渲染合成预览：

```bash
node "$CLI" render \
  --input /absolute/path/base.mp4 \
  --asset-root /absolute/path/workspace \
  --timeline-json /absolute/path/subtitle-timeline.json \
  --output /absolute/path/preview.mp4 \
  --report /absolute/path/preview.subtitle-motion.json \
  --mode composite
```

## 时间线要点

- `start`、`end` 使用秒，必须满足 `0 <= start < end`。
- `fonts[].path` 可以是绝对路径，也可以相对 `--asset-root`。
- `branding.words` 会把指定词自动拆成品牌字体 span，例如 `汽水音乐`、`汽水`。
- `position` 支持 `lower_center`、`middle_lower`、`center`、`top_center`、`bottom_center`、`custom`。
- 字幕默认 `maxWidth` 是画布宽度的 `86%`，避免触边。
- 优先传 TTS 的 `frontend.words` 或每条字幕的 `tokens` / `words`，报告里 `syncMode=timed_tokens` 才表示用了真实字词时间戳。

详细字段见 [effects.md](references/effects.md)。示例见 [timeline-template.json](references/timeline-template.json) 和 [preset-gallery.json](references/preset-gallery.json)。

## 前贴和正文接入

建议流程：

1. 普通字幕时间线生成后，转成字幕动效 JSON。
2. 如果是前贴，先用 `--subtitle-render-mode motion` 重新生成干净底片，保留右下角警示语但不烧普通主字幕。
3. 调用本 skill 渲染透明 alpha 字幕层。
4. 前贴或正文合成阶段把 alpha 字幕层 overlay 到主视频。
5. 图层顺序保持：主视频/素材 -> 字幕动效 -> logo -> 警示语。

最低可用集成只需要：画布、字体、字幕数组、`position`、`effectPreset` 和输出路径。

## 运行依赖

需要 Node.js、npm、Chrome/Chromium 或 Edge、FFmpeg/FFprobe。Remotion、React、renderer、bundler 版本由 skill 内 `package-lock.json` 固定。无需后端、数据库、Redis、剪映或项目 API。
