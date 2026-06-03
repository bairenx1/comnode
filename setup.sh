#!/usr/bin/env bash
# ═══════════════════════════════════════════════════════════════
#  ComfyUI NodeStudio — 在线安装脚本 (Mac / Linux)
#  用法: curl -fsSL <RAW_URL> | bash
# ═══════════════════════════════════════════════════════════════
set -e

# ── 颜色 ──
RED="\033[31m"; GREEN="\033[32m"; YELLOW="\033[33m"
CYAN="\033[36m"; BOLD="\033[1m"; DIM="\033[2m"; RESET="\033[0m"
CHECK="✅"; CROSS="❌"; DOT="•"; ARROW="➜"

REPO_URL="https://github.com/USER/comfyui-nodestudio.git"
REPO_ZIP="https://github.com/USER/comfyui-nodestudio/archive/refs/heads/main.zip"
INSTALL_DIR="$HOME/comfyui-nodestudio"

clear

# ── 欢迎横幅 ──
echo -e "${CYAN}${BOLD}"
echo "  ╔══════════════════════════════════════════════╗"
echo "  ║                                              ║"
echo "  ║   ${RESET}ComfyUI NodeStudio${CYAN}                          ║"
echo "  ║   ${DIM}AI 图像生成工作流 — 一键在线安装${CYAN}              ║"
echo "  ║                                              ║"
echo "  ╚══════════════════════════════════════════════╝"
echo -e "${RESET}\n"

# ── 系统检测 ──
OS="$(uname)"
echo -e "  ${DOT} 操作系统: ${BOLD}${OS}${RESET}"

if [[ "$OS" != "Darwin" && "$OS" != "Linux" ]]; then
    echo -e "  ${CROSS} ${RED}不支持的操作系统: ${OS}${RESET}"
    echo -e "  ${ARROW} Windows 用户请使用 PowerShell 安装:"
    echo -e "      ${CYAN}irm <RAW_URL>/setup.ps1 | iex${RESET}"
    exit 1
fi

# ── 检查 Python ──
echo -e "  ${DOT} 检查 Python 环境..."
PYTHON_BIN=""
if command -v python3.11 &>/dev/null; then
    PYTHON_BIN="python3.11"
elif command -v python3 &>/dev/null; then
    PY_VER=$(python3 -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')")
    PY_MAJ=$(echo "$PY_VER" | cut -d. -f1)
    PY_MIN=$(echo "$PY_VER" | cut -d. -f2)
    if [[ "$PY_MAJ" -ge 3 && "$PY_MIN" -ge 10 ]]; then
        PYTHON_BIN="python3"
    else
        echo -e "  ${CROSS} Python 版本 ${PY_VER} 过低，需要 >= 3.11"
        PYTHON_BIN=""
    fi
fi

if [[ -z "$PYTHON_BIN" ]]; then
    echo -e "  ${DOT} 未找到 Python 3.11+，尝试自动安装..."
    if [[ "$OS" == "Darwin" ]]; then
        if command -v brew &>/dev/null; then
            echo -e "  ${ARROW} brew install python@3.11"
            brew install python@3.11
            PYTHON_BIN="python3.11"
        else
            echo -e "  ${CROSS} ${RED}未安装 Homebrew${RESET}"
            echo -e "  请先安装 Homebrew:"
            echo -e "    ${CYAN}/bin/bash -c \"\$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)\"${RESET}"
            echo -e "  然后重新运行本脚本。"
            exit 1
        fi
    else
        # Linux — 尝试 apt / dnf / pacman
        if command -v apt-get &>/dev/null; then
            sudo apt-get update -qq && sudo apt-get install -y -qq python3.11 python3.11-venv python3-pip
            PYTHON_BIN="python3.11"
        elif command -v dnf &>/dev/null; then
            sudo dnf install -y python3.11
            PYTHON_BIN="python3.11"
        elif command -v pacman &>/dev/null; then
            sudo pacman -S --noconfirm python
            PYTHON_BIN="python3"
        else
            echo -e "  ${CROSS} ${RED}无法自动安装 Python，请手动安装 3.11+${RESET}"
            exit 1
        fi
    fi
fi

echo -e "  ${CHECK} Python: $($PYTHON_BIN --version 2>&1)"

# ── 下载项目 ──
echo -e "\n  ${DOT} 下载项目文件..."

if [[ -d "$INSTALL_DIR" ]]; then
    echo -e "  ${DOT} 目录已存在: ${INSTALL_DIR}"
    echo -e "  ${ARROW} 更新已有项目 (git pull)..."
    if command -v git &>/dev/null && [[ -d "$INSTALL_DIR/.git" ]]; then
        cd "$INSTALL_DIR"
        git pull --ff-only 2>/dev/null || echo -e "  ${DOT} 无法拉取，使用现有文件"
        cd - >/dev/null
    else
        echo -e "  ${DOT} 使用现有文件"
    fi
else
    if command -v git &>/dev/null; then
        echo -e "  ${ARROW} git clone ${REPO_URL}"
        git clone --depth 1 "$REPO_URL" "$INSTALL_DIR" 2>&1 | while read line; do
            echo -e "    ${DIM}${line}${RESET}"
        done
    elif command -v curl &>/dev/null; then
        echo -e "  ${ARROW} 下载 zip 包..."
        curl -fsSL "$REPO_ZIP" -o /tmp/nodestudio.zip
        mkdir -p "$INSTALL_DIR"
        unzip -qo /tmp/nodestudio.zip -d /tmp/nodestudio_extract
        mv /tmp/nodestudio_extract/*/* "$INSTALL_DIR/" 2>/dev/null || true
        rm -rf /tmp/nodestudio.zip /tmp/nodestudio_extract
    else
        echo -e "  ${CROSS} ${RED}需要 git 或 curl 来下载项目${RESET}"
        exit 1
    fi
fi

echo -e "  ${CHECK} 项目路径: ${BOLD}${INSTALL_DIR}${RESET}"

# ── 创建虚拟环境 ──
echo -e "\n  ${DOT} 创建 Python 虚拟环境..."
VENV_DIR="$INSTALL_DIR/ComfyUI/.venv"
if [[ ! -f "$VENV_DIR/bin/python" ]]; then
    $PYTHON_BIN -m venv "$VENV_DIR"
fi
echo -e "  ${CHECK} 虚拟环境已就绪"

# ── 运行安装向导 ──
echo -e "\n${CYAN}${BOLD}  ═══ 运行 GPU 检测与依赖安装 ═══${RESET}\n"
cd "$INSTALL_DIR/ComfyUI"
"$VENV_DIR/bin/python" install.py
INSTALL_EXIT=$?

if [[ $INSTALL_EXIT -ne 0 ]]; then
    echo -e "\n  ${CROSS} ${RED}安装未完全成功，请查看上方日志。${RESET}"
    exit 1
fi

# ── 完成 ──
echo -e "\n${GREEN}${BOLD}  ═══════════════════════════════════════${RESET}"
echo -e "${GREEN}${BOLD}   安装完成！${RESET}"
echo -e "${GREEN}${BOLD}  ═══════════════════════════════════════${RESET}\n"
echo -e "  ${BOLD}启动方式:${RESET}"
echo -e "    cd ${INSTALL_DIR}/ComfyUI"
echo -e "    ${CYAN}bash start_comfyui_and_webui.command${RESET}  (Mac)"
echo -e "    ${CYAN}bash start_comfyui_and_webui.sh${RESET}       (Linux)"
echo -e "\n  ${BOLD}启动后访问:${RESET} ${CYAN}http://127.0.0.1:8288${RESET}\n"
