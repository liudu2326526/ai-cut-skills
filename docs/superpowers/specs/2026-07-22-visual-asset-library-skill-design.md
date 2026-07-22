# 通用视觉素材库 Skill 拆分设计

## 背景

`edit-soda-music-video` 当前同时承担素材目录扫描、媒体元数据采集、模型视觉理解、有效区域标注、语义选材、汽水业务判断、时间轴编排和渲染。这使通用素材能力与汽水专属规则相互耦合，也容易在多份文档中形成重复或冲突规则。

本设计把通用视觉素材能力拆成独立 Skill，并通过稳定的 Manifest 与候选报告 JSON 契约服务汽水混剪及其他项目。执行 Skill 的模型继续直接使用 Read 查看真实画面；不增加向量库、外部大模型接口或素材理解脚本。

## 已确认决策

- 新 Skill 是跨项目通用视觉素材库，不包含汽水业务语义。
- 汽水 Skill 保留利益点判断、特殊匹配、合规、时间轴和渲染规则。
- 通用 Skill 的检索只输出候选素材及匹配理由，不选择最终素材，不修改调用方时间轴。
- 两个 Skill 通过独立 Manifest 契约通信，不共享 Python 包或内部数据结构。
- Skill 名称使用 `manage-visual-asset-library`。

## 目标

1. 为图片和视频提供可增量更新的统一素材清单。
2. 让执行模型通过 Read 完成准确的中文内容理解和源像素有效区域标注。
3. 在素材理解完整后，根据任意项目提供的查询文本输出可审查的语义候选。
4. 让消费方仅依赖公开 JSON 契约，不依赖通用 Skill 的内部实现。
5. 保留旧汽水 Manifest 的显式传入兼容能力，避免已有任务立即失效。

## 非目标

- 不管理 BGM、字体或字幕文件。
- 不判断台词是否为利益点。
- 不保存汽水渠道、金额、第三方授权或品牌规则。
- 不保存 `withdraw_0_3` 等特殊素材规则。
- 不生成或修改视频时间轴。
- 不决定素材布局、位置、缩放、动效或图层顺序。
- 不生成 `keywords`、`recommended_usage`、向量索引或模型配置字段。
- 不通过脚本、API 或额外模型完成视觉理解和语义匹配。

## 职责边界

### `manage-visual-asset-library`

- 递归扫描图片和视频。
- 使用 FFprobe 采集尺寸、时长、格式、编码和帧率等确定性元数据。
- 比较文件身份并增量更新 Manifest。
- 为视频确定性导出代表帧，供执行模型使用 Read 查看。
- 指导模型为每个素材写入准确中文 `description`。
- 指导模型写入源像素坐标的 `effective_region`。
- 校验 Manifest 覆盖、理解完整性和字段合法性。
- 接收查询文本，基于 description 与媒体事实输出最多三个候选和理由。

### `edit-soda-music-video`

- 判断口播中的利益点与非利益点。
- 只允许利益点匹配普通素材。
- 优先执行 `special-material-matches.md` 中的汽水特殊规则。
- 校验渠道、金额、歌曲和第三方授权。
- 生成 Whisper input 时间轴并设置素材入点、出点和无缝衔接。
- 写入 `semantic_role`、`matched_benefit_text` 和 `special_match_rule`。
- 应用品牌保护区、有效内容碰撞、移动、缩放、动效和渲染规则。
- 在渲染边界执行最低消费端校验，防止引用未入库或理解不完整的素材。

## 目录结构

```text
skills/manage-visual-asset-library/
├── SKILL.md
├── agents/
│   └── openai.yaml
├── scripts/
│   ├── asset_manifest.py
│   ├── extract_video_frames.py
│   └── validate_manifest.py
├── references/
│   ├── manifest-contract.md
│   ├── content-understanding.md
│   └── semantic-matching.md
└── tests/
    ├── test_asset_manifest.py
    ├── test_extract_video_frames.py
    ├── test_validate_manifest.py
    └── test_skill_contract.py
```

