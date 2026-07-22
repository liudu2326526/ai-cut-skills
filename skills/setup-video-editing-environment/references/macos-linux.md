# macOS 与 Linux 环境初始化

## macOS

```bash
SKILL_DIR="${CODEX_HOME:-$HOME/.codex}/skills/setup-video-editing-environment"
python3 "$SKILL_DIR/scripts/discover_environments.py" \
  --profile soda-scripted-render \
  --motion-effects auto

# 只有退出码为 2 时才安装：
brew install python@3.11 ffmpeg
python3.11 -m venv "$HOME/.virtualenvs/ai-video-editing"
source "$HOME/.virtualenvs/ai-video-editing/bin/activate"
python -m pip install --upgrade pip
python -m pip install -U openai-whisper
python -c 'import whisper; whisper.load_model("tiny")'
```

## Ubuntu/Debian

```bash
SKILL_DIR="${CODEX_HOME:-$HOME/.codex}/skills/setup-video-editing-environment"
python3 "$SKILL_DIR/scripts/discover_environments.py" \
  --profile soda-scripted-render \
  --motion-effects auto

# 只有退出码为 2 时才安装：
sudo apt-get update
sudo apt-get install -y python3 python3-venv python3-pip ffmpeg
python3 -m venv "$HOME/.virtualenvs/ai-video-editing"
source "$HOME/.virtualenvs/ai-video-editing/bin/activate"
python -m pip install --upgrade pip
python -m pip install -U openai-whisper
python -c 'import whisper; whisper.load_model("tiny")'
```

发现阶段会检查当前 Python、已激活环境、项目虚拟环境、`~/.virtualenvs`、`~/.venvs`、Conda 和 `PATH` 候选。环境名称不参与通过判断：任何业务环境只要满足目标 profile 都可以复用；任何环境即使名为 `ai-video-editing` 也必须先验证。

只有所有候选失败时才创建统一命名的 `~/.virtualenvs/ai-video-editing`。安装后保持同一 shell，确认 `command -v python ffmpeg ffprobe whisper`，再用该环境的 Python 运行 `scripts/check_environment.py`。

如果启用必需动效，额外安装 Node.js LTS、Chrome/Chromium 和 `video-motion-effects` Skill 的固定 Remotion 依赖。`auto` 模式缺失时允许静态回退。
