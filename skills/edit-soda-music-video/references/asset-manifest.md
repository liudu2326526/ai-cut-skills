# 工作区素材 Manifest

## 目的

`sync-assets` 把调用方提供的素材目录读取为工作区内的 `soda_assets_manifest.json`。它不向 Skill 写入具体素材，也不依赖 AIVideoEditor 项目。

## 同步行为

1. 递归扫描支持的图片、视频、音频、字体和字幕文件。
2. 为每个文件记录相对素材根目录的路径、扩展名、类型、大小和修改时间。
3. 对视频、音频和图片调用 FFprobe 读取可用的时长、分辨率、帧率、编码和音频参数；字体和字幕只记录文件信息。
4. 根据路径文字推断用途类别，例如品牌标识、官方尾帧、背景音乐、功能操作、场景视觉、利益点视觉或 CTA；推断结果必须人工复核，不能代替合规审查。
5. 用路径+大小+修改时间生成指纹。增加 `--checksum` 后改用 SHA-256 参与指纹。
6. 指纹、素材根目录、扫描模式和 Manifest 结构均未变化时返回 `status=unchanged`，不改写文件。
7. 发现新增、删除或修改时，只重新读取受影响文件的元数据并原子替换 Manifest；未变化文件的已读取元数据会复用。

## 执行模型内容理解

基础 Manifest 不调用另一个大模型。执行 Skill 的模型在读取 Manifest 后，直接使用 Read 工具逐张查看新增、修改或缺少 description 的图片，并查看视频代表帧，然后把准确中文 `description` 写回对应素材记录。不要通过素材理解脚本、API 端点或向量库完成这一步，也不要生成 `keywords` 或 `recommended_usage`。

## 状态

- `created`：首次创建 Manifest；
- `updated`：检测到素材变化或显式使用 `--force`；
- `unchanged`：素材指纹一致，文件未重写。

命令输出会包含 `added`、`removed`、`modified` 和 `reused_metadata_count`，便于记录本次同步范围。

## 使用约束

- Manifest 必须写在工作区内，默认文件名为 `soda_assets_manifest.json`。
- `asset_root` 可以是工作区内的目录，也可以是外部素材目录；Manifest 保存素材根目录位置和相对路径。
- `--quick` 适合只检查文件增删改，不读取媒体元数据；正式剪辑前使用默认完整扫描。
- FFprobe 不可用时仍会保存基础文件信息，并在对应记录的 `media.probe_error` 中说明原因。
- Manifest 是当前工作区的运行时缓存，不得复制回 Skill 目录或提交为固定素材配置。
- 缺少 `description` 的素材不能作为已理解素材参与语义匹配；无法确认内容时留空并标记待人工确认。