`SKILL.md` 只保留核心工作流、门禁顺序和引用路由。详细 Schema、描述规则和匹配规则分别放入三个一级 reference，避免重复。

## Manifest 契约

默认文件名为 `visual_assets_manifest.json`。Manifest 必须写入任务工作区，不得写回 Skill 目录或作为具体素材配置提交。

```json
{
  "schema_version": 1,
  "generated_at": "2026-07-22T00:00:00+00:00",
  "workspace": "/absolute/path/workspace",
  "asset_root": "/absolute/path/assets",
  "fingerprint_mode": "path-size-mtime",
  "metadata_mode": "ffprobe",
  "fingerprint": "a1b2c3d4",
  "summary": {
    "total": 1,
    "by_kind": {"image": 1}
  },
  "changes": {
    "status": "updated",
    "added": [],
    "removed": [],
    "modified": [],
    "reused_metadata_count": 1
  },
  "scan_errors": [],
  "assets": [
    {
      "relative_path": "ui/withdraw.png",
      "file_name": "withdraw.png",
      "extension": ".png",
      "kind": "image",
      "size_bytes": 123456,
      "mtime_ns": 123456789,
      "media": {
        "probe_ok": true,
        "width": 1080,
        "height": 1920
      },
      "description": "执行模型基于实际画面写出的准确中文描述。",
      "effective_region": {
        "x": 99,
        "y": 105,
        "width": 882,
        "height": 1743,
        "coordinate_space": "source_pixels"
      }
    }
  ]
}
```

### 字段规则

- `relative_path` 是素材在 `asset_root` 下的稳定引用键。
- `kind` 只允许 `image` 或 `video`。
- 新 Skill 不根据文件名或目录名推断语义 `category`。
- `description` 必须来自执行模型实际查看的原图或视频代表帧。
- `effective_region` 必须是源文件像素坐标中的最小有效内容联合矩形。
- 图片有效内容包括人物、UI、文字、图标、按钮以及具有表达作用的背景。
- 透明留白、纯色无内容边距和空画布不得进入有效区域。
- 视频有效区域使用多张代表帧中有效内容的联合边界。
- `description` 或 `effective_region` 缺失表示理解未完成，不增加额外状态字段。
- 新增或实际内容变化的素材不得复用旧理解结果。
- 未变化素材保留已有人工作业字段，避免重复 Read。
- 旧 Manifest 中的额外非视觉记录或旧字段可以被消费者忽略，但不能影响视觉记录校验。

### 变化检测

默认使用相对路径、文件大小和修改时间生成指纹。`--checksum` 可以作为可选的内容变化检测方式，但 SHA-256 只用于增量同步，不能用于特殊规则、视觉相似性或业务合规判断。

## 内容理解流程

1. 运行素材同步，获取新增、修改、删除和复用清单。
2. 对所有新增、修改或缺少理解字段的图片使用 Read 查看原图。
3. 对视频先导出首帧、四分之一、中点、四分之三和尾帧；短视频去除重复时间点。
4. 使用 Read 逐张查看视频代表帧，不能只看文件名或第一帧。
5. 透明图片必要时分别在浅色和深色背景上查看，区分透明留白和真实内容。
6. 写入具体、可核对、可检索的中文 description。
7. 写入源像素 effective_region；视频写多帧联合区域。
8. 运行通用 validator。只有全部视觉记录通过，Manifest 才能用于正式检索。

description 应覆盖适用的页面或素材类型、主体、布局与数量、关键可见文字和数字、动作或状态以及画面本身能直接表达的语义。无法确认关键事实时保持字段缺失并报告人工确认，不能根据文件名补全。

## 候选报告契约

默认输出文件名为 `asset_candidates.json`。

