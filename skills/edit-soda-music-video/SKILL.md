---
name: edit-soda-music-video
description: Create, revise, or validate Soda Music portrait talking-head mixed-cut videos with a standalone Python and FFmpeg workflow plus optional randomly selected Remotion entrance effects from an installed video-motion-effects skill. Includes Read-based image/video material understanding and description-only semantic material matching performed by the executing model, Whisper tiny pause timing, caller-script subtitle repair, punctuation-free captions, speed remapping, logos, caller-supplied assets, compliance, BGM, end cards, export, and QA. Use for 汽水混剪、汽水音乐剪辑、素材内容理解、素材语义匹配、去气口、口播字幕校正、无标点字幕、口播加速、物料动效、随机入场特效、logo、素材清单、BGM、尾帧、渠道检查或自动化成片。
---

# 汽水音乐混剪成片

## 核心原则

保留原始视频、BGM 和素材包，只输出新文件。Skill 内不得保存或假设具体素材名称、文件名、绝对路径、固定时间码或样片脚本；只维护素材种类、输入契约和剪辑规则。所有任务素材必须由调用方提供。

字幕中的“汽水音乐”和“汽水”必须使用调用方提供的 SodaFont，并显示为品牌绿 `#3BFD42`；同一字幕中的其他文字立即恢复为调用方提供的方正兰亭和普通字幕颜色。字体规范属于品牌规则，可以写入 Skill；字体文件和路径仍由调用方提供。

字体 family 必须填写字体文件的真实内部名称。字幕字号、缩放、字间距、描边、阴影、对齐和位置统一通过时间轴的 `font.caption_style` 配置；新时间轴使用模板中的校准值，旧时间轴缺少该字段时保留兼容默认值。

成片不设置最低时长。实际长度由数字人口播、自然去气口、调用方指定倍速和官方尾帧共同决定；不得为了凑时长重复镜头、拉长静帧或补无关内容。渠道金额、禁词、歌曲审查和第三方授权规则仍然必须执行。

每次执行前完整阅读 [brand-rules.md](references/brand-rules.md)。准备素材时阅读 [asset-requirements.md](references/asset-requirements.md) 和 [asset-manifest.md](references/asset-manifest.md)，准备剪辑或渲染时阅读 [workflow.md](references/workflow.md)，调整运行环境、素材目录或时间轴配置时阅读 [standalone-runtime.md](references/standalone-runtime.md)。

需要理解或检索素材时，阅读 [asset-content-understanding.md](references/asset-content-understanding.md)。执行 Skill 的模型必须直接用 Read 工具查看图片和视频缩略帧，写入每个素材的 `description`，再根据口播语义匹配真实素材；不要调用素材理解/匹配脚本，也不要生成 `keywords`、`recommended_usage` 或向量索引。

去气口必须先于倍速处理。不要判断口播速度来决定是否加速：调用方未指定时统一使用 `1.1×`；调用方指定时以 `--speed` 为准。详细判定规则见 [pause-removal.md](references/pause-removal.md)。

口播识别固定使用本地 Whisper `tiny`。Whisper 只负责词级时间戳和停顿辅助，不作为最终字幕文案来源；调用方通过 `--script-file` 或 `--text` 传入口播时，口播文本是字幕校正的最高优先级，渲染前自动生成修正版时间轴替换识别错误。最终字幕统一去除中英文标点，仅保留必要的词组空格和换行。

透明 logo 的画布比例与目标视频一致时，优先把整张 logo 画布直接缩放到输出尺寸并在 `(0,0)` 叠加，不要裁剪透明留白或单独修改可见 logo 大小。只有紧边 logo 或比例不一致的素材才使用 `width/x/y/crop` 定位。

字幕和素材不得出现背景黑条、黑框或半透明黑色承托层。字幕保留 `2–3px` 黑色细描边，默认 `3px`，阴影固定为 `0`；字幕文本必须去除中英文标点，不能把逗号、顿号、句号等带入画面；警示语、开头钩子和 CTA 只使用纯文字。`phone` 素材必须等比直接叠加，禁止通过 `drawbox`、pad 或背景板补黑边。素材可以进入字幕区域，但不得进入左上 logo 保护区和底部警示语保护区；1080×1920 默认素材可用区为 `x=48..1032, y=320..1740`。素材默认保持时间轴指定的尺寸，先通过平移避让 logo/警示语保护区；只有平移仍无法避让时，才按可用区计算“刚好不遮挡品牌区域的最大尺寸”进行等比缩放，不设置固定缩放上限或下限。动效帧仍必须裁切在可用区内。图层顺序固定为主画面 → 素材/动效 → 字幕与 CTA → logo → 警示语：字幕位于素材上方，logo 位于素材、字幕和 CTA 上方，警示语为最终最高层。源视频若被预检识别出跨多帧稳定的固定黑边，必须更换或裁切素材后才能渲染。

