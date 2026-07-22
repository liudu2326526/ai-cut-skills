# 执行工作流

## 1. 开剪前确认

确认以下字段并写入计划或报告：

- 主视频路径、渠道类型；实际时长由处理后的数字人口播决定；
- BGM 路径、素材根目录、logo 版本、尾帧文件；
- 是否金币、是否歌单、歌曲禁投审查结果；
- 金额档位、允许的利益点；
- 口播字幕文本和每个物料的入点/出点。
- 若调用方提供口播文件，确认其为字幕文本的权威来源；字幕时序仍必须来自对当前输入执行的 Whisper `--word_timestamps True`，字幕只保留无标点版本。

如果渠道没有确认，不要直接渲染。时长只记录实际结果，不作为渲染门槛。

## 2. 同步并预检素材

先运行 `scripts/soda_pipeline.py sync-assets`，把素材根目录的文件清单和可读取的媒体信息写入工作区 Manifest。每次运行都会比较指纹；未变化时复用现有清单，发生新增、删除或修改时重新读取并更新。执行模型随后必须用 Read 工具查看所有新增、修改或缺少理解结果的图片和视频代表帧，并把准确中文 description 与源像素 effective_region 写入 Manifest；description 写回前必须按 [asset-content-understanding.md](asset-content-understanding.md) 自检页面类型、结构数量、关键文字数字、状态和可表达语义，空泛描述需要重写。特殊素材也通过 Read 核对实际画面，不使用 SHA-256 门禁。不要调用素材理解脚本或外部模型端点。生成视频前再次确认全部图片/视频都有合格的 description/effective_region，Manifest 的 `asset_root` 与当前任务一致，时间轴没有引用未入库视觉素材。任何一项不满足都先完成素材理解，禁止进入 render。

使用 `scripts/soda_pipeline.py preflight` 检查 FFmpeg、FFprobe、BGM、时间轴 JSON、字体、logo、尾帧和通用物料。原始视频和原始物料保持不变，在副本路径输出中间文件。

## 3. 去气口

先用 `detect-pauses` 运行 `-35dB/-30dB/-25dB` 多阈值交叉检测；固定使用本地 Whisper `tiny` 增加逐词时间戳。Whisper 文本不负责最终字幕文字，但它的实际词级时间戳必须负责字幕时序。严格阈值默认检查 0.35 秒以上静音，动态阈值补充 0.18 秒以上停顿。只把多阈值相互印证，或音量检测与 Whisper 相互印证的区间列为稳定候选。

不要自动接受全部候选。结合语义、波形、呼吸、尾音、爆破音、口型和动作人工确认，每处保留 `0.12–0.20s`，默认 `0.16s`。将批准范围写入 JSON，再用 `trim-pauses` 输出中间视频。完整规则见 [pause-removal.md](pause-removal.md)。

删掉停顿后，先生成音画同步的去气口中间文件，并把该文件作为 Whisper 和渲染的当前 input。字幕和物料统一使用 `time_mode=input`，素材时间直接对齐 Whisper 识别出的 input 字幕边界；不再对这些时间重复扣减去气口范围。默认倍速 `1.1×`，调用方明确指定时使用其 `--speed`；渲染器最后再对字幕、物料和音效统一应用倍速。

## 4. 计划与渲染

先逐句识别利益点。只有明确表达产品功能带来的用户价值、合规权益、已授权优惠或具体使用收益的台词才允许选材；寒暄、过渡、情绪铺垫、泛泛描述、单独 CTA 和免责声明不查询、不匹配、不插入普通素材。对每条利益点先按 [special-material-matches.md](special-material-matches.md) 判断特殊规则；命中时优先使用参考素材，或使用 Read 确认核心画面完整的轻度变体，并写入 `special_match_rule`；未命中才阅读 Manifest description 做普通语义匹配。所有素材都要写入真实路径、`semantic_role=benefit_point` 和 `matched_benefit_text`；不得创造路径或因为文件名相似就选择无关画面。完整种类和输入要求见 [asset-requirements.md](asset-requirements.md)。如果传入口播文件，先对去气口后的当前输入运行 `repair-captions --input ...`；修正版时间轴会改为 `time_mode=input`。执行模型随后必须直接读取修正字幕 input `start/end`，重算所有素材，再进入 `render`。有物料时不要依赖 `render --script-file` 一步到底，因为 Whisper 生成新字幕后仍需执行模型完成语义选材与 input 时间回填。

Skill 不提供固定物料映射或样片时间码。使用 Whisper 时，必须根据当前 input 上的修正字幕重新计算素材入点与出点，不把 output 时间或去气口前 original 时间回填给素材。素材时间区间使用半开 `[start,end)`：同一 `sequence_id` 内不留过渡缓冲，严格使用 `previous.end == next.start`，且该 input 时刻必须等于下一条字幕的 input `start`。不同利益点段回到数字人时使用不同 `sequence_id`，不得用普通素材填空。

