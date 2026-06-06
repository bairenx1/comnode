# ═══════════════════════════════════════════════════════════════
#  ComfyUI NodeStudio — 在线安装脚本 (Windows PowerShell)
#  用法: irm <RAW_URL> | iex
# ═══════════════════════════════════════════════════════════════

$ErrorActionPreference = "Stop"

$REPO_URL   = "https://github.com/bairenx1/comnode.git"
$REPO_ZIP   = "https://github.com/bairenx1/comnode/archive/refs/heads/master.zip"
$INSTALL_DIR = "$env:USERPROFILE\comfyui-nodestudio"

Clear-Host

# ── 欢迎横幅 ──
Write-Host @"

  ╔══════════════════════════════════════════════╗
  ║                                              ║
  ║   ComfyUI NodeStudio                         ║
  ║   AI 图像生成工作流 — 一键在线安装            ║
  ║                                              ║
  ╚══════════════════════════════════════════════╝

"@ -ForegroundColor Cyan

# ── 系统检测 ──
Write-Host "  $([char]0x2022) 操作系统: Windows" -NoNewline
$arch = (Get-WmiObject Win32_OperatingSystem).OSArchitecture
Write-Host " ($arch)"

# ── 检查 Python ──
Write-Host "  $([char]0x2022) 检查 Python 环境..."

$pythonCmd = $null
try {
    $pyVer = python --version 2>&1
    if ($pyVer -match "Python (\d+)\.(\d+)") {
        $major = [int]$Matches[1]
        $minor = [int]$Matches[2]
        if ($major -ge 3 -and $minor -ge 10) {
            $pythonCmd = "python"
        }
    }
} catch {}

if (-not $pythonCmd) {
    Write-Host "  $([char]0x2022) 未找到 Python 3.11+, 尝试通过 winget 自动安装..."

    try {
        winget install Python.Python.3.11 --accept-package-agreements --accept-source-agreements --scope user *>$null
        # winget 安装后需要刷新 PATH
        $env:Path = [System.Environment]::GetEnvironmentVariable("Path","Machine") + ";" +
                    [System.Environment]::GetEnvironmentVariable("Path","User")

        # 尝试验证
        try { python --version *>$null; $pythonCmd = "python" }
        catch {
            # 安装完成但需要重启 shell
            Write-Host @"

  Python 安装完成！
  请关闭此窗口，然后重新运行安装命令:
    irm <RAW_URL>/setup.ps1 | iex

"@ -ForegroundColor Green
            exit 0
        }
    } catch {
        Write-Host @"

  ❌ Python 自动安装失败。请手动安装:
     1. 打开 https://www.python.org/downloads/
     2. 下载 Python 3.11+ 安装包
     3. 安装时务必勾选 "Add Python to PATH"
     4. 重新运行本脚本

"@ -ForegroundColor Red
        exit 1
    }
}

Write-Host "  ✅ Python: $(python --version 2>&1)"

# ── 下载项目 ──
Write-Host ""
Write-Host "  $([char]0x2022) 下载项目文件..."

if (Test-Path $INSTALL_DIR) {
    Write-Host "  $([char]0x2022) 目录已存在: $INSTALL_DIR"
    if (Get-Command git -ErrorAction SilentlyContinue) {
        if (Test-Path "$INSTALL_DIR\.git") {
            Write-Host "  ➜ 更新已有项目 (git pull)..."
            Set-Location $INSTALL_DIR
            git pull --ff-only 2>$null
            Set-Location $PSScriptRoot
        }
    } else {
        Write-Host "  $([char]0x2022) 使用现有文件"
    }
} else {
    if (Get-Command git -ErrorAction SilentlyContinue) {
        Write-Host "  ➜ git clone $REPO_URL"
        git clone --depth 1 $REPO_URL $INSTALL_DIR
    } else {
        Write-Host "  ➜ 下载 zip 包..."
        $zipPath = "$env:TEMP\nodestudio.zip"
        $extractPath = "$env:TEMP\nodestudio_extract"

        [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
        Invoke-WebRequest -Uri $REPO_ZIP -OutFile $zipPath

        Expand-Archive -Path $zipPath -DestinationPath $extractPath -Force

        # zip 解压后有一层包装目录，移出内容
        $innerDir = Get-ChildItem $extractPath | Select-Object -First 1
        Move-Item "$($innerDir.FullName)\*" $INSTALL_DIR -Force

        Remove-Item $zipPath -Force
        Remove-Item $extractPath -Recurse -Force
    }
}

Write-Host "  ✅ 项目路径: $INSTALL_DIR"

# ── 创建虚拟环境 ──
Write-Host ""
Write-Host "  $([char]0x2022) 创建 Python 虚拟环境..."
$VENV_DIR = "$INSTALL_DIR\ComfyUI\.venv"
if (-not (Test-Path "$VENV_DIR\Scripts\python.exe")) {
    python -m venv $VENV_DIR
}
Write-Host "  ✅ 虚拟环境已就绪"

# ── 运行安装向导 ──
Write-Host ""
Write-Host "  ═══ 运行 GPU 检测与依赖安装 ═══" -ForegroundColor Cyan
Write-Host ""

$installScript = "$INSTALL_DIR\ComfyUI\install.py"
& "$VENV_DIR\Scripts\python.exe" $installScript

if ($LASTEXITCODE -ne 0) {
    Write-Host ""
    Write-Host "  ❌ 安装未完全成功，请查看上方日志。" -ForegroundColor Red
    Read-Host "按回车键退出"
    exit 1
}

# ── 完成 ──
Write-Host @"

  ═══════════════════════════════════════
   安装完成！
  ═══════════════════════════════════════

  启动方式:
    双击 $INSTALL_DIR\ComfyUI\start_comfyui_and_webui.bat

  启动后访问: http://127.0.0.1:8288

"@ -ForegroundColor Green

Read-Host "按回车键退出"
