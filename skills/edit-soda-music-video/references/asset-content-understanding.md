# 执行模型的素材理解与语义匹配

## 原则

素材内容理解和素材匹配不通过脚本调用另一个大模型，也不配置 API、模型端点或向量库。执行这个 Skill 的模型本身就是理解和匹配模型，直接使用可用的 Read/图像查看工具检查素材，再编辑工作区 Manifest 和时间轴。

`sync-assets` 只负责确定性的文件扫描、类型判断和 FFprobe 元数据。它不会理解图片，也不会根据文件名替素材做决定。

生成视频前必须完成全量视觉素材理解门禁：Manifest 中所有 `kind=image` 或 `kind=video` 的记录都必须有非空 `description` 和源像素坐标的 `effective_region`，Manifest 的 `asset_root` 必须与当前任务一致，时间轴引用的 logo、尾帧和普通素材都必须出现在 Manifest 中。`preflight`/`render` 会检查这些条件；任一条件不满足时先停止渲染，完成下面的 Read 流程后再继续。

## 入库时的操作顺序

1. 运行 `sync-assets`，读取工作区 Manifest；
2. 查看 Manifest 的 `changes.added`、`changes.modified`，以及缺少 `description` 或 `effective_region` 的素材；若要进入正式生成，不能只理解变化项，必须把所有图片/视频都核对为已有准确描述和有效区域；
3. 对每张待理解的图片使用 Read 工具打开原图，逐张确认真实画面；
4. 对每段待理解的视频先用 FFprobe 获取时长，再用 FFmpeg 导出首帧、四分之一、中点、四分之三和尾帧等缩略图；使用 Read 工具逐张查看这些缩略帧，不能只看文件名或第一帧；
5. 对透明 PNG 必要时在浅色和深色背景上各查看一次，区分透明留白与实际内容；
6. 为每个素材写一段准确、具体、可检索的中文 `description`；同时识别真正承载画面信息的最小矩形联合区域，以源文件像素坐标写入 `effective_region`；
7. 透明留白、纯色空白边距和无内容画布不进入 effective_region；人物、图标、文字、UI、手机框、按钮及有表达作用的背景进入 effective_region。视频使用代表帧中有效内容的联合边界；
8. 只把 `description` 和 `effective_region` 写入对应 Manifest 素材记录，不增加 `keywords`、`recommended_usage`、向量或模型调用字段；
9. 保存 Manifest 前复核描述和有效区域是否真的来自画面，不能把文件名、目录名或粗分类当成画面事实；
10. 再运行 `preflight --asset-manifest ...`，确认门禁报告 `asset_understanding.ok=true` 后才允许生成视频。

## description 写法

描述应尽量用一到三句话说明：

- 画面主体和场景；
- 正在发生的动作或界面操作；
- 可见的重要文字或功能状态；
- 这张图/这段视频实际能表达的口播语义。

示例：

```json
{
  "relative_path": "正文端内物料/通用/模式1.mp4",
  "kind": "video",
  "category": "ui_operation",
  "description": "这是一段手机录屏，展示用户进入汽水音乐播放设置页面并切换播放模式，画面中能看到循环播放和随机播放等选项，适合表达播放模式或播放设置功能。",
  "effective_region": {
    "x": 0,
    "y": 0,
    "width": 1080,
    "height": 1920,
    "coordinate_space": "source_pixels"
  }
}
```

不要写成空泛描述，例如“一个 App 页面”或“一个功能截图”。不要凭文件名臆测，也不要把透明区域描述成黑色背景。

例如一个 1080×1920 的驾车图标文件，只有中心 `x=440,y=860,width=200,height=200` 的白色图标有内容，其余区域为空白或透明，则写：

```json
"effective_region": {
  "x": 440,
  "y": 860,
  "width": 200,
  "height": 200,
  "coordinate_space": "source_pixels"
}
```

渲染器只用该 200×200 区域判断是否遮挡品牌区域，不能因为 1080×1920 源画布越界而移动或缩小素材。

## 什么时候重新查看

- 新增素材：必须查看并写 description 与 effective_region；
- Manifest 标记为 modified：源文件可能被替换，必须重新查看；
- 已有 description/effective_region 且素材未变化：复用，不重复查看；
- 只有文件名或目录名变化、画面内容未变：可以保留原理解结果，但要检查路径是否仍对应同一素材；
- 不能确认素材内容或有效区域：对应字段留空并在报告中标记待人工确认，不得编造。

## 根据口播匹配素材

执行模型先把当前口播逐句分为“利益点”和“非利益点”。只有明确表达产品功能带来的用户价值、合规权益、已授权优惠或具体使用收益的句子才属于利益点。寒暄、开场过渡、情绪铺垫、泛泛描述、单独 CTA 和免责声明不触发素材匹配。

只对利益点读取 Manifest 的 `description` 并做语义匹配：

1. 非利益点直接保持数字人主画面，不查询、不选择、不插入普通素材；logo、警示语和官方尾帧不属于这里的普通素材；
2. 对利益点先按 `kind`、`category`、布局、时长、合规状态和黑边检查做硬过滤；
3. 对剩余素材逐条阅读 description，并与利益点句子的主体、动作、功能、收益和场景进行语义比较；
4. 选择真正能解释这条利益点的素材，不因为关键词相似就选无关画面；
5. 将选中的真实 `path` 写入时间轴，同时写入 `semantic_role: benefit_point`、`matched_benefit_text`、素材的 `name`、`category`、`kind`、`layout` 和时间范围；
6. 没有准确匹配时明确报告“没有合适素材”，不要强行填充；
7. 如有两个以上候选，记录选择理由和未选原因到任务报告，方便人工复核。

模型不能创造 Manifest 中不存在的路径，也不能绕过现有的 logo/警示语保护区、固定黑边、渠道合规和图层顺序规则。
