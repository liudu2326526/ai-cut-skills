# AI Cut Skills

面向 Codex 与 WorkBuddy 的视频剪辑 Skill 集合，目前包含：

- `setup-video-editing-environment`：Windows PowerShell 优先的跨平台剪辑环境发现、复用、安装和复检，覆盖 Python、FFmpeg/FFprobe、Whisper 与可选动效依赖。
- `manage-visual-asset-library`：跨项目图片/视频入库、Read 内容理解、有效区域标注、Manifest 校验和语义候选报告。
- `edit-soda-music-video`：汽水音乐竖屏数字人口播混剪，覆盖去气口、倍速、字幕、素材、BGM、合规、导出和 QA。
- `video-motion-effects`：基于 Remotion 的五种图片入场动效，可输出合成视频或透明 ProRes 4444 动效层。

## 目录

```text
skills/
├── setup-video-editing-environment/
├── manage-visual-asset-library/
├── edit-soda-music-video/
└── video-motion-effects/
```

## 安装

仓库中的 `skills/` 是唯一可信源。克隆或更新仓库后，用同一份仓库内容同步 Codex 与 WorkBuddy，避免两个运行时加载到不同版本：

```bash
git clone git@github.com:liudu2326526/ai-cut-skills.git
CODEX_SKILLS="${CODEX_HOME:-$HOME/.codex}/skills"
WORKBUDDY_SKILLS="${WORKBUDDY_HOME:-$HOME/.workbuddy}/skills"
mkdir -p "$CODEX_SKILLS" "$WORKBUDDY_SKILLS"

rsync -a --delete ai-cut-skills/skills/setup-video-editing-environment/ "$CODEX_SKILLS/setup-video-editing-environment/"
rsync -a --delete ai-cut-skills/skills/setup-video-editing-environment/ "$WORKBUDDY_SKILLS/setup-video-editing-environment/"
rsync -a --delete ai-cut-skills/skills/manage-visual-asset-library/ "$CODEX_SKILLS/manage-visual-asset-library/"
rsync -a --delete ai-cut-skills/skills/manage-visual-asset-library/ "$WORKBUDDY_SKILLS/manage-visual-asset-library/"
rsync -a --delete ai-cut-skills/skills/edit-soda-music-video/ "$CODEX_SKILLS/edit-soda-music-video/"
rsync -a --delete ai-cut-skills/skills/edit-soda-music-video/ "$WORKBUDDY_SKILLS/edit-soda-music-video/"
rsync -a --delete --exclude='node_modules/' ai-cut-skills/skills/video-motion-effects/ "$CODEX_SKILLS/video-motion-effects/"
rsync -a --delete --exclude='node_modules/' ai-cut-skills/skills/video-motion-effects/ "$WORKBUDDY_SKILLS/video-motion-effects/"
```

首次使用 Remotion 动效时，在实际运行时目录安装锁定依赖：

```bash
node "${CODEX_HOME:-$HOME/.codex}/skills/video-motion-effects/scripts/remotion/render.mjs" setup
node "${WORKBUDDY_HOME:-$HOME/.workbuddy}/skills/video-motion-effects/scripts/remotion/render.mjs" setup
```

每次同步后可用 `diff -qr` 比较仓库 Skill 与对应运行时副本；不应直接只修改 `~/.codex/skills` 或 `~/.workbuddy/skills` 中的单独副本。

各 Skill 的完整使用方式和输入约定请查看对应目录下的 `SKILL.md`。
