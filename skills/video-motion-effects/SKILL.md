---
name: video-motion-effects
description: "Create, render, validate, or integrate reusable Remotion-based image entrance effects for mixed-cut video timelines. Use when Codex needs 动感缩小, 底部上冲回正, 透视翻转回正, 白闪拉伸回正, WebGL2 卷页翻入回正, mirrored page backs, transparent ProRes 4444 layers, reference-frame reproduction, or a Remotion effect preset without FFmpeg animation expressions or Motion Canvas."
---

# Remotion 视频动效

## 核心原则

使用 Skill 内置 Remotion 项目实现全部视觉动画。不要使用 FFmpeg 动效表达式、Motion Canvas 或其他动画引擎替代 Remotion。FFprobe 只用于读取媒体元数据和验收输出。

正式效果共五种：

- `dynamic_shrink`：第一动效，动感缩小；
- `bottom_rise`：第二动效，底部上冲回正；
- `perspective_settle`：第三动效，透视翻转回正 V3；
- `flash_stretch`：第四动效，白闪拉伸回正；
- `page_curl`：第五动效，WebGL2 卷页翻入回正，使用原图镜像背面。

前四种预设基于 `6473457bdeee21e3149b251fd2e19c2f.mov` 的 30fps 对应帧校准；`page_curl` 使用连续 WebGL2 网格并按事件最终布局等比映射。详细参数、默认时长和可配置字段见 [effects.md](references/effects.md)。

## 执行顺序

1. 确认画布、帧率、素材根目录、时间线和输出模式。
2. 复制 [timeline-template.json](references/timeline-template.json) 到任务目录并填写真实素材；不要修改 Skill 内模板。
3. 若依赖缺失，运行一次 `setup`。
4. 运行 `validate`，确认路径、时间、布局、预设和持续时间。
5. 运行 `render --dry-run` 检查标准化时间线和渲染计划。
6. 正式渲染 `composite` 成片或 `alpha` 透明动效层。
7. 使用 FFprobe 和开始/中间/稳定帧抽检输出。

## 命令入口

```bash
SKILL_DIR="${CODEX_HOME:-$HOME/.codex}/skills/video-motion-effects"
CLI="$SKILL_DIR/scripts/remotion/render.mjs"
```

安装固定版本依赖：

```bash
node "$CLI" setup
```

查看效果：

```bash
node "$CLI" list-effects
```

校验时间线：

```bash
node "$CLI" validate \
  --input /absolute/path/base.mp4 \
  --asset-root /absolute/path/assets \
  --timeline-json /absolute/path/timeline.json \
  --mode composite
```

渲染带主视频的成片：

```bash
node "$CLI" render \
  --input /absolute/path/base.mp4 \
  --asset-root /absolute/path/assets \
  --timeline-json /absolute/path/timeline.json \
  --output /absolute/path/output.mp4 \
  --report /absolute/path/output.motion.json \
  --mode composite
```

渲染透明动效层：

```bash
node "$CLI" render \
  --asset-root /absolute/path/assets \
  --timeline-json /absolute/path/timeline.json \
  --output /absolute/path/effects.mov \
  --report /absolute/path/effects.motion.json \
  --mode alpha
```

## 时间线约定

- `start`、`end` 和 `effect.duration` 均使用最终输出时间轴秒数。
- 当前只接受图片事件；输入图尽量使用紧边透明图，避免围绕整张透明画布中心缩放。稳定布局默认保持调用方指定的尺寸；接入汽水混剪时先通过平移避让 logo/警示语保护区，只有平移无法解决重叠时才允许有限等比缩小。
- `layout.width/height` 是最终稳定尺寸；`height` 省略时按源图比例计算。
- `layout.x/y` 是最终左上角，可使用数字或 `center`。
- `layout.origin_x/origin_y` 是缩放锚点，默认素材中心。
- 事件按 JSON 顺序从下到上叠加。
- `effect.type` 可使用英文 type 或中文别名；渲染前会统一归一化。
- `dynamic_shrink`、`perspective_settle` 使用 `samples`；`page_curl` 可设置 `back_texture_strength`，默认 `0.92`；其余效果不需要采样参数。入场阶段可以按效果改变视觉尺度，但最终 Alpha 层仍必须裁切在调用方的品牌保护区之外。
- `composite` 输出 H.264 4:2:0，并保留主视频音频。
- `alpha` 输出 ProRes 4444 Alpha，不包含音频；具体像素格式以当前 Remotion/FFmpeg build 的报告为准（常见为 `yuva444p10le` 或 `yuva444p12le`）。

## 验收边界

- `dynamic_shrink`：第 0 帧为大近景，第 10 帧稳定；主图保持不透明，拖影必须归一化且稳定后消失。
- `bottom_rise`：第 0 帧为空场，第 1–2 帧按参考透明度显形，第 15 帧稳定，不得改变素材尺寸。
- `perspective_settle`：保留 V3 第 2–7 帧右侧释放区和上宽下窄透视；拖影不得出现硬切交接。
- `flash_stretch`：第 0 帧必须是高曝光白闪和左右独立拖影，不得渲染成灰块；第 13 帧稳定。
- `page_curl`：使用 WebGL2 真网格；卷曲区域不得被素材原边界裁断，背面必须显示原图镜像，不得退化为灰色或白色填充；destination 必须透明，不得出现 Canvas 矩形接缝。
- Alpha 输出背景必须透明，边缘不得出现黑边或黑底。
- 最终报告必须记录原素材、标准化布局、效果 type、预设、持续时间、采样参数和输出媒体信息。

## 运行依赖

需要 Node.js、npm、支持 WebGL2 的 Chrome/Chromium 和 FFprobe。Remotion、React、renderer、bundler 与 `@vysmo/transitions` 使用 Skill 内 `package-lock.json` 固定版本。无需 Python、Motion Canvas、业务项目、数据库或 API。
