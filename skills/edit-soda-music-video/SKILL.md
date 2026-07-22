---
name: edit-soda-music-video
description: Create, revise, or validate Soda Music portrait talking-head mixed-cut videos that consume a manifest and semantic candidates from manage-visual-asset-library, while retaining Soda-only benefit-point selection, approved special-material overrides, model-semantic caption segmentation with a style-derived character budget, direct Whisper input-time caption/material alignment, screen-safe balanced caption wrapping, seamless half-open handoffs, brand-safe layout, optional Remotion effects, pause removal, speed remapping, compliance, BGM, end cards, export, and QA. Use for 汽水混剪、汽水音乐剪辑、利益点选材、Whisper input时间对齐、字幕语义切分、字幕超出画面、中文字幕自动换行、素材无缝衔接、字幕切换点对齐、特殊素材匹配、满三毛提现、小数金额字幕、去气口、Whisper词级字幕、口播字幕校正、无标点字幕、口播加速、物料动效、logo、BGM、尾帧、渠道检查或自动化成片。
---

# 汽水音乐混剪成片

## 核心原则

**REQUIRED SUB-SKILL:** Use manage-visual-asset-library

所有图片/视频的扫描、Read 内容理解、`description`、`effective_region`、完整性校验和普通语义候选检索都由该通用 Skill 完成。本 Skill 只消费 `visual_assets_manifest.json` 与 `asset_candidates.json`，并负责汽水业务决策、最终选材、时间轴和渲染。

保留原始视频、BGM 和素材包，只输出新文件。除 [special-material-matches.md](references/special-material-matches.md) 中由用户明确批准的特殊匹配外，Skill 内不得保存或假设具体素材名称、文件名、绝对路径、固定时间码或样片脚本；只维护素材种类、输入契约和剪辑规则。特殊匹配只保存参考相对路径、画面识别条件和触发规则，不保存文件哈希，也不能把素材文件复制进 Skill。所有任务视觉素材仍必须由调用方提供并进入当前工作区 Manifest。

字幕中的“汽水音乐”和“汽水”必须使用调用方提供的 SodaFont，并显示为品牌绿 `#3BFD42`；同一字幕中的其他文字立即恢复为调用方提供的方正兰亭和普通字幕颜色。字体规范属于品牌规则，可以写入 Skill；字体文件和路径仍由调用方提供。

字体 family 必须填写字体文件的真实内部名称，且只能是单一 ASS font family，不能写逗号分隔的 fallback 列表或任何 ASS 控制字符；例如填写 `FZLanTingHeiS-R-GB`，不要填写 `FZLanTingHeiS-R-GB,方正兰亭黑简体`。字幕字号、缩放、字间距、描边、阴影、对齐和位置统一通过时间轴的 `font.caption_style` 配置；新时间轴使用模板中的校准值，旧时间轴缺少该字段时保留兼容默认值。

成片不设置最低时长。实际长度由数字人口播、自然去气口、调用方指定倍速和官方尾帧共同决定；不得为了凑时长重复镜头、拉长静帧或补无关内容。渠道金额、禁词、歌曲审查和第三方授权规则仍然必须执行。

每次执行前完整阅读 [brand-rules.md](references/brand-rules.md)。准备汽水时间轴物料时阅读 [asset-requirements.md](references/asset-requirements.md)，准备剪辑或渲染时阅读 [workflow.md](references/workflow.md)，调整运行环境、素材目录或时间轴配置时阅读 [standalone-runtime.md](references/standalone-runtime.md)。

开始选材前必须阅读 [special-material-matches.md](references/special-material-matches.md)。先把口播分为利益点与非利益点，只有明确利益点允许匹配普通素材；对利益点先检查特殊匹配，命中时优先使用参考素材或满足画面条件的轻度变体，未命中才把利益点文本交给 `manage-visual-asset-library` 输出候选和理由。本 Skill 根据汽水合规、布局和连续性决定是否采用，不能把候选第一名自动视为最终素材。寒暄、过渡、情绪铺垫、单独 CTA、免责声明等非利益点保持数字人主画面。

