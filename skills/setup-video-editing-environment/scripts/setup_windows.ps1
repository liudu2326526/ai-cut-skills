[CmdletBinding()]
param(
    [ValidateSet("base-video", "soda-scripted-render", "soda-timeline-render", "soda-detect-pauses")]
    [string]$Profile = "soda-scripted-render",

    [ValidateSet("auto", "off", "required")]
    [string]$MotionEffects = "auto",

    [switch]$Install,
    [string]$EnvironmentName = "ai-video-editing",
    [string]$EnvironmentPath,
    [string]$ReportPath
)

$ErrorActionPreference = "Stop"

function Refresh-ProcessPath {
    $machine = [Environment]::GetEnvironmentVariable("Path", "Machine")
    $user = [Environment]::GetEnvironmentVariable("Path", "User")
    $env:Path = "$machine;$user"
}

function Get-PythonExecutable {
    $launcher = Get-Command py -ErrorAction SilentlyContinue
    if ($launcher) {
        foreach ($selector in @("-3.11", "-3")) {
            $path = & $launcher.Source $selector -c "import sys; print(sys.executable if sys.version_info >= (3, 10) else '')" 2>$null
            if ($LASTEXITCODE -eq 0 -and $path) {
                return $path.Trim()
            }
        }
    }
    foreach ($command in @("python", "python3")) {
        $python = Get-Command $command -ErrorAction SilentlyContinue
        if ($python) {
            $path = & $python.Source -c "import sys; print(sys.executable if sys.version_info >= (3, 10) else '')" 2>$null
            if ($LASTEXITCODE -eq 0 -and $path) {
                return $path.Trim()
            }
        }
    }
    return $null
}

function Install-WingetPackage {
    param([Parameter(Mandatory = $true)][string]$Id)
    $winget = Get-Command winget -ErrorAction SilentlyContinue
    if (-not $winget) {
        throw "WinGet is required for automatic Windows setup. Install or repair Microsoft App Installer first."
    }
    & $winget.Source install --id $Id --exact --source winget --accept-package-agreements --accept-source-agreements
    if ($LASTEXITCODE -ne 0) {
        throw "WinGet failed to install $Id. Run 'winget search $Id' and inspect the package source."
    }
    Refresh-ProcessPath
}

function Test-FfmpegCapabilities {
    $ffmpeg = Get-Command ffmpeg -ErrorAction SilentlyContinue
    $ffprobe = Get-Command ffprobe -ErrorAction SilentlyContinue
    if (-not $ffmpeg -or -not $ffprobe) {
        return $false
    }
    $filters = (& $ffmpeg.Source -hide_banner -filters 2>&1 | Out-String)
    $encoders = (& $ffmpeg.Source -hide_banner -encoders 2>&1 | Out-String)
    return (
        $filters.Contains("subtitles") -and
        $filters.Contains("loudnorm") -and
        $filters.Contains("ebur128") -and
        $encoders.Contains("libx264") -and
        $encoders.Contains("aac")
    )
}

