# 素材种类与输入要求

Skill 默认只定义素材种类和输入契约，不保存具体素材名称、文件名、目录、绝对路径、固定时间码或历史样片映射。唯一例外是 [special-material-matches.md](special-material-matches.md) 中经用户明确批准的特殊规则；这里只记录参考相对路径和画面识别条件，不记录文件哈希，也不内置素材文件。

运行时可用 `sync-assets` 将调用方素材目录同步到工作区 Manifest；Manifest 只属于当前工作区，不是 Skill 内置资源。

## 必需素材

| 种类 | 用途 | 建议格式 | 最低要求 |
| --- | --- | --- | --- |
| 主口播视频 | 主画面与原始人声 | MOV/MP4 | 画面和音频可正常解码 |
| BGM | 背景音乐 | MP3/WAV/M4A | 已确认版权和投放范围，可循环 |
| 方正兰亭 | 除“汽水音乐”“汽水”外的普通字幕、警示语和标题 | TTF/OTF | 调用方提供文件及准确的字体内部名称，FFmpeg/libass 可加载 |
| SodaFont | 字幕中的“汽水音乐”“汽水” | TTF/OTF | 调用方提供文件及准确的字体内部名称，并使用品牌绿 `#3BFD42` |
| 浅色 logo | 深色背景使用 | 透明 PNG | 支持紧边 logo 或已排好位置的全画布 logo |
| 深色 logo | 浅色背景使用 | 透明 PNG | 支持紧边 logo 或已排好位置的全画布 logo |
| 官方尾帧 | 结尾品牌画面 | MP4/MOV | 竖屏优先，时长和声音已确认 |

## 仅在利益点台词中选用的素材

| 种类 | 适用语义 | 推荐布局 |
| --- | --- | --- |
| 产品功能操作录屏 | 搜索、播放、设置、模式、歌单等真实操作；保持原始比例直接叠加，不得自动补黑边 | `phone` |
| 使用场景图或图标 | 通勤、驾驶、居家等场景表达 | `icon` 或 `full_alpha` |
| 合规利益点图 | 金币、提现、会员、免费听等已获准利益点 | `full_alpha` |
| 功能说明图 | 曲库、离线、音质等功能说明 | `full_alpha` 或 `phone` |
| CTA 视觉元素 | 下载、体验等行动引导 | `cta_icon` |
| 补充 B-roll | 遮盖跳口或增强节奏 | `phone` 或 `full_alpha` |

先判断台词是否属于利益点，再选择脚本实际需要且已完成审查的种类。利益点选材必须先检查特殊规则；命中时优先使用参考素材，或使用 Read 确认核心画面完整的轻度变体，未命中才做普通语义匹配。非利益点不得匹配或插入普通素材；logo、警示语和官方尾帧不受此限制。没有对应利益点语义时不要为了填满画面强行添加。

需要自动匹配时，执行 Skill 的模型直接用 Read 工具查看图片原图和视频缩略帧，为每个素材补充 `description` 和源像素 `effective_region`。description 必须具体记录适用的页面类型、布局和数量、关键文字数字、动作或状态以及可表达语义；UI、金额和权益素材必须枚举清晰可见的关键档位与分组，不能用“小额金额”或“多个选项”代替。只针对利益点检索 description；不调用素材理解/匹配脚本，不生成或保存 `keywords`、`recommended_usage` 或向量。文件类型、布局、黑边、渠道和品牌安全区仍由规则校验。

所有素材不得在渲染器中生成黑条、黑框或半透明黑色承托层。视频素材若自身带有跨多帧稳定的固定黑边，预检必须报错；自然画面中的黑色内容不按黑边处理。

素材不必避让字幕安全区，可以覆盖到字幕所在空间；但素材的 `effective_region` 不得进入左上 logo 保护区或底部警示语保护区。渲染器不得用源文件完整画布判断遮挡：透明留白、纯色空白边距和无内容区域越界不触发移动或缩放。`icon` 布局先按 effective_region 裁去空白画布，默认保持有效内容源像素尺寸，不执行固定宽度缩放；时间轴 `x/y` 表示裁切后有效内容的左上角。只有有效内容真实遮挡时才先移动；移动仍无法避让时，才按有效内容计算最大安全缩放比例。Remotion 动效按 effective_region 裁切实际内容后检查。所有素材叠加完成后绘制字幕与 CTA，再叠加 logo，最后绘制警示语。

时间线的 `visual_policy` 默认使用以下素材尺寸策略：

```json
{
  "match_materials_only_for_benefit_points": true,
  "preserve_material_size": true,
  "reposition_before_scale": true,
  "seamless_material_handoffs": true,
  "align_material_cuts_to_caption_boundaries": true
}
```

安装 `video-motion-effects` 后，默认只从 `kind=image` 且布局为 `full_alpha`、`phone` 或 `cta_icon` 的物料中随机选择入场动效。`icon` 和视频物料默认保持原叠加方式；需要改变候选范围时通过时间线 `motion_effects.eligible_layouts` 明确配置。

## Logo 画布模式

- `auto`：默认模式。透明 PNG 的画布比例与目标视频一致时自动使用 `full_canvas`，否则使用 `placed`。
- `full_canvas`：素材画布已经包含最终位置和大小。整张图缩放到输出分辨率并在 `(0,0)` 叠加，忽略 `width/x/y/crop`。
- `placed`：适用于紧边 logo 或比例不一致的画布，使用 `width/x/y` 定位；只有明确需要时才设置 `crop`。

全画布模式允许透明留白，因为留白属于品牌排版的一部分，不能按普通紧边 logo 规则删除。

## 时间轴条目

每个物料条目至少包含：

```json
{
  "name": "<任务内可读名称>",
  "category": "<素材种类>",
  "path": "<相对 asset-root 的路径或绝对路径>",
  "kind": "image 或 video",
  "layout": "phone、icon、full_alpha 或 cta_icon",
  "semantic_role": "benefit_point",
  "matched_benefit_text": "<触发该素材的利益点台词原文>",
  "sequence_id": "benefit-01",
  "start": 0.0,
  "end": 1.0
}
```

命中特殊规则时，额外加入对应规则 ID，例如：

```json
{
  "special_match_rule": "withdraw_0_3"
}
```

`special_match_rule` 对普通语义匹配素材必须省略。只要填写该字段，`preflight` 和 `render` 就会校验规则 ID 是否已定义，但不会校验文件哈希。执行模型仍必须 Read 实际素材，并确认画面满足对应特殊规则；不允许为了绕过校验使用未知规则 ID。

`start` 和 `end` 必须来自当前任务时间轴。不要把其他视频的时间码、素材路径或文件名写回 Skill；已批准的特殊规则只按专用引用文件维护。素材使用半开区间 `[start,end)`。同一连续素材段的相邻条目必须严格 `previous.end == next.start`，不允许重叠或 0.2–0.3 秒过渡缓冲；只有有意返回数字人才切换 `sequence_id`。所有素材起止边界和切换点都必须对齐映射后字幕边界，内部衔接点对齐下一条字幕的 `start`。

`effective_region` 保存在 Manifest 中，`render` 会根据素材真实路径自动加载并映射到画布；不要在时间轴里凭感觉重新填写另一套区域。