去气口必须先于倍速处理。不要判断口播速度来决定是否加速：调用方未指定时统一使用 `1.1×`；调用方指定时以 `--speed` 为准。详细判定规则见 [pause-removal.md](references/pause-removal.md)。

对去气口后的当前输入执行 Whisper 后，时间轴统一改用 `time_mode=input`。所有字幕和素材都必须使用该 input 时钟：素材 `start/end` 直接复用 Whisper 实际识别字幕的 input 边界，不先扣减 `removed_ranges`，不先除以倍速，也不得混用 `original` 或 `output`。预检通过后，渲染器再对字幕和素材统一除以 `speed`。

素材时间区间统一使用半开语义 `[start,end)`，不得在相邻展示素材之间预留 `0.2–0.3s` 或任何其他“过渡缓冲”。同一连续素材段内，上一条 `end` 必须与下一条 `start` 在 Whisper input 时间轴上严格相等，切换点必须等于下一条字幕的 input `start`。多个连续利益点段使用不同 `sequence_id`；只有 `sequence_id` 发生变化时，才允许中间留出明确的数字人无素材段。字幕经 Whisper 重新定时后，必须以新字幕 input 边界重算 `materials[]`，不得沿用旧的素材时间。

口播识别固定使用本地 Whisper `tiny`。只要调用方提供 `--script-file` 或 `--text`，就必须先对**实际传给 render/repair-captions 的输入视频**执行 `whisper --word_timestamps True`，取得 Whisper 的真实词级时间戳；再把调用方口播台词按顺序填入这些时间槽，不能继续沿用原时间轴中可能错误的字幕入点/出点，也不能因为有台词就跳过 Whisper。台词文本是最终字幕文案来源，Whisper 文本只用于时间定位。映射前先运行 `caption-budget`，根据当前画布与 `font.caption_style` 只计算一次本任务的单行字数上限；执行模型只在原台词中插入换行，按动作、结果、条件、转折、因果或并列意群完成语义分段。每一行对应一个依次展示的 caption event，脚本不得再按字符宽度自动平均切分。语义行超过动态上限时必须先重新分段；不得拆开动宾结构、否定结构、品牌词、小数金额、数量单位或英文单词。最终字幕去除普通中英文标点，但必须保留数字内部小数点并统一为半角 `.`。即使 Whisper 把 `0.3` 输出为 `0.3`、`0`/`.`/`3` 或 `0.`/`3`，也不得在小数点处分成两个 caption。

透明 logo 的画布比例与目标视频一致时，优先把整张 logo 画布直接缩放到输出尺寸并在 `(0,0)` 叠加，不要裁剪透明留白或单独修改可见 logo 大小。只有紧边 logo 或比例不一致的素材才使用 `width/x/y/crop` 定位。

字幕和素材不得出现背景黑条、黑框或半透明黑色承托层。字幕保留 `2–3px` 黑色细描边，默认 `3px`，阴影固定为 `0`；字幕文本去除逗号、顿号、句号等普通标点，但 `0.3`、`0.30`、`8.72` 等数值中的数字内部小数点必须保留。新时间轴使用 1080 画布左右至少 `96px` 安全边距和 `0.92` 宽度余量；渲染前必须按中文、英文、数字与品牌字体的加权宽度显式均衡换行，优先一至两行、最多三行，不得依赖 ASS 自动换行。换行不得拆分“汽水音乐”、数字小数、金额或英文单词；三行仍无法放入安全宽度时预检必须失败，由执行模型按照本任务动态字数上限重新做语义分行，再映射 Whisper 词级时间，禁止自动缩小字号或脚本等宽拆句。警示语、开头钩子和 CTA 只使用纯文字。`phone`、`full_alpha` 和 `cta_icon` 默认保持原始比例和源像素尺寸直接叠加，禁止使用 `650×1050`、`300×300`、整画布拉伸或其他固定包围框做默认标准化；`icon` 只裁掉 effective_region 之外的空白画布，并按裁后有效内容源像素尺寸 `1:1` 叠加。`icon` 未显式填写 `y` 时，底边默认跟随该时段**最终显式换行后**的字幕上边界并保留 `72px` 间距，字幕换行时图标同步上移；显式 `y` 始终优先。这一规则只改坐标，不改图标尺寸，静态渲染与动效共用同一解析后坐标。所有普通素材都禁止通过 `drawbox`、pad 或背景板补黑边。素材可以进入字幕区域，但其**有效内容区域**不得进入左上 logo 保护区和底部警示语保护区；1080×1920 默认素材可用区为 `x=48..1032, y=320..1740`。遮挡判断只看 Manifest 的 `effective_region`，透明留白、纯色空白边距或大画布中的无内容区域不算遮挡。例如 1080×1920 源文件中心只有 200×200 驾车图标时，只检查这 200×200 的有效内容，不能因为源画布覆盖保护区而缩小。只有有效内容真实碰到品牌区域时才先平移整个素材；平移仍无法解决时，才以源尺寸为起点等比缩小到有效内容刚好不遮挡品牌区域的最大尺寸，禁止无碰撞缩放或放大。动效沿用同一规则：effective_region 只参与碰撞计算，只有 icon 裁切 effective_region；phone、full_alpha 和 cta_icon 进入动效后仍保留完整源文件。图层顺序固定为主画面 → 素材/动效 → 字幕与 CTA → logo → 警示语：字幕位于素材上方，logo 位于素材、字幕和 CTA 上方，警示语为最终最高层。源视频若被预检识别出跨多帧稳定的固定黑边，必须更换或裁切素材后才能渲染。