成片必须从数字人口播第一帧直接开始，不生成模糊背景标题卡、预卷、开场动画或独立静帧。开头钩子只能通过数字人画面上的字幕或已审查物料表达。旧时间轴中的 `pre_roll_duration` 和 `hook` 字段仅兼容读取，渲染器必须忽略。

BGM 必须先按目标综合响度归一化，再做小范围后置微调。默认目标为 `-28 LUFS`，`--bgm-volume` 默认为 `1.0`，只作为归一化后的微调倍率；不得沿用旧的原始衰减值 `0.22`。人声继续归一化到 `-16 LUFS`，最终以人声清晰且 BGM 可感知但不盖住人声为准。

默认以 `motion_effects.mode=auto` 检测已安装的 `video-motion-effects`。可用时为合格图片物料随机选择 Remotion 入场效果；不可用或单个效果失败时回退静态叠加。随机选择必须可复现，详细规则见 [motion-effects.md](references/motion-effects.md)。

## 执行顺序

1. 确认工作区、素材根目录、BGM、时间轴 JSON、渠道类型、金币/歌单状态、歌曲审查结果和第三方授权；实际时长以数字人口播处理结果为准。
2. 运行素材清单同步；若检测到新增、删除或修改，读取并更新工作区 Manifest，否则复用已有清单。
3. 如果需要内容级素材匹配，执行模型在基础同步后直接用 Read 工具逐张查看新增、修改或缺少 description 的图片，并查看视频代表帧；将准确中文 description 写回 Manifest，再按口播语义选择真正匹配的素材。如果调用方提供 `--script-file` 口播，先使用口播修正时间轴字幕文本并去除标点；原始时间轴不覆盖，修正版时间轴和修复报告单独输出。随后运行预检，检查字幕 `2–3px` 黑色细描边、阴影为 `0`、无背景承托层、素材不进入 logo/警示语保护区、素材默认尺寸未被改变、素材先平移，必要时再缩放到不遮挡品牌区域的最大尺寸、字幕高于素材、logo 高于素材/字幕/CTA、警示语处于最终最高层，以及源素材无固定黑边；不要在素材或运行环境缺失时猜测路径。
4. 使用多组音量阈值交叉检测停顿；固定调用 Whisper `tiny` 增加逐词时间戳校验，但不得用 Whisper 结果覆盖调用方口播。
5. 结合语义、波形、呼吸、尾音、口型和动作人工确认范围，每处默认保留约 `0.16s`，不得整段删除。
6. 先输出去气口中间视频，再应用倍速。未指定时使用 `1.1×`，指定时使用调用方传入的倍速。
7. 校正字幕，优先使用调用方口播修正后的文本，按去气口和倍速后的时间轴匹配真实物料；最终字幕去除中英文标点，只保留必要的词组空格和换行。检测 `video-motion-effects` 并按稳定随机种子为合格图片选择入场效果。字幕使用 `2–3px` 黑色细描边且无阴影，不得带背景条；素材不受字幕安全区限制，但必须限制在 `visual_policy.material_safe_area` 内。素材先保持原尺寸并平移避让，只有确实碰到 logo/警示语保护区且无法平移解决时，才按可用区计算最大安全尺寸进行等比缩放。字幕和 CTA 在素材及动效上方绘制，logo 再叠加于字幕与 CTA 上方。第 0 秒直接显示数字人，开头 0–3 秒可叠加有效钩子字幕或物料，不得生成独立开场或黑屏。
8. 先运行规则校验，再渲染。校验失败时不要通过改参数绕过红线。
9. 使用调用方提供的官方 logo、规定警示语和官方尾帧视频。正片中 logo 必须位于素材、动效、字幕和 CTA 上方，警示语必须最后绘制为最高层；尾帧硬切进入，不叠加其他元素。
10. 先把 BGM 归一化到目标响度，再混入人声和轻提示音，完成人声、BGM、响度和手机扬声器复听。
11. 运行完整 QA，交付成片、封面、素材/时间轴报告、合规报告和技术验收报告。

## 命令入口

将 Skill 路径和运行时设为：

```bash
SKILL_DIR="${CODEX_HOME:-$HOME/.codex}/skills/edit-soda-music-video"
PY=python3
PIPE="$SKILL_DIR/scripts/soda_pipeline.py"
```

