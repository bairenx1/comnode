@echo off
setlocal

set "ROOT_DIR=%~dp0"
set "VENV_DIR=%ROOT_DIR%.venv"
set "VENV_PYTHON=%VENV_DIR%\Scripts\python.exe"
set "COMFY_PORT=8188"
set "COMFY_LISTEN=127.0.0.1"
set "WEBUI_PORT=8288"
set "WEBUI_HOST=127.0.0.1"

echo.
echo ============================================
echo   ComfyUI NodeStudio - 启动中...
echo ============================================
echo.

where python >nul 2>nul
if errorlevel 1 (
    echo [*] Python 未找到，尝试通过 winget 自动安装...
    echo.
    winget install Python.Python.3.11 --accept-package-agreements --accept-source-agreements --scope user 2>nul
    if errorlevel 1 (
        echo [X] 自动安装失败。请手动安装 Python 3.11+：
        echo     https://www.python.org/downloads/
        echo     安装时务必勾选 "Add Python to PATH"
        echo.
        pause
        exit /b 1
    )
    echo.
    echo [+] Python 安装完成！请关闭此窗口，然后重新双击 bat 文件启动。
    echo.
    pause
    exit /b 0
)

if not exist "%VENV_DIR%\Scripts\python.exe" (
    echo [*] 创建虚拟环境...
    python -m venv "%VENV_DIR%"
    if errorlevel 1 (
        echo [X] 虚拟环境创建失败
        pause & exit /b 1
    )
)

REM --- 运行安装向导（GPU 检测 + PyTorch + 依赖） ---
echo.
"%VENV_PYTHON%" "%ROOT_DIR%install.py"
if errorlevel 1 (
    echo.
    echo [X] 安装过程中出现问题，请查看上方错误信息。
    pause
    exit /b 1
)

REM --- 启动 ComfyUI 后端 ---
echo.
echo ============================================
echo  启动 ComfyUI 后端 (端口 %COMFY_PORT%)...
echo ============================================
echo.
start "ComfyUI-Backend" cmd /k "cd /d "%ROOT_DIR%" && "%VENV_PYTHON%" main.py --listen %COMFY_LISTEN% --port %COMFY_PORT% --disable-auto-launch --enable-assets --enable-cors-header --front-end-root "%ROOT_DIR%custom_webui\frontend""

timeout /t 3 /nobreak >nul

echo 启动 WebUI (端口 %WEBUI_PORT%)...
start "ComfyUI-Custom-WebUI" cmd /k "cd /d "%ROOT_DIR%" && set COMFY_BASE_URL=http://%COMFY_LISTEN%:%COMFY_PORT% && "%VENV_PYTHON%" -m custom_webui.backend.run"

timeout /t 2 /nobreak >nul

echo.
echo ============================================
echo  所有服务已启动！
echo  - ComfyUI:     http://127.0.0.1:%COMFY_PORT%
echo  - NodeStudio:  http://127.0.0.1:%WEBUI_PORT%
echo ============================================
echo.
start "" "http://%WEBUI_HOST%:%WEBUI_PORT%"

endlocal