成片必须从数字人口播第一帧直接开始，不生成模糊背景标题卡、预卷、开场动画或独立静帧。开头钩子只能通过数字人画面上的字幕或已审查物料表达。旧时间轴中的 `pre_roll_duration` 和 `hook` 字段仅兼容读取，渲染器必须忽略。

BGM 必须先按目标综合响度归一化，再做小范围后置微调。默认目标为 `-28 LUFS`，`--bgm-volume` 默认为 `1.0`，只作为归一化后的微调倍率；不得沿用旧的原始衰减值 `0.22`。人声继续归一化到 `-16 LUFS`，最终以人声清晰且 BGM 可感知但不盖住人声为准。

渠道和 BGM 采用“用户要求优先，否则模型自主选择”的输入契约。用户明确指定渠道或 BGM 时按其要求执行；用户未指定渠道时，执行模型必须自行选择与口播利益点、金额、歌单和素材画面一致的正式渠道，并按该渠道的最严格文案边界完成校验，正式成片不得使用 `general`；用户未指定 BGM 时，执行模型必须从任务目录或调用方提供的音频候选中选择真实存在、可解码且已纳入本次投放范围的 BGM，优先选择不抢人声、无明显歌词或突兀强拍、适合循环且与口播节奏相符的候选。视觉 Manifest 不保存音频记录。存在多个合格候选时直接选择最匹配者，不向用户追问渠道或 BGM；把最终选择和依据写入计划、合规报告或交付说明。只有找不到任何真实可用 BGM 时才按缺少必需素材处理，不得虚构路径。CLI 仍显式传入模型选定的 `--channel` 和 `--bgm`，参数必填不代表必须让用户决定。

默认以 `motion_effects.mode=auto` 检测已安装的 `video-motion-effects`。可用时为合格图片物料随机选择 Remotion 入场效果；不可用或单个效果失败时回退静态叠加。随机选择必须可复现，详细规则见 [motion-effects.md](references/motion-effects.md)。

## 执行顺序

