# AI Cut Skills

面向 Codex 的视频剪辑 Skill 集合，目前包含：

- `edit-soda-music-video`：汽水音乐竖屏数字人口播混剪，覆盖去气口、倍速、字幕、素材、BGM、合规、导出和 QA。
- `video-motion-effects`：基于 Remotion 的五种图片入场动效，可输出合成视频或透明 ProRes 4444 动效层。

## 目录

```text
skills/
├── edit-soda-music-video/
└── video-motion-effects/
```

## 安装

克隆仓库后，将需要的 Skill 复制到 Codex Skill 目录：

```bash
git clone git@github.com:liudu2326526/ai-cut-skills.git
mkdir -p "${CODEX_HOME:-$HOME/.codex}/skills"
cp -R ai-cut-skills/skills/edit-soda-music-video "${CODEX_HOME:-$HOME/.codex}/skills/"
cp -R ai-cut-skills/skills/video-motion-effects "${CODEX_HOME:-$HOME/.codex}/skills/"
```

首次使用 Remotion 动效时安装锁定依赖：

```bash
node "${CODEX_HOME:-$HOME/.codex}/skills/video-motion-effects/scripts/remotion/render.mjs" setup
```

各 Skill 的完整使用方式和输入约定请查看对应目录下的 `SKILL.md`。

