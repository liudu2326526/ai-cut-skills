# Windows 环境初始化

## 支持范围

优先支持带 WinGet 的 Windows 10 1809+、Windows 11 和 Windows Server 2025。使用 64 位 Python 3.11；它满足剪辑 Skill 的 Python 3.10+ 要求，也处于 OpenAI Whisper 官方兼容范围内。

使用 PowerShell，不要把 Git Bash、WSL 和原生 Windows Python/FFmpeg 混在同一流程。路径包含中文或空格时始终使用引号和 PowerShell `&` 调用符。

## 推荐：先发现，再复用或安装

```powershell
$SkillDir = Join-Path $HOME ".codex\skills\setup-video-editing-environment"
$Workspace = "C:\workspace"

Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
& "$SkillDir\scripts\setup_windows.ps1" `
  -Profile soda-scripted-render `
  -MotionEffects auto `
  -Install `
  -EnvironmentName ai-video-editing `
  -ReportPath "$Workspace\video_environment.json"
```

脚本执行以下步骤：

1. 枚举当前 Python、已激活环境、项目虚拟环境、常见虚拟环境目录、Conda、Windows `py` 启动器和 `PATH` 中的候选；
2. 临时加入各候选的 Scripts 目录，逐个按目标 profile 做完整能力检查；
3. 首个返回 `ok=true` 的候选直接复用，不执行安装；
4. 仅当所有候选失败且指定 `-Install` 时，通过 WinGet 安装缺失的 Python 3.11 和 FFmpeg；
5. 创建默认的 `~\.virtualenvs\ai-video-editing`，安装 `openai-whisper` 并预下载 `tiny`；
6. 把选定 Python 的 Scripts 目录加入当前 PowerShell 的 `PATH`，再按 profile 复检。

省略 `-Install` 时只发现和检查，不改变机器；没有合格环境时退出码为 `2`。不要按业务名称定向搜索环境。业务环境如果通过通用来源被正常发现且通过能力检查就可以复用；同样不能因为名为 `ai-video-editing` 就跳过检查。

新环境统一命名为 `ai-video-editing`。需要覆盖默认位置时传入：

```powershell
-EnvironmentPath "D:\python-envs\ai-video-editing"
```

## 手动初始化

先确认 WinGet：

```powershell
winget --version
winget search --id Python.Python.3.11
winget search ffmpeg
```

安装基础依赖：

```powershell
winget install --id Python.Python.3.11 --exact --source winget
winget install --id Gyan.FFmpeg --exact --source winget
```

如果 WinGet 不可用，先从 Microsoft App Installer 安装/修复 WinGet。FFmpeg 也可以按 OpenAI Whisper 官方说明使用 Chocolatey 的 `choco install ffmpeg` 或 Scoop 的 `scoop install ffmpeg`。无论从哪个来源安装，最终都必须通过本 Skill 的滤镜和编码器检查。

先单独查看发现报告：

```powershell
$BootstrapPython = (& py -3.11 -c "import sys; print(sys.executable)").Trim()
& $BootstrapPython "$SkillDir\scripts\discover_environments.py" `
  --profile soda-scripted-render `
  --motion-effects auto `
  --output-json "$Workspace\video_environment_discovery.json"
```

如果退出码为 `2`，再创建统一环境并安装 Whisper：

```powershell
py -3.11 -m venv "$HOME\.virtualenvs\ai-video-editing"
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
& "$HOME\.virtualenvs\ai-video-editing\Scripts\Activate.ps1"

python -m pip install --upgrade pip
python -m pip install -U openai-whisper

$ScriptsDir = python -c "import sysconfig; print(sysconfig.get_path('scripts'))"
$env:Path = "$ScriptsDir;$env:Path"

where.exe python
where.exe ffmpeg
where.exe ffprobe
where.exe whisper
whisper --help
python -c "import whisper; whisper.load_model('tiny')"
```

安装或修改 `PATH` 后保持同一个 PowerShell 会话；新开终端时重新激活 `ai-video-editing`。若要显式验证某个不在常见目录中的业务环境，可向 `discover_environments.py` 重复传入 `--python C:\path\to\python.exe`；仍以能力检查结果为准。

## 动效环境

只有 `--motion-effects required` 才把下列依赖视为硬门槛：

```powershell
winget install --id OpenJS.NodeJS.LTS --exact --source winget
winget install --id Google.Chrome --exact --source winget
```

还必须安装 `video-motion-effects` Skill，并确保其 Remotion 项目已有固定的 `node_modules` 依赖。`auto` 模式缺失这些依赖时回退静态素材，不要为了基础渲染强制安装。

## 常见失败

- `whisper` 不在 `PATH`：把选定 Python 的 Scripts 目录加入当前会话，或重新激活选定环境。
- `No module named whisper`：CLI 与当前 Python 不属于同一环境；用当前 Python 重新安装。
- `tiny.pt` 不存在：运行 `python -c "import whisper; whisper.load_model('tiny')"` 预下载。
- FFmpeg 缺少 `subtitles`：当前 Windows build 没有 libass，换用包含 libass 的完整 build。
- PowerShell 禁止脚本：仅对当前进程运行 `Set-ExecutionPolicy -Scope Process Bypass`，不要无理由修改全局策略。
- WinGet 安装后仍找不到命令：刷新当前进程 PATH 或重新打开 PowerShell，再复检。