1. 确认工作区、素材根目录和时间轴 JSON；用户已指定时采用其渠道/BGM，未指定时由执行模型按上面的契约自行选择并记录依据。继续确认金币/歌单状态、歌曲审查结果和第三方授权；实际时长以数字人口播处理结果为准。
2. 使用 `manage-visual-asset-library` 同步素材、Read 理解全部图片/视频并校验 `visual_assets_manifest.json`。若检测到新增或修改，必须在通用 Skill 中补齐理解结果后再继续。
3. 生成任何视频前确认通用 Manifest 校验 `ok=true`。汽水 preflight 还会在消费端检查 `asset_root`、引用路径、非空 description 和合法 effective_region；任一失败都返回通用 Skill 修复，不能在汽水 Skill 中另建一套描述规则。
4. 先逐句判断是否为利益点。特殊规则未命中时才把利益点文本交给通用 Skill，读取 `asset_candidates.json` 后决定是否采用；每条最终物料必须记录 `semantic_role=benefit_point` 和对应的 `matched_benefit_text`。非利益点不查询普通候选。如果调用方提供口播，先运行 `caption-budget` 取得由当前字幕样式动态计算的单行字数上限；执行模型复制原台词并只插入语义换行，再把这份语义字幕稿传给 `repair-captions`。随后对当前输入视频执行 Whisper 词级转写，把每个语义行映射到实际词级时间；原始台词、原始时间轴不覆盖，修正版时间轴和修复报告单独输出。最后运行预检，检查素材契约、利益点选材、字幕样式、品牌保护区、缩放、图层顺序和源素材固定黑边；不要在素材或运行环境缺失时猜测路径。
5. 使用多组音量阈值交叉检测停顿；固定调用 Whisper `tiny` 增加逐词时间戳校验。提供口播时，字幕时序仍必须由对当前输入执行的 `--word_timestamps True` 结果驱动。
6. 结合语义、波形、呼吸、尾音、口型和动作人工确认范围，每处默认保留约 `0.16s`，不得整段删除。
7. 先输出去气口中间视频，再应用倍速。未指定时使用 `1.1×`，指定时使用调用方传入的倍速。
8. 使用 Whisper 实际词级时间戳生成 `time_mode=input` 字幕，再填入已经按动态字数上限完成语义分行的口播台词；一行严格对应一个 caption event，禁止渲染脚本再做等宽时间切分。把时间轴和全部物料统一到 `input`，直接复用修复后字幕 input `start/end`，不使用映射后 output 时间回填素材。字幕事件内部仍按实际像素宽度显式均衡换行，优先一到两行、最多三行，超限直接失败，不缩小字号。同一 `sequence_id` 内相邻素材必须满足上一条 `end ==` 下一条 `start`，不留缓冲、不重叠；数字人空档必须切换 `sequence_id`。只在利益点时间段匹配真实物料，最终字幕去除普通标点并保留数字内部小数点。检测 `video-motion-effects` 并按稳定随机种子为合格图片选择入场效果。字幕使用 `2–3px` 黑色细描边且无阴影，不得带背景条；素材不受字幕安全区限制。渲染器只检查素材 `effective_region` 是否进入品牌保护区；无内容画布不触发移动或缩放。只有有效内容真实遮挡时才先平移，无法平移解决时再等比缩放。字幕和 CTA 在素材及动效上方绘制，logo 再叠加于字幕与 CTA 上方。第 0 秒直接显示数字人，非利益点默认不叠加普通素材。
9. 先运行规则校验，再渲染。校验失败时不要通过改参数绕过红线。
10. 使用调用方提供的官方 logo、规定警示语和官方尾帧视频。正片中 logo 必须位于素材、动效、字幕和 CTA 上方，警示语必须最后绘制为最高层；尾帧硬切进入，不叠加其他元素。
11. 先把 BGM 归一化到目标响度，再混入人声和轻提示音，完成人声、BGM、响度和手机扬声器复听。
12. 运行完整 QA，交付成片、封面、素材/时间轴报告、合规报告和技术验收报告。

## 命令入口

将 Skill 路径和运行时设为：

```bash
SKILL_DIR="${CODEX_HOME:-$HOME/.codex}/skills/edit-soda-music-video"
PY=python3
PIPE="$SKILL_DIR/scripts/soda_pipeline.py"
```

### 同步工作区素材清单

正式流程直接使用通用 Skill；下面的汽水命令只作为兼容转发入口：

```bash
"$PY" "$PIPE" sync-assets \
  --workspace /absolute/path/workspace \
  --asset-root /absolute/path/assets
```

默认在工作区生成 `visual_assets_manifest.json`。`sync-assets` 不再包含扫描实现，只查找并转发到 `manage-visual-asset-library/scripts/asset_manifest.py`。旧 `soda_assets_manifest.json` 仍可通过 `--asset-manifest` 显式传入 preflight/render，但新任务不再默认生成旧文件名。

素材理解与普通语义检索必须完整使用通用 Skill；汽水只保留“特殊匹配 → 通用候选 → 汽水最终决策”的业务顺序。特殊命中时仍把规则 ID 写入 `special_match_rule`。