### 同步工作区素材清单

```bash
"$PY" "$PIPE" sync-assets \
  --workspace /absolute/path/workspace \
  --asset-root /absolute/path/assets
```

默认在工作区生成 `soda_assets_manifest.json`。首次运行创建清单；后续运行先比较素材指纹，未变化时返回 `status=unchanged` 且不重写文件，检测到新增、删除或修改时才更新清单。需要内容级校验时增加 `--checksum`；只想快速扫描文件而不调用 FFprobe 时增加 `--quick`。详细字段见 [asset-manifest.md](references/asset-manifest.md)。

素材内容理解和语义匹配不通过额外脚本执行。执行模型直接读取 Manifest、图片原图和视频代表帧，在 Manifest 素材记录中写入 `description`，然后阅读口播文案并将真实素材路径写入时间轴。详细操作见 [asset-content-understanding.md](references/asset-content-understanding.md)。

### 预检

```bash
"$PY" "$PIPE" preflight \
  --input /absolute/path/source.mov \
  --asset-root /absolute/path/assets \
  --bgm /absolute/path/background-music.mp3 \
  --timeline-json /absolute/path/timeline.json \
  --output-json /absolute/path/preflight.json
```

必须检查 `ok=true`。`--asset-root`、`--bgm` 和 `--timeline-json` 没有默认值，必须按任务显式传入。

可复制 `$SKILL_DIR/references/timeline-template.json` 到任务输出目录，填写调用方实际提供的路径、字幕、物料和时间点，再通过 `--timeline-json` 传入。模板只描述字段结构，不包含现有素材信息。

### 去气口

```bash
"$PY" "$PIPE" detect-pauses \
  --input /absolute/path/source.mov \
  --thresholds=-35dB,-30dB,-25dB \
  --min-silence 0.35 \
  --dynamic-min-silence 0.18 \
  --keep-pause 0.16 \
  --output-json /absolute/path/pause_candidates.json
```

默认调用本地 Whisper `tiny` 模型生成逐词时间戳；环境不可用时仍会输出多阈值候选并记录警告。需要跳过 Whisper 时使用 `--no-whisper`。正式流程保持 `tiny`，不要自行切换其他模型。

调用方提供口播后，使用 `repair-captions` 单独修正时间轴字幕；`render` 传入 `--script-file` 时会自动执行同样的修正，并在输出目录生成 `<成片名>_repaired_timeline.json` 和 `<成片名>_subtitle_repair.json`。修正只替换字幕文本，不改变原始入点、出点或素材时间。

```bash
"$PY" "$PIPE" repair-captions \
  --timeline-json /absolute/path/timeline.json \
  --script-file /absolute/path/spoken_script.txt \
  --output-timeline-json /absolute/path/timeline_repaired.json \
  --output-json /absolute/path/subtitle_repair.json
```

人工审核 `remove_ranges` 后再执行：

```bash
"$PY" "$PIPE" trim-pauses \
  --input /absolute/path/source.mov \
  --ranges-json /absolute/path/approved_ranges.json \
  --output /absolute/path/source_去气口.mp4 \
  --output-json /absolute/path/trim_report.json
```

严格阈值先检测 0.35 秒以上静音，较敏感阈值补充 0.18 秒以上停顿。只把多阈值相互印证，或音量检测与 Whisper 逐词间隔相互印证的区间列为稳定候选。每处保留范围必须在 `0.12–0.20s`，默认 `0.16s`。不得切掉呼吸、尾音、爆破音或造成跳口。

### 规则校验

校验示例：

```bash
"$PY" "$PIPE" validate-rules \
  --channel old-down \
  --video /absolute/path/edited.mp4 \
  --script-file /absolute/path/script.txt \
  --amount-yuan 25 \
  --has-playlist \
  --song-review-passed \
  --output-json /absolute/path/compliance.json
```

视频时长仅记录实际结果，不作为通过或失败条件。不要默认打开 `--allow-third-party` 或 `--song-review-passed`；必须有真实依据。

### 渲染

先用 `--dry-run` 查看 Skill 内置独立 renderer 的计划：

```bash
"$PY" "$PIPE" render \
  --input /absolute/path/source_去气口.mp4 \
  --asset-root /absolute/path/assets \
  --bgm /absolute/path/background-music.mp3 \
  --timeline-json /absolute/path/timeline.json \
  --output /absolute/path/finished.mp4 \
  --speed 1.1 \
  --channel old-down \
  --script-file /absolute/path/script.txt \
  --bgm-target-lufs -28 \
  --bgm-volume 1.0 \
  --compliance-report /absolute/path/compliance.json \
  --preflight-report /absolute/path/preflight.json \
  --qa-report /absolute/path/qa.json \
  --motion-effects auto \
  --motion-seed version-a \
  --dry-run
```

