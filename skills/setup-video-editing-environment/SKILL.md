---
name: setup-video-editing-environment
description: Discover, reuse, install, diagnose, or verify cross-platform AI video-editing runtimes, with Windows PowerShell as the primary workflow and macOS/Linux support. Validates existing environments by capability before installing the uniformly named ai-video-editing environment. Covers Python 3.10+, FFmpeg/FFprobe, OpenAI Whisper CLI and tiny model cache, Soda editing Skill dependencies, and optional Node/Chrome/Remotion motion effects. Use when Whisper、FFmpeg、ffprobe、Python、Node、Chrome、Remotion 缺失，Windows 剪辑环境初始化，或运行 edit-soda-music-video 前需要发现、安装或检查依赖。
---

# 视频剪辑环境安装

## 核心边界

先发现已有环境，再决定是否安装。候选可以来自当前 Python、已激活环境、项目虚拟环境、`~/.virtualenvs`、`~/.venvs`、Conda、Windows `py` 启动器和 `PATH`。逐个运行目标 profile 的完整检查；只复用 `ok=true` 的候选。

按能力而不是环境名称判断。不要按业务名称定向搜索、直接采用或排除环境；即使名为 `ai-video-editing` 也必须通过检查。若所有候选均不合格，再创建统一命名的 `ai-video-editing`；默认路径为 `~/.virtualenvs/ai-video-editing`，调用方可显式覆盖。

环境检查是只读操作，可以直接执行。安装 Python、FFmpeg、Whisper、Node 或 Chrome 会改变机器状态；仅在用户明确要求安装/初始化时执行。需要管理员权限、PowerShell 执行策略、sudo 或网络下载时，先说明影响并取得所需权限。

不要声称“环境可用”直到 `scripts/check_environment.py` 对目标 profile 返回 `ok=true`。安装日志和环境报告写入任务工作区，不写回本 Skill。

## Profile 选择

| Profile | 必需能力 |
| --- | --- |
| `base-video` | Python 3.10+、FFmpeg/FFprobe 及规定滤镜/编码器 |
| `soda-scripted-render` | 基础能力、Whisper CLI、当前 Python 的 Whisper 包、已缓存 tiny、`manage-visual-asset-library` |
| `soda-timeline-render` | 基础能力、`manage-visual-asset-library`；Whisper 仅报告不阻断 |
| `soda-detect-pauses` | 基础能力；Whisper 缺失时允许退化为音量检测 |

动效另用 `--motion-effects auto/off/required` 控制。`auto` 缺失时静态回退；`required` 额外要求 `video-motion-effects`、Node、Chrome 和 Remotion 依赖齐全。

## 执行流程

1. 检测操作系统。Windows 必须先完整阅读 [windows.md](references/windows.md)；macOS/Linux 阅读 [macos-linux.md](references/macos-linux.md)。
2. 根据目标剪辑流程选择 profile，不要默认把 Whisper 设为可选。提供口播台词并依赖实际词级时间戳时，使用 `soda-scripted-render`。
3. 使用任一可运行的 Python 3.10+ 执行 `scripts/discover_environments.py`。候选的 Python Scripts 目录会临时加入检查进程的 `PATH`，避免把“未激活”误判为“不可用”。
4. 如果发现 `ok=true` 的候选，直接复用报告里的 `selected_environment.python_executable`，不要重复安装。
5. 如果用户只要求诊断且没有合格候选，交付候选检查结果、缺失项和建议命令，不执行安装。
6. 如果用户明确要求初始化且没有合格候选，按平台文档创建 `ai-video-editing` 并安装缺失依赖。Windows 优先运行带 `-Install` 的 `setup_windows.ps1`。
7. 使用选定 Python 和同一终端再次运行 `scripts/check_environment.py`。只有 `ok=true`、`errors=[]` 才交付环境。

## Windows 快速入口

在 PowerShell 中执行：

```powershell
$SkillDir = Join-Path $HOME ".codex\skills\setup-video-editing-environment"
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass

& "$SkillDir\scripts\setup_windows.ps1" `
  -Profile soda-scripted-render `
  -MotionEffects auto `
  -Install `
  -EnvironmentName ai-video-editing `
  -ReportPath "C:\workspace\video_environment.json"
```

脚本始终先发现并验证已有环境；发现合格候选时，即使带 `-Install` 也不会重复安装。只有无候选合格且带 `-Install` 时，才创建 `~\.virtualenvs\ai-video-editing`。可用 `-EnvironmentPath` 显式覆盖新环境路径。继续在同一个 PowerShell 会话中运行后续剪辑命令，以继承脚本设置的 `PATH`。

## macOS/Linux 快速入口

```bash
SKILL_DIR="${CODEX_HOME:-$HOME/.codex}/skills/setup-video-editing-environment"
python3 "$SKILL_DIR/scripts/discover_environments.py" \
  --profile soda-scripted-render \
  --motion-effects auto \
  --output-json /absolute/path/video_environment.json
```

退出码为 `0` 表示已选出可复用环境；退出码为 `2` 表示所有候选均不合格，明确要求安装时再按 [macos-linux.md](references/macos-linux.md) 初始化。安装完成后用新环境的 Python 运行 `check_environment.py` 复检。

## 交付

列出操作系统、profile、发现过的候选、最终 Python 可执行文件、复用或新建结论、FFmpeg/FFprobe 路径与能力、Whisper CLI/包/tiny 缓存状态、通用素材 Skill、动效环境、执行过的安装命令、环境报告路径以及仍需用户处理的权限或重启事项。