### 动态字幕字数上限与语义分段

每个任务先根据实际时间轴样式计算一次单行字数上限：

```bash
"$PY" "$PIPE" caption-budget \
  --timeline-json /absolute/path/timeline.json \
  --output-json /absolute/path/caption_budget.json
```

读取报告中的 `caption_character_budget.max_characters_per_line`。执行模型复制原口播，只插入换行，按完整语义意群生成一行一个 caption 的字幕稿；不得修改、遗漏、补充或调整原词序。未超过动态上限时通常保持完整；超过时优先在动作与结果、条件与结论、转折、因果或并列意群之间切分。禁止按字符数平均切分，也不得拆开动宾结构、否定结构、“汽水音乐”、数字小数、金额单位或英文单词。后续全部句子复用本任务同一个动态上限，不逐句重新计算像素宽度；最终由布局预检统一兜底。

### 预检

```bash
"$PY" "$PIPE" preflight \
  --input /absolute/path/source.mov \
  --asset-root /absolute/path/assets \
  --asset-manifest /absolute/path/workspace/visual_assets_manifest.json \
  --bgm /absolute/path/background-music.mp3 \
  --timeline-json /absolute/path/timeline.json \
  --output-json /absolute/path/preflight.json
```

必须检查 `ok=true`。`--asset-root`、`--bgm` 和 `--timeline-json` 没有 CLI 默认值，必须按任务显式传入；用户没有指定 BGM 时，由执行模型先从任务内候选自主选定路径再传给 `--bgm`，不要把参数必填转化成对用户的追问。

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

调用方提供口播后，先用 `caption-budget` 取得动态上限，再由执行模型生成只增加语义换行的字幕稿，最后使用 `repair-captions` 单独生成字幕时间；`render` 传入 `--script-file` 或 `--text` 时会自动对当前 `--input` 执行 Whisper `--word_timestamps True`，把每个语义行填入实际词级时间戳，并在输出目录生成 `<成片名>_repaired_timeline.json` 和 `<成片名>_subtitle_repair.json`。任何语义行超过本任务动态上限都会失败，脚本不再自动等宽拆句。修正版时间轴顶层记录 `time_mode=input`，执行模型必须再把所有素材直接对齐该轴的 input 字幕边界；原始时间轴和旧素材时间不自动当作新字幕时间。有素材时应先完成 input 时间回填再渲染；提供口播时 Whisper 不可用或没有词级结果必须报错，不能退化到旧字幕区间或静音估算。

