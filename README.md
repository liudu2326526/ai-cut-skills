# AI Cut Skills

面向 Codex 与 WorkBuddy 的视频生产 Skill 集合。仓库按能力层级做逻辑分类，但所有 Skill 仍保持 `skills/<skill-name>` 的扁平目录，确保运行时可以直接发现。

分类、依赖和同步范围以根目录的 [`skill-catalog.yaml`](skill-catalog.yaml) 为准。

## Skill 分类

### 1. 运行环境

- `setup-video-editing-environment`：跨平台发现、复用、安装和检查 Python、FFmpeg/FFprobe、Whisper，以及可选的 Node、Chrome 和 Remotion 依赖。

### 2. 素材获取与治理

- `douyin-video-toolkit`：抖音页面捕获、视频流采集、URL/GID/关键词批量下载和失败诊断。
- `mogong-gid-retrieval`：消费通用抖音引用，执行魔工 GID 能力查询、业务过滤、结果导出和可选委托下载。
- `adxray-playlet-crawler`：AdXRay/ADX Ray 抖音热播短剧素材采集与下载，支持短剧分类筛选、剧名搜索、详情页素材排序和 manifest/debug 产物，下载后交给审核闸门。
- `aivideoeditor-visual-moderation`：阿里云视频审核增强版，输出涉政、涉军和 NSFW 命中信息、时间点、过审路由与短剧剪辑闸门。
- `manage-visual-asset-library`：跨项目图片/视频入库、Read 内容理解、有效区域标注、Manifest 校验和语义候选报告。

`douyin-video-toolkit` 负责通用素材解析与下载；`mogong-gid-retrieval` 只负责魔工业务查询、过滤和结果导出。魔工兼容入口通过统一引用契约调用 Toolkit，不再复制短链解析、GID 提取和万邦下载代码。

`adxray-playlet-crawler` 面向短剧热榜素材下载，下载结果先进入 `aivideoeditor-visual-moderation` 做阿里云审核闸门，只让 `过了` 或 `allow_short_drama_editing=true` 的素材进入后续包装、裂变或上传链路。

### 3. 通用渲染组件

- `subtitle-motion-effects`：Remotion 字幕动效层渲染，支持透明字幕层、合成预览和多字重字体目录。
- `video-motion-effects`：Remotion 图片入场动效，可输出合成视频或透明 ProRes 4444 动效层。

### 4. 业务成片工作流

- `aivideoeditor-pre-roll`：独立本地前贴视频渲染，覆盖资产清单、Logo 选择、字幕模式、免责声明和预检，不依赖远程服务。
- `edit-soda-music-video`：汽水音乐竖屏数字人口播混剪，覆盖素材理解、去气口、Whisper 字幕、BGM、合规、品牌布局、导出和正式交付 QA。
- `edit-short-drama-packaging`：只处理过审短剧的轻包装，覆盖剧名审查与补齐、利益点避让、风险/AI 提示去重、无背景提示语、原尾板替换和横竖屏尾板拼接。

### 5. 衍生加工

- `aivideoeditor-video-fission`：本地视频裂变与素材重混，支持抽帧变体、前贴排列组合、文件夹组合和音视频配对输出。
- `aivideoeditor-video-compression`：独立视频压缩与转码，支持质量优先的编码选择、体积限制、报告输出和压缩后校验。

### 6. 分发自动化

- `aivideoeditor-usergrowth-automation`：UserGrowth 桌面自动上传，支持歌曲库匹配、Excel/CID 回填、素材标签、送审和诊断产物。
- `aivideoeditor-soda-music-upload`：汽水音乐 UserGrowth 上传、录入变色龙、送审、CID 回收和任务证据记录；不包含番茄打标或红果短剧流程。

## 能力链路

```text
运行环境
   ↓
素材获取 → 内容审核 → 素材理解与 Manifest
   ↓
通用渲染组件 → 业务成片
   ↓
视频裂变
   ↓
上传与分发
```

关键依赖：

| 调用方 | 必需能力 | 可选能力 | 推荐下一阶段 |
| --- | --- | --- | --- |
| `edit-soda-music-video` | `setup-video-editing-environment`、`manage-visual-asset-library` | `video-motion-effects` | `aivideoeditor-video-fission` |
| `aivideoeditor-pre-roll` | 无 | `manage-visual-asset-library`、`subtitle-motion-effects` | `aivideoeditor-video-fission` |
| `edit-short-drama-packaging` | 无 | `setup-video-editing-environment` | `aivideoeditor-video-fission` |
| `adxray-playlet-crawler` | 无 | `setup-video-editing-environment` | `aivideoeditor-visual-moderation` |
| `aivideoeditor-visual-moderation` | 无 | `setup-video-editing-environment` | `edit-short-drama-packaging` |
| `aivideoeditor-video-fission` | 无 | `setup-video-editing-environment` | `aivideoeditor-usergrowth-automation` |
| `mogong-gid-retrieval` | `douyin-video-toolkit` | 无 | `manage-visual-asset-library` |

完整的机器可读关系见 [`skill-catalog.yaml`](skill-catalog.yaml)。

## Skill Router