```json
{
  "schema_version": 1,
  "generated_at": "2026-07-22T00:00:00+00:00",
  "manifest": "/absolute/path/visual_assets_manifest.json",
  "query": "满三毛即可提现",
  "status": "matched",
  "candidates": [
    {
      "rank": 1,
      "relative_path": "ui/withdraw.png",
      "kind": "image",
      "description": "完整提现档位选择页，清晰显示0.3元提现档位。",
      "match_level": "strong",
      "reason": "画面明确包含0.3元提现档位，与查询主体、金额和动作一致。"
    }
  ],
  "no_match_reason": null
}
```

### 检索规则

- 检索前必须先通过 Manifest 完整性校验。
- 调用方可以提供 `kind`、方向、分辨率或时长等媒体事实过滤条件，但不能把项目业务规则写入通用 Skill。
- 执行模型比较查询与 description 中的主体、动作、功能、状态、场景、可见文字和数字。
- 不能因为文件名、目录名或单个关键词相同就判为匹配。
- 最多返回三个候选，按 `strong`、`medium`、`weak` 分级，不伪造精确数值分数。
- 每个候选必须给出基于画面事实的匹配理由。
- 没有真正匹配时返回空候选，不能为了填满数量强行选择。

### 状态

- `matched`：至少有一个可解释的候选。
- `no_match`：Manifest 完整，但没有合适素材；`candidates` 为空并填写 `no_match_reason`。
- `needs_understanding`：Manifest 中仍有缺失或无效理解字段，不执行语义检索。
- `error`：Manifest 不可读、根目录不一致、媒体无法确认尺寸或存在其他结构错误。

## 汽水集成流程

1. 汽水 Skill 要求使用 `manage-visual-asset-library` 同步素材并完成全量理解。
2. 通用 Skill 校验 Manifest，汽水 Skill 获得 Manifest 路径。
3. 汽水 Skill 使用 Whisper input 字幕逐句判断利益点。
4. 非利益点不查询普通素材。
5. 利益点先检查汽水特殊规则；命中时由汽水 Skill 负责规则判断和最终确认。
6. 未命中特殊规则时，把利益点文本交给通用 Skill，获得候选报告。
7. 汽水 Skill 结合合规、布局和素材连续性决定是否采用候选。
8. 汽水 Skill 写入真实路径、`semantic_role`、`matched_benefit_text`、时间范围和可选 `special_match_rule`。
9. 汽水 preflight 对被引用素材执行消费端最低契约校验，再进入布局和渲染。

特殊规则在需要寻找重命名或轻度变体素材时，可以把明确画面条件作为通用查询输入；规则是否命中以及候选是否满足业务要求仍由汽水 Skill 决定。

## 迁移方案

### 迁入通用 Skill

- 将现有 `asset_manifest.py` 的扫描和增量更新能力迁入并改为只处理图片、视频。
- 将通用 Manifest 说明迁入 `manifest-contract.md`。
- 将 Read、description、effective_region 和普通语义比较规则迁入对应 references。
- 为视频代表帧增加独立的确定性导出脚本。
- 把通用 Manifest 校验从汽水 pipeline 提取为独立 validator。

### 汽水 Skill 调整

- `special-material-matches.md` 保持汽水专属，不迁移。
- `asset-requirements.md` 只保留汽水布局、黑边、保护区和时间轴输入字段。
- 删除汽水中重复的通用描述提示词和普通语义匹配说明，改为 `**REQUIRED SUB-SKILL:** Use manage-visual-asset-library`。
- `soda_pipeline.py preflight` 保留消费端最低校验，不重新实现素材同步或内容理解。
- `sync-assets` 在过渡期保留为薄转发入口，不保留扫描实现；新文档使用通用 Skill 的命令入口。
- 新任务默认使用 `visual_assets_manifest.json`。
- 已有 `soda_assets_manifest.json` 仍允许通过 `--asset-manifest` 显式传入；只要视觉记录满足契约即可使用。

### Skill 定位

兼容转发入口按以下顺序查找通用 Skill：

1. `VISUAL_ASSET_LIBRARY_SKILL_DIR` 环境变量；
2. `${CODEX_HOME:-$HOME/.codex}/skills/manage-visual-asset-library`；
3. 当前仓库中的 sibling skill 目录。