```bash
"$PY" "$PIPE" repair-captions \
  --timeline-json /absolute/path/timeline.json \
  --input /absolute/path/source_去气口.mp4 \
  --script-file /absolute/path/spoken_script_semantic_lines.txt \
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
  --asset-manifest /absolute/path/workspace/visual_assets_manifest.json \
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

`--speed` 在去气口之后应用，默认值为 `1.1`。不要根据口播快慢自行改回原速；只有调用方明确传入其他值时才覆盖默认值。新流程的字幕、物料和提示音都使用去气口后当前 input 的时间：不得再扣减 `removed_ranges`，渲染器只统一除以最终 `speed`。仅 `time_mode=original` 的旧兼容时间轴才先按删除区间映射，再应用倍速。

`--motion-effects` 可为 `auto/off/required`；`--motion-seed` 用于生成可复现的随机动效版本。省略种子时，渲染器根据时间线、输出路径和物料信息生成稳定种子。

`render` 收到 `--script-file` 或 `--text` 时必须先用本地 Whisper `tiny` 对当前 `--input` 执行 `--word_timestamps True`；调用方台词是字幕文本权威来源，但传入文本必须已经按 `caption-budget` 的动态上限完成模型语义分行。每行是一个 caption event，入点/出点来自该行首尾文字对应的 Whisper 真实词级时序，禁止复用原字幕区间或让脚本按宽度自动切分。修正版时间轴统一写为 `time_mode=input`；所有素材也必须在渲染前改为 input 时间，并直接对齐修正字幕的 input `start/end`。缺少 Whisper CLI、词级 JSON、有效词时间戳或存在超限语义行时直接失败。原时间轴保持不变，可通过 `--repaired-timeline-json` 和 `--subtitle-repair-report` 指定修正版时间轴与修复报告路径。修正版中如果仍有素材使用 `original/output` 或未对齐 input 字幕边界，预检必须失败。

`preflight` 和 `render` 都会检查 `--asset-manifest`（省略时默认为时间轴 JSON 所在目录的 `visual_assets_manifest.json`）：Manifest 必须与 `--asset-root` 一致，消费端门禁校验 description 非空、`effective_region` 合法以及时间轴视觉素材已经入库；语义完整性以通用 Skill 的校验和 Read 复核为准。显式传入旧 `soda_assets_manifest.json` 时，只要其中视觉记录满足同一契约仍可使用。每条 `materials[]` 还必须标记 `semantic_role=benefit_point` 和 `matched_benefit_text`；声明 `special_match_rule` 时只校验规则 ID 合法，不校验素材 SHA-256。执行模型必须通过 Read 确认实际画面满足特殊规则。Whisper 时间轴门禁会强制顶层、字幕和全部素材使用 `time_mode=input`，直接在 input 时钟比较字幕/素材边界；同时校验半开区间、禁止重叠、同 `sequence_id` 严格无缝和字幕切换点对齐。门禁失败时先完成素材理解、利益点标注、特殊素材纠正或重算素材时间，再重新预检。

素材策略写在时间线的 `visual_policy` 中：`match_materials_only_for_benefit_points=true`、`preserve_material_size=true`、`reposition_before_scale=true`、`seamless_material_handoffs=true`、`align_material_cuts_to_caption_boundaries=true`，小图标相对字幕的默认位置由 `icon_caption_placement={mode: above_caption, gap: 72, line_height_scale: 1.2}` 控制。渲染器把 Manifest 的 `effective_region` 映射到画布，只在有效内容真实进入 logo/警示语保护区时处理；空白或透明画布越界不触发任何尺寸变化。`phone`、`full_alpha` 和 `cta_icon` 默认使用完整源文件的源像素尺寸，`icon` 默认按 effective_region 裁去空白画布并以裁后内容源像素尺寸 `1:1` 叠加；不得固定缩放到 230px、300×300 或输出画布。只有有效内容碰撞且移动无法解决时，才等比缩小到最大安全尺寸。

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
- QA 必须确认普通素材只出现在利益点台词时间段；所有素材使用 `[start,end)` 半开区间，不重叠，同一 `sequence_id` 内相邻条目严格 `end == next.start`，切换点对齐下一条字幕 `start`；“满三毛提现”命中时使用 Read 确认符合画面要求的完整提现页或轻度变体，且时间轴带 `special_match_rule=withdraw_0_3`；字幕、警示语和所有素材外围不存在背景黑条、黑框或半透明黑色承托层；字幕文本与调用方口播一致，普通标点已移除而数字内部小数点仍保留；预检/渲染报告中的字幕分行不超过三行且每行宽度不超过安全宽度，最长字幕抽帧后左右不越界，图标位置使用同一最终字幕行数；只检查素材有效内容与整个入场动效的有效内容是否进入 logo/警示语保护区，透明留白和无内容画布不得导致缩放；确有碰撞时先平移，再缩放到最大安全尺寸；字幕黑色细描边为 `2–3px`、阴影为 `0`，字幕始终位于素材上方，logo 位于素材/字幕/CTA 上方，警示语位于最终最高层；源素材固定黑边必须在预检阶段拦截。
- 缺少素材时可用明确标注 `DEMO/待替换` 的文字卡临时占位；正式交付前必须替换或获得书面确认。
- 歌单、金额、第三方名称和“赚钱”类利益点必须按渠道分别校验，不能把一次授权扩展到其他任务。
- 素材文件名或目录名中的内部标签不得直接当作投放文案；最终画面、字幕和旁白仍须单独执行禁词扫描。

## 交付说明

最终回复列出：输入文件、渠道及选择依据、去气口范围、速度、素材根目录、BGM 及选择依据、BGM 目标 LUFS 和后置微调倍率、实际时长、输出视频、封面、合规报告、预检报告和 QA 结果。
