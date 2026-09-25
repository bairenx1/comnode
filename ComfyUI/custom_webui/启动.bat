@echo off
cd /d "%~dp0"
echo.
echo ============================================
echo   NodeStudio 启动中...
echo ============================================
echo.
echo ComfyUI 地址: http://127.0.0.1:8188
echo WebUI   地址: http://127.0.0.1:8288
echo.
python -m backend.run
pause
