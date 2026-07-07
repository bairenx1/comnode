@echo off
setlocal

set "ROOT_DIR=%~dp0"
set "ROOT_DIR=%ROOT_DIR:~0,-1%"
set "VENV_DIR=%ROOT_DIR%\.venv"
set "VENV_PYTHON=%VENV_DIR%\Scripts\python.exe"
set "COMFY_PORT=8188"
set "COMFY_LISTEN=127.0.0.1"
set "WEBUI_PORT=8288"
set "WEBUI_HOST=127.0.0.1"
set "INSTALL_FLAG=%ROOT_DIR%\.install_done"

echo.
echo ============================================
echo   ComfyUI NodeStudio
echo ============================================
echo.

REM --- 检查 Python ---
where python >nul 2>nul
if errorlevel 1 (
    echo [X] 未找到 Python，请先安装 Python 3.11+
    echo     https://www.python.org/downloads/
    pause
    exit /b 1
)

REM --- 创建虚拟环境（仅首次） ---
if not exist "%VENV_PYTHON%" (
    echo [*] 首次运行，创建虚拟环境...
    python -m venv "%VENV_DIR%"
    if errorlevel 1 (
        echo [X] 虚拟环境创建失败
        pause & exit /b 1
    )
    echo [+] 虚拟环境创建完成
)

REM --- 安装依赖（仅首次，之后跳过；想重装就删掉 .install_done 文件） ---
if not exist "%INSTALL_FLAG%" (
    echo.
    echo [*] 安装依赖中，请耐心等待...
    "%VENV_PYTHON%" "%ROOT_DIR%\install.py"
    if errorlevel 1 (
        echo [X] 安装失败，查看上方错误信息
        pause & exit /b 1
    )
    echo > "%INSTALL_FLAG%"
    echo [+] 依赖安装完成
) else (
    echo [+] 环境已就绪，跳过安装
)

REM --- 启动 ComfyUI ---
echo.
echo [*] 启动 ComfyUI 后端 (端口 %COMFY_PORT%)...
start "ComfyUI" cmd /k "cd /d "%ROOT_DIR%" && "%VENV_PYTHON%" main.py --listen %COMFY_LISTEN% --port %COMFY_PORT% --disable-auto-launch --enable-assets --enable-cors-header"

REM --- 等 ComfyUI 启动 ---
echo [*] 等待 ComfyUI 启动 (10秒)...
timeout /t 10 /nobreak >nul

REM --- 启动 WebUI ---
echo [*] 启动 NodeStudio (端口 %WEBUI_PORT%)...
start "NodeStudio" cmd /k "cd /d "%ROOT_DIR%" && set COMFY_BASE_URL=http://%COMFY_LISTEN%:%COMFY_PORT% && "%VENV_PYTHON%" -m custom_webui.backend.run"

timeout /t 2 /nobreak >nul

echo.
echo ============================================
echo   ComfyUI:     http://127.0.0.1:%COMFY_PORT%
echo   NodeStudio:  http://127.0.0.1:%WEBUI_PORT%
echo ============================================
echo.
start "" "http://%WEBUI_HOST%:%WEBUI_PORT%"

endlocal