先运行 `preflight --asset-manifest ...`。预检会阻止以下情况：Manifest 缺失、Manifest 与当前 `asset_root` 不一致、任意图片/视频 description/effective_region 为空或无效、时间轴视觉素材未被 Manifest 跟踪、普通素材没有明确绑定利益点，以及未知 `special_match_rule`。预检不使用 SHA-256 判断特殊素材；执行模型必须在生成前 Read 并确认画面符合对应规则。门禁失败时回到素材理解、利益点标注或特殊匹配步骤，不能用参数绕过。

渲染使用 Skill 内置 `scripts/standalone_renderer.py`。它通过 Python 标准库和 FFmpeg/FFprobe 独立完成 ASS 字幕、媒体信息读取、调用方素材叠加、封面提取、BGM 混音和 JSON 报告，默认输出 1080×1920、30fps、H.264/AAC。BGM 先归一化到默认 `-28 LUFS`，再使用默认 `1.0` 的后置微调倍率；禁止把旧的 `0.22` 原始衰减值继续用于新流程。

时间线 `motion_effects.mode` 默认为 `auto`。已安装的 `video-motion-effects` 可用时，为合格图片随机选择 Remotion 入场效果，生成短透明 ProRes 4444 片段；FFmpeg 延长稳定帧，在素材上方绘制字幕与 CTA，再叠加 logo，最后绘制警示语。随机选择必须记录种子，具体配置见 [motion-effects.md](motion-effects.md)。

渲染器必须从数字人口播第一帧直接开始。不得生成独立开场标题卡；旧时间轴中的 `pre_roll_duration` 和 `hook` 字段不参与渲染。首屏钩子需要时直接叠加在数字人主画面上。

使用 `references/timeline-template.json` 作为字段结构参考。复制到任务输出目录后填写字幕、去气口范围、调用方素材路径和时间点，再通过 `--timeline-json` 传入。

连续素材段的每个 `materials[]` 条目可填 `sequence_id`。同一 `sequence_id` 的条目按时间排序必须无缝衔接；省略时默认为同一连续段，因此编辑模型不得无意留下 0.2–0.3 秒间隙。有意返回数字人时才切换 `sequence_id`；Whisper 流程中的切换点和每个素材起止点都必须直接对齐 input 字幕边界。

填写字体时必须使用字体文件的真实内部 family name，不能把文件名或正文字体名称复制给 SodaFont。字幕样式写入 `font.caption_style`；模板已把字号 13、缩放 100%、黑色细描边、阴影 0、`x=0,y=-500` 转为 1080×1920 ASS renderer 的校准配置：`outline=3`、`shadow=0`。字幕文本必须去除中英文标点，不得添加字幕背景条或半透明承托层。

素材无需避让字幕安全区。1080×1920 默认品牌保护边界对应素材可用区 `x=48..1032, y=320..1740`，但碰撞判断只使用 Manifest 的 effective_region 映射结果。透明留白、纯色空白边距和无内容画布可以越过保护边界，不触发变换。`phone`、`full_alpha` 和 `cta_icon` 默认保持完整源文件的源像素尺寸与原始比例；`icon` 在渲染前裁切 effective_region 并保持有效内容源像素尺寸，时间轴 `x/y` 直接定位裁切后的内容。不得对任何布局做 `650×1050`、`300×300`、230px 宽或整画布拉伸等默认标准化。只有人物、图标、文字、UI 等有效内容真实碰撞时才先移动，移动无法解决时再从源尺寸等比缩小到最大安全比例。Remotion 沿用相同策略：effective_region 只用于碰撞判断，只有 icon 裁切 effective_region，其他布局的动效保留完整源文件。

渲染顺序固定为主画面 → 素材/动效 → 字幕与 CTA → logo → 警示语。字幕必须高于素材；logo 必须高于素材、字幕和 CTA；警示语必须最后绘制为最终最高层。不得把 logo 与普通素材放在同一层，也不得让字幕滤镜在 logo 之后覆盖品牌标识。

检查 logo 画布：透明 logo 与目标视频同宽高比时使用 `full_canvas`，整张画布直接套到视频；紧边 logo 或比例不一致时使用 `placed`。默认 `auto` 会按画布比例和透明通道自动选择。

## 5. 验收

使用 `qa` 检查分辨率、帧率、编码、时长、完整解码和响度；再人工检查普通素材只出现在利益点、特殊利益点使用了符合画面要求的完整素材、“满三毛提现”没有误用局部截图或余额卡片、素材和动效的有效内容没有进入 logo/警示语保护区、空白画布没有导致无意义缩放、字幕位于素材上方、logo 位于素材/字幕/CTA 上方、警示语处于最终最高层，字幕黑色细描边为 `2–3px`、阴影为 `0`、无背景黑条或承托层，以及黑屏/冻帧、logo 重叠、禁投歌曲、第三方标识和手机扬声器听感。

QA 记录实际时长但不设置最低时长，也不区分正式成片与短 Demo；实际长度应与处理后的数字人口播和官方尾帧一致。

正式成片目标：约 -16±1 LUFS，峰值不高于 -1.0 至 -1.5 dBTP，人声约 -16 LUFS，BGM 默认约 -28 LUFS，且可感知但不盖住人声。尾帧不叠加任何额外元素。
