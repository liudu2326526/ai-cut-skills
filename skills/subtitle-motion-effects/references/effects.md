# 字幕动效字段

## 时间线结构

- `canvas`: 画布配置，常用 `width=1080`、`height=1920`、`fps=30`、`duration`。
- `fonts`: 字体文件，`family` 必须和字幕样式里的 `fontFamily` 一致，`path` 可以是绝对路径或相对 `--asset-root`。
- Skill 默认带了 `assets/fonts/FZLanTingHei-Medium.ttf` 和 `assets/fonts/SodaFont-Regular.otf`，可以直接在 `fonts[]` 里引用。
- `branding`: 品牌词规则。前贴里建议把 `汽水音乐`、`汽水` 放到 `branding.words`。
- `defaultStyle` / `defaultStylePreset`: 默认字幕样式。
- `defaultEffect` / `defaultEffectPreset`: 默认字幕动效。
- `frontend.words`: 可选的 TTS 字/词时间戳。传入后动效按真实口播节奏走。
- `subtitles`: 字幕时间线。

## 品牌词规则

字幕中提到 `汽水音乐` 或 `汽水` 时，建议使用：

```json
{
  "branding": {
    "words": ["汽水音乐", "汽水"],
    "style": {
      "fontFamily": "SodaFont",
      "fontSize": 76,
      "fontWeight": 900,
      "color": "#3BFD42",
      "strokeColor": "#071307",
      "strokeWidth": 4,
      "shadowBlur": 0
    },
    "scale": 1.15
  }
}
```

渲染器会在最后一步重新应用品牌样式，所以开启逐字弹跳、落字、歌词高亮、爱心/金币跳字时，品牌词也不会被普通 token 样式覆盖。

## 字幕字段

- `id`: 字幕 ID。
- `start` / `end`: 开始和结束时间，单位秒。
- `text`: 字幕全文。
- `position`: `lower_center`、`middle_lower`、`center`、`top_center`、`bottom_center`、`custom`。
- `x` / `y`: 仅 `custom` 生效。
- `maxWidth`: 最大宽度，默认画布宽度的 86%。
- `align`: `left`、`center`、`right`。
- `style` / `stylePreset`: 样式覆盖。
- `spans`: 局部样式；未提供时会按 `branding.words` 自动拆品牌词。
- `tokens` / `words`: 真实口播时间戳。做高亮、小图标跳字时优先传它。
- `role`: `disclaimer` / `warning` / `legal` 默认走 `plain`，不加动效。
- `effect` / `effectPreset`: 动效配置。

## 内置动效

- `plain`: 静态字幕。
- `fade_slide`: 淡入轻微上移。
- `pop_word`: 逐字/逐词弹跳。
- `drop_word`: 字从上往下落入字幕位置，适合用户给的那种短视频落字效果。
- `stack_pop`: 叠影弹出，保留兼容；不要用它冒充落字。
- `karaoke_highlight`: 类歌词逐字高亮。
- `bounce_badge`: 当前字上方小图标跳动。爱心会像参考视频一样在字与字之间连续滑跳，并保留旋转和残影；金币会用更精致的金色圆片。爱心旋转可用 `badgeSpinDegrees`、`badgeSpinDuration`、`badgeSpinWobble` 调整，跳跃高度可用 `badgeTravelHeight` 调整。
- `typewriter`: 打字机。
- `shake_emphasis`: 轻微抖动强调。

## 内置动效预设

- `drop_in`: 标准落字入场。
- `drop_bounce`: 弹性更强的旋转落字。
- `pop_bold`: 逐字弹跳。
- `heart_jump`: 单个爱心在每个字之间丝滑跳动，旋转并带残影。
- `coin_jump`: 字上方金币跳动。
- `spark_jump`: 字上方星光跳动。
- `lyrics_gold`: 金色歌词高亮。
- `lyrics_cyan`: 青色歌词高亮。
- `lyrics_green`: 绿色歌词高亮。
- `lyrics_pink`: 粉色歌词高亮。
- `lyrics_orange`: 橙色歌词高亮。
- `lyrics_violet`: 紫色歌词高亮。
- `notice_typewriter`: 通知类打字机。
- `glitch_shake`: 故障感轻抖。

## 内置样式预设

- `standard_white`: 标准白字黑边。
- `variety_yellow`: 综艺黄字黑边。
- `boxed_white`: 黑底白字。
- `blue_glow`: 蓝色荧光。
- `red_highlight`: 红色高亮。
- `cyan_fashion`: 时尚青色。
- `soda_green`: 汽水品牌绿。
- `pink_heart`: 爱心粉描边。
- `lyric_gold`: 金色歌词高亮。
- `lyric_cyan`: 青色歌词高亮。
- `lyric_green`: 绿色歌词高亮。
- `lyric_pink`: 粉色歌词高亮。
- `lyric_orange`: 橙色歌词高亮。
- `lyric_violet`: 紫色歌词高亮。

## 同步规则

动效同步优先级：

1. 字幕传了 `tokens` / `words`：按真实时间戳控制逐字高亮、爱心、金币和落字。
2. 没有 token：按字幕 `start/end` 均匀估算。

报告里的 `syncMode=timed_tokens` 表示用了真实时间戳；`uniform` 表示均匀兜底。