function Find-ReusableEnvironment {
    param([Parameter(Mandatory = $true)][string]$BootstrapPython)
    $discoverScript = Join-Path $PSScriptRoot "discover_environments.py"
    $temporaryReport = [IO.Path]::GetTempFileName()
    try {
        & $BootstrapPython $discoverScript `
            --profile $Profile `
            --motion-effects $MotionEffects `
            --output-json $temporaryReport | Out-Null
        $discoveryExitCode = $LASTEXITCODE
        $discoveryReport = Get-Content $temporaryReport -Raw | ConvertFrom-Json
        return [PSCustomObject]@{
            ExitCode = $discoveryExitCode
            Report = $discoveryReport
        }
    }
    finally {
        Remove-Item $temporaryReport -Force -ErrorAction SilentlyContinue
    }
}

$bootstrapPython = Get-PythonExecutable
$pythonExe = $null
$discovery = $null

if ($bootstrapPython) {
    $discovery = Find-ReusableEnvironment -BootstrapPython $bootstrapPython
    if ($discovery.Report.ok) {
        $pythonExe = [string]$discovery.Report.selected_environment.python_executable
        Write-Host "Reusing capability-validated environment: $pythonExe"
    }
    elseif (-not $Install) {
        $discovery.Report | ConvertTo-Json -Depth 20
        [Console]::Error.WriteLine("No existing environment passed profile '$Profile'. Re-run with -Install to create '$EnvironmentName'.")
        exit 2
    }
}
elseif (-not $Install) {
    [Console]::Error.WriteLine("No Python 3.10+ bootstrap was found. Re-run with -Install to create '$EnvironmentName'.")
    exit 2
}

if (-not $pythonExe) {
    Write-Host "No reusable environment passed the capability checks. Installing '$EnvironmentName'."

    if (-not $bootstrapPython) {
        Install-WingetPackage -Id "Python.Python.3.11"
        $bootstrapPython = Get-PythonExecutable
        if (-not $bootstrapPython) {
            throw "Python was installed but is not visible in the current PowerShell. Reopen PowerShell and rerun this script."
        }
    }

    if (-not (Test-FfmpegCapabilities)) {
        Install-WingetPackage -Id "Gyan.FFmpeg"
    }

    if (-not $EnvironmentPath) {
        $EnvironmentPath = Join-Path (Join-Path $HOME ".virtualenvs") $EnvironmentName
    }
    $resolvedEnvironment = [IO.Path]::GetFullPath($EnvironmentPath)
    & $bootstrapPython -m venv $resolvedEnvironment
    if ($LASTEXITCODE -ne 0) {
        throw "Failed to create virtual environment at $resolvedEnvironment"
    }
    $pythonExe = Join-Path $resolvedEnvironment "Scripts\python.exe"

    & $pythonExe -m pip install --upgrade pip
    if ($LASTEXITCODE -ne 0) {
        throw "Failed to upgrade pip in $pythonExe"
    }

    if ($Profile -eq "soda-scripted-render") {
        & $pythonExe -m pip install -U openai-whisper
        if ($LASTEXITCODE -ne 0) {
            throw "Failed to install openai-whisper in $pythonExe"
        }
        & $pythonExe -c "import whisper; whisper.load_model('tiny')"
        if ($LASTEXITCODE -ne 0) {
            throw "Whisper installed but the tiny model could not be cached"
        }
    }

    if ($MotionEffects -eq "required") {
        if (-not (Get-Command node -ErrorAction SilentlyContinue)) {
            Install-WingetPackage -Id "OpenJS.NodeJS.LTS"
        }
        $chromeCandidates = @(
            "$env:ProgramFiles\Google\Chrome\Application\chrome.exe",
            "${env:ProgramFiles(x86)}\Google\Chrome\Application\chrome.exe",
            "$env:LOCALAPPDATA\Google\Chrome\Application\chrome.exe"
        )
        if (-not ($chromeCandidates | Where-Object { Test-Path $_ } | Select-Object -First 1)) {
            Install-WingetPackage -Id "Google.Chrome"
        }
    }
}

$scriptsDir = & $pythonExe -c "import sysconfig; print(sysconfig.get_path('scripts'))"
if ($LASTEXITCODE -ne 0 -or -not $scriptsDir) {
    throw "Could not resolve the Scripts directory for $pythonExe"
}
$env:Path = "$($scriptsDir.Trim());$env:Path"

$checkScript = Join-Path $PSScriptRoot "check_environment.py"
$arguments = @($checkScript, "--profile", $Profile, "--motion-effects", $MotionEffects)
if ($ReportPath) {
    $arguments += @("--output-json", [IO.Path]::GetFullPath($ReportPath))
}

Write-Host "Using Python: $pythonExe"
Write-Host "Current Scripts PATH: $($scriptsDir.Trim())"
& $pythonExe @arguments
exit $LASTEXITCODE
