#!/usr/bin/env bash
set -e

ROOT_DIR="$(cd "$(dirname "$0")" && pwd)"
VENV_DIR="$ROOT_DIR/.venv"
VENV_PYTHON="$VENV_DIR/bin/python"
COMFY_PORT=8188
COMFY_LISTEN="127.0.0.1"
WEBUI_PORT=8288
WEBUI_HOST="127.0.0.1"

clear
echo
echo "============================================"
echo "  ComfyUI NodeStudio — 启动中..."
echo "============================================"
echo

# --- Python 检测与自动安装 ---
if ! command -v python3 &>/dev/null && ! command -v python &>/dev/null; then
    echo "[*] Python 未找到"

    if command -v brew &>/dev/null; then
        echo "    正在通过 Homebrew 自动安装 Python 3.11..."
        brew install python@3.11
        if command -v python3.11 &>/dev/null; then
            PYTHON_BIN="python3.11"
            echo "[+] Python 3.11 安装完成"
        else
            echo "[X] 自动安装失败，请手动安装: https://www.python.org/downloads/"
            read -p "按回车键退出..." dummy
            exit 1
        fi
    else
        echo
        echo "❌ 未找到 Python 且没有 Homebrew"
        echo
        echo "请先安装 Homebrew (复制下面命令到终端运行):"
        echo '  /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"'
        echo
        echo "然后重新运行本脚本，会自动通过 brew 安装 Python"
        read -p "按回车键退出..." dummy
        exit 1
    fi
else
    PYTHON_BIN=$(command -v python3 || command -v python)
fi

if [ ! -f "$VENV_PYTHON" ]; then
    echo "[*] 创建虚拟环境..."
    $PYTHON_BIN -m venv "$VENV_DIR"
fi

# 运行安装向导（GPU 检测 + PyTorch + 依赖）
echo
"$VENV_PYTHON" "$ROOT_DIR/install.py"
if [ $? -ne 0 ]; then
    echo
    echo "[X] 安装过程中出现问题，请查看上方错误信息。"
    read -p "按回车键退出..." dummy
    exit 1
fi

# 后台启动 ComfyUI 后端
cd "$ROOT_DIR"
echo
echo "============================================"
echo "  启动 ComfyUI 后端 (端口 $COMFY_PORT)..."
echo "============================================"
echo
"$VENV_PYTHON" main.py \
    --listen "$COMFY_LISTEN" \
    --port "$COMFY_PORT" \
    --disable-auto-launch \
    --enable-assets \
    --enable-cors-header \
    --front-end-root "$ROOT_DIR/custom_webui/frontend" &
COMFY_PID=$!

sleep 3

echo "启动 NodeStudio WebUI (端口 $WEBUI_PORT)..."
COMFY_BASE_URL="http://$COMFY_LISTEN:$COMFY_PORT" "$VENV_PYTHON" -m custom_webui.backend.run &
WEBUI_PID=$!

sleep 2

echo
echo "============================================"
echo "  所有服务已启动！"
echo "  - ComfyUI:     http://127.0.0.1:$COMFY_PORT"
echo "  - NodeStudio:  http://127.0.0.1:$WEBUI_PORT"
echo "============================================"
echo

# 打开浏览器
if command -v open &>/dev/null; then
    open "http://$WEBUI_HOST:$WEBUI_PORT"
elif command -v xdg-open &>/dev/null; then
    xdg-open "http://$WEBUI_HOST:$WEBUI_PORT" &>/dev/null &
fi

# Ctrl+C 或关闭终端时停止服务
cleanup() {
    echo
    echo "正在关闭所有服务..."
    kill $COMFY_PID 2>/dev/null
    kill $WEBUI_PID 2>/dev/null
    wait
    echo "已退出。"
}
trap cleanup EXIT INT TERM

wait
