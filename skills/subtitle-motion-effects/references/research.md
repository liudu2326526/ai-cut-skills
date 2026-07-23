# 开源方案调研

## 结论

字幕动效建议走“字幕 JSON -> Web/Remotion 动画 -> 透明视频层 -> FFmpeg 叠加”。它兼顾可扩展、可预览、可复用和后续可视化编辑，适合前贴和正文两个工作流。

## 参考方案

### 剪映草稿 / Web-to-Video

`jianying-editor-skill` 的方向是自动生成剪映草稿，并把 HTML/JavaScript/Canvas/SVG 网页动效录成视频素材再导入剪映。优点是贴近剪映生态，缺点是依赖桌面剪映版本、草稿目录和自动导出环境，不适合作为后端或无项目用户的稳定字幕渲染内核。

### Remotion

Remotion 官方支持字幕能力和透明视频输出，社区也有 TikTok-style captions 模板。它的优势是字幕就是 React/CSS 组件，逐字弹跳、卡拉 OK 高亮、上方小标移动都能逐帧计算，并且能直接输出透明 ProRes 4444 或 WebM Alpha。

### PupCaps / CSS 字幕

PupCaps 这类项目说明了另一路线：从 SRT 解析字幕，用 CSS 做 Karaoke-style word-by-word highlighting，再调用视频工具生成结果。它证明了“Web 字幕样式 + 视频输出”可行，但我们的业务更需要 JSON 时间线、品牌字体 span 和多工作流集成，所以保留思路，不直接绑定它的 SRT 格式。

### ASS / libass

ASS 适合传统字幕样式、淡入淡出、移动和基础 karaoke tag。缺点是表达自研动效不直观，难以做可视化编辑，也不适合“字上方有小元素逐字跳动”这种复杂元素绑定。可以作为导入来源，但不建议作为最终动效数据结构。

## 设计取舍

- 使用 JSON 而不是 ASS 作为核心协议：方便表达 spans、品牌词、动画数组和后续编辑器。
- 使用 Remotion 而不是纯 FFmpeg 表达式：复杂动画更好写，调试更接近前端。
- 默认输出 Alpha 层而不是直接烧录：前贴和正文可以决定图层顺序，logo/警示语还能保持最高层。
- 保留 composite 预览：方便 AI IDE 或人工快速看效果。