当前采用最小侵入的 SkillOS 方案：不重排 `skills/<skill-name>` 目录，不修改 `SKILL.md` frontmatter，也不改变同步到 Codex/WorkBuddy 的运行副本。路由只读取根目录的 [`skill-catalog.yaml`](skill-catalog.yaml)，先把用户意图缩小到少量候选 Skill，再交给 Agent 做最终判断。

每个 Skill 可以在 catalog 中补充以下可选路由元数据：

- `capability_path`：能力树路径，例如 `Video > Edit > Subtitle > MotionRenderer`。
- `tags`：短关键词，用于召回中文业务词、英文工具名和常见别名。
- `when_to_use`：正向触发场景。
- `when_not_use`：排除场景，用来降低相近 Skill 的误召回。
- `inputs` / `outputs`：粗粒度输入输出契约，详细门禁仍以对应 `SKILL.md` 为准。
- `quality`：仅在有真实观测数据时填写 `confidence` 或 `success_rate`，没有数据时保持缺省，不影响排序。

本地查看候选：

```bash
python3 scripts/sync_skills.py --route "做一个类似剪映字幕" --top 3
python3 scripts/sync_skills.py --route "查询魔工 gid 并导出 excel" --top 3
python3 scripts/sync_skills.py --route "下载 AdXRay 抖音热播短剧素材" --top 3
python3 scripts/sync_skills.py --route "审核短剧视频里的证件和 NSFW 风险" --top 3
python3 scripts/sync_skills.py --route "跑一个短剧从下载审核到包装的全流程" --top 5
```

输出会包含候选 Skill、能力路径、正向命中原因和 `when_not_use` 命中原因，方便定位 Skill Drift。

## 目录

```text
.
├── skill-catalog.yaml
├── scripts/
│   └── sync_skills.py
└── skills/
    ├── setup-video-editing-environment/
    ├── douyin-video-toolkit/
    ├── mogong-gid-retrieval/
    ├── adxray-playlet-crawler/
    ├── aivideoeditor-visual-moderation/
    ├── manage-visual-asset-library/
    ├── subtitle-motion-effects/
    ├── video-motion-effects/
    ├── aivideoeditor-pre-roll/
    ├── edit-soda-music-video/
    ├── edit-short-drama-packaging/
    ├── aivideoeditor-video-fission/
    ├── aivideoeditor-video-compression/
    ├── aivideoeditor-usergrowth-automation/
    └── aivideoeditor-soda-music-upload/
```

## 安装与同步

仓库中的 `skills/` 是唯一可信源。不要只修改 `~/.codex/skills` 或 `~/.workbuddy/skills` 中的运行副本。

克隆仓库后，先检查分类清单：

```bash
git clone git@github.com:liudu2326526/ai-cut-skills.git
cd ai-cut-skills
python3 scripts/sync_skills.py --check
python3 scripts/sync_skills.py --list
```

同步全部 Skill 到 Codex 和 WorkBuddy：

```bash
python3 scripts/sync_skills.py --runtime all
```

只同步一个运行时、分类或 Skill：

```bash
python3 scripts/sync_skills.py --runtime codex
python3 scripts/sync_skills.py --runtime codex --category production
python3 scripts/sync_skills.py --runtime workbuddy --skill edit-soda-music-video
```

按单 Skill 或分类同步时，脚本默认根据 `skill-catalog.yaml` 递归带上全部 `requires` 依赖。例如同步 `mogong-gid-retrieval` 会自动同步 `douyin-video-toolkit`。只有在明确管理依赖时才使用 `--no-dependencies`。

先预览操作：

```bash
python3 scripts/sync_skills.py --runtime all --dry-run
```

默认运行目录：

- Codex：`${CODEX_HOME:-$HOME/.codex}/skills`
- WorkBuddy：`${WORKBUDDY_HOME:-$HOME/.workbuddy}/skills`

可以通过 `--codex-skills-dir` 和 `--workbuddy-skills-dir` 覆盖。同步默认删除目标 Skill 内已经不在仓库中的旧文件，但会保留 `node_modules`、`__pycache__`、`.npm`、缓存目录和编译产物；需要保留所有旧文件时使用 `--no-delete`。

首次使用 Remotion 动效时，在实际运行目录安装锁定依赖：

```bash
node "${CODEX_HOME:-$HOME/.codex}/skills/video-motion-effects/scripts/remotion/render.mjs" setup
node "${WORKBUDDY_HOME:-$HOME/.workbuddy}/skills/video-motion-effects/scripts/remotion/render.mjs" setup
node "${CODEX_HOME:-$HOME/.codex}/skills/subtitle-motion-effects/scripts/remotion/render.mjs" setup
node "${WORKBUDDY_HOME:-$HOME/.workbuddy}/skills/subtitle-motion-effects/scripts/remotion/render.mjs" setup
```

各 Skill 的输入、输出和门禁规则请查看对应目录下的 `SKILL.md`。

## Pull Request 门禁

面向 `main` 的 PR 必须通过测试、语法检查、增量安全扫描和可信默认分支上的 AI 审查门禁。自动合并的信任边界、失败关闭策略及仓库变量见 [`docs/auto-merge.md`](docs/auto-merge.md)。