确认无误后移除 `--dry-run`。基础 renderer 依赖 Python 3 标准库、FFmpeg、FFprobe、输入视频、BGM、素材目录和时间轴；启用已安装的 `video-motion-effects` 时额外使用 Node、Chrome 和该 Skill 的 Remotion 依赖。`--bgm-target-lufs` 控制归一化目标，默认 `-28`；`--bgm-volume` 是归一化后的微调倍率，默认 `1.0`、允许范围 `0.5–1.5`。需要调整时优先每次改变目标响度约 `1–2 LUFS`；只有细微听感修正时才把微调倍率每次改变约 `0.03–0.05`，并重新运行完整响度与人声清晰度 QA。

`--speed` 在去气口之后应用，默认值为 `1.1`。不要根据口播快慢自行改回原速；只有调用方明确传入其他值时才覆盖默认值。字幕、物料和提示音必须同时按去气口范围与最终倍速重映射。

`--motion-effects` 可为 `auto/off/required`；`--motion-seed` 用于生成可复现的随机动效版本。省略种子时，渲染器根据时间线、输出路径和物料信息生成稳定种子。

`render` 收到 `--script-file` 或 `--text` 时会把口播作为字幕权威文本，按原有字幕时间范围顺序匹配并修正文字，自动去除标点，同时保留原时间轴文件。可通过 `--repaired-timeline-json` 和 `--subtitle-repair-report` 指定修正版时间轴与修复报告路径。

素材尺寸策略写在时间线的 `visual_policy` 中：`preserve_material_size=true`、`reposition_before_scale=true`。这两个默认值要求先平移；缩放只在必要时使用，并计算为不进入 logo/警示语保护区的最大等比尺寸，不设置固定缩放阈值，也不能把素材统一压缩到安全区中心。

成片时长跟随处理后的数字人口播，不设置最低值；不要重复镜头、拉长静帧或添加无关内容补时长。

### 单独验收

```bash
"$PY" "$PIPE" qa \
  --input /absolute/path/finished.mp4 \
  --output-json /absolute/path/qa.json
```

只有排查环境时才使用 `--quick`；最终交付必须执行完整解码和响度扫描。QA 记录实际时长，但不按时长判定失败。

## 渲染与内容边界

- 使用 Skill 内置 `standalone_renderer.py` 生成 ASS 字幕、读取媒体信息，并在可用时调用 `video-motion-effects` 生成临时 Remotion Alpha 入场片段。视觉渲染顺序固定为主画面 → 静态或动效物料 → 字幕与 CTA → logo → 警示语；logo 和警示语是不可被遮挡的最高品牌层，随后再完成 BGM 混音、封面和 JSON 报告。
- 默认输出 1080×1920、30fps、H.264 High/yuv420p、AAC 192kbps/44.1kHz、faststart。
- 人声参考 -16 LUFS、LRA≤7、True Peak≤-1.5 dBTP；BGM 默认归一化到 -28 LUFS；成片综合响度建议 -16±1 LUFS。
- QA 必须确认字幕、警示语和所有素材外围不存在背景黑条、黑框或半透明黑色承托层；字幕文本与调用方口播一致且不含中英文标点；素材可见边界和整个入场动效都不得进入 logo/警示语保护区；素材没有无必要的尺寸变化，确需避让时先平移，再缩放到不遮挡品牌区域的最大尺寸；字幕黑色细描边为 `2–3px`、阴影为 `0`，字幕始终位于素材上方，logo 位于素材/字幕/CTA 上方，警示语位于最终最高层；源素材固定黑边必须在预检阶段拦截。
- 缺少素材时可用明确标注 `DEMO/待替换` 的文字卡临时占位；正式交付前必须替换或获得书面确认。
- 歌单、金额、第三方名称和“赚钱”类利益点必须按渠道分别校验，不能把一次授权扩展到其他任务。
- 素材文件名或目录名中的内部标签不得直接当作投放文案；最终画面、字幕和旁白仍须单独执行禁词扫描。

## 交付说明

最终回复列出：输入文件、渠道、去气口范围、速度、素材根目录、BGM、BGM 目标 LUFS 和后置微调倍率、实际时长、输出视频、封面、合规报告、预检报告和 QA 结果。