找不到通用 Skill 时明确失败并给出安装路径，不回退到汽水内部旧实现。

## 错误处理

- 素材根目录不存在：同步失败，不创建空的正式 Manifest。
- FFprobe 不可用或无法读取视觉尺寸：正式同步/校验失败；快速扫描可以记录错误，但不能进入正式检索。
- 图片或视频读取失败：记录具体相对路径并阻止完整性通过。
- description 缺失或空泛：确定性 validator 负责非空门禁，执行模型按质量清单负责语义复核。
- effective_region 缺失、非正数、越过源尺寸或坐标系错误：校验失败。
- 素材发生修改：清除旧 description/effective_region，要求重新 Read。
- 查询无匹配：返回 `no_match`，不能选择低相关素材充数。
- 候选报告不包含最终选择字段，以防通用层越权替消费方决策。

## 测试策略

实施严格采用 RED-GREEN-REFACTOR。先为新契约写失败测试，再迁移实现。

### 确定性代码测试

- 只扫描支持的图片和视频，忽略音频、字体、字幕和其他文件。
- 首次同步创建 Manifest；指纹未变化时不重写。
- 未变化素材保留 description/effective_region。
- 新增素材缺少理解字段；修改素材清除旧理解字段；删除素材从 Manifest 移除。
- Manifest 必须位于工作区内，路径逃逸被拒绝。
- `--checksum` 只影响变化检测，不生成业务校验逻辑。
- validator 拒绝错误根目录、缺失描述、缺失区域、非法坐标和越界区域。
- validator 忽略旧 Manifest 中的非视觉记录和允许的额外字段。
- 代表帧脚本为普通视频导出五个时间点，为短视频去重，并对失败给出明确路径。

### Skill 契约测试

- 新 Skill 明确要求 Read 原图和视频多帧。
- 新 Skill 禁止文件名代替画面理解。
- 新 Skill 不包含 `keywords`、`recommended_usage`、向量或外部模型调用。
- 新 Skill 不包含利益点、汽水特殊匹配、时间轴和品牌布局规则。
- 候选报告只包含候选、分级和理由，不包含最终选用或时间轴字段。
- 汽水 Skill 明确声明通用 Skill 依赖。
- 汽水特殊匹配规则仍存在且优先于普通候选查询。
- 汽水 Skill 不再重复保存完整通用素材理解提示词。

### 集成测试

- 通用 Skill 生成的新 Manifest 可以通过汽水 preflight。
- 显式传入满足视觉契约的旧 `soda_assets_manifest.json` 仍可通过。
- Manifest 未完成理解时，通用检索返回 `needs_understanding`，汽水渲染也被阻止。
- 普通利益点可获得候选报告，但通用 Skill 不修改时间轴。
- 非利益点和特殊规则的决策完全留在汽水 Skill。

### 行为验收场景

- 文件名很像查询但画面不相关时，不应入选。
- 提现页面 description 记录清晰金额和页面状态时，可以针对相符查询成为强候选。
- 只有局部金额、结果页或模糊关键文字时，应降级或返回无匹配。
- 1080×1920 空画布中央小图标只标注中心有效区域，不把整张画布视为内容。
- 修改素材画面但保留文件名时，旧理解必须失效并要求重新 Read。

## 验收标准

1. 仓库和本地安装目录中存在可独立触发的 `manage-visual-asset-library`。
2. 新 Skill 能完成同步、代表帧导出、Read 理解指导、校验和候选报告流程。
3. 通用 Manifest 与候选报告符合本设计 Schema。
4. 通用层没有汽水利益点、特殊规则、渠道、品牌、时间轴或渲染逻辑。
5. 汽水层没有重复的通用素材扫描实现或完整理解提示词。
6. 汽水特殊匹配、Whisper input 时间轴和品牌渲染规则行为不变。
7. 新增测试先失败后通过，现有汽水测试继续通过。
8. `quick_validate.py`、Python 编译、测试套件和 `git diff --check` 全部通过。
