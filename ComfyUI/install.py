#!/usr/bin/env python3
"""
ComfyUI NodeStudio — 一键安装向导
自动检测 GPU、选择正确的 PyTorch 版本、安装依赖并验证环境。
纯标准库实现，无需额外依赖。
"""
import subprocess, sys, os, platform, re, shutil, urllib.request, json
from pathlib import Path

# ── ANSI 终端样式 ──────────────────────────────────────────────
BOLD = "\033[1m"; DIM = "\033[2m"; RESET = "\033[0m"
RED = "\033[31m"; GREEN = "\033[32m"; YELLOW = "\033[33m"
BLUE = "\033[34m"; CYAN = "\033[36m"; WHITE = "\033[37m"; MAGENTA = "\033[35m"
BG_GREEN = "\033[42m"; BG_RED = "\033[41m"; BG_BLUE = "\033[44m"
CHECK = "✔"; CROSS = "✘"; DOT = "•"; ARROW = "→"
LINE = "─" * 54


def clear():
    os.system("cls" if os.name == "nt" else "clear")


def banner():
    clear()
    print(f"""{CYAN}{BOLD}
  ┌──────────────────────────────────────────────────┐
  │                                                  │
  │   {WHITE}ComfyUI NodeStudio{CYAN}                            │
  │   {DIM}一键安装向导 v1.0{CYAN}                              │
  │                                                  │
  │   {DIM}自动检测 GPU · 适配 PyTorch · 验证环境{CYAN}           │
  └──────────────────────────────────────────────────┘{RESET}
""")


def section(title: str):
    print(f"\n{CYAN}{BOLD}{LINE}{RESET}")
    print(f"{BOLD}  {title}{RESET}")
    print(f"{CYAN}{BOLD}{LINE}{RESET}\n")


def ok(msg: str):
    print(f"  {GREEN}{CHECK}{RESET}  {msg}")


def fail(msg: str):
    print(f"  {RED}{CROSS}{RESET}  {msg}")


def info(msg: str):
    print(f"  {BLUE}{DOT}{RESET}  {msg}")


def warn(msg: str):
    print(f"  {YELLOW}!{RESET}  {YELLOW}{msg}{RESET}")


def cmd(title: str):
    print(f"  {DIM}> {title}{RESET}")


def run(cmd_list: list[str], desc: str = "", check: bool = True, silent: bool = False) -> tuple[int, str]:
    """运行命令并捕获输出。返回 (returncode, output)"""
    try:
        if not silent:
            print(f"  {DIM}$ {' '.join(cmd_list[:4])}{' ...' if len(cmd_list) > 4 else ''}{RESET}")
        result = subprocess.run(cmd_list, capture_output=True, text=True, timeout=600)
        if result.returncode != 0 and check:
            print(f"  {RED}{CROSS} {desc}失败 (退出码 {result.returncode}){RESET}")
            if result.stderr:
                # 只显示最后几行错误
                lines = result.stderr.strip().split("\n")
                for line in lines[-5:]:
                    print(f"    {RED}{line}{RESET}")
        return result.returncode, result.stdout + result.stderr
    except subprocess.TimeoutExpired:
        print(f"  {RED}{CROSS} {desc}超时{RESET}")
        return -1, ""
    except FileNotFoundError:
        print(f"  {RED}{CROSS} 命令未找到: {cmd_list[0]}{RESET}")
        return -1, ""


# ── GPU 检测 ───────────────────────────────────────────────────

def detect_gpu() -> dict:
    """检测 GPU 信息，返回 {vendor, name, compute_capability, vram_mb, arch}"""
    system = platform.system()

    # ── NVIDIA (Windows & Linux) ──
    nvidia_smi = shutil.which("nvidia-smi")
    if not nvidia_smi and system == "Windows":
        # 尝试常见路径
        for p in [r"C:\Windows\System32\nvidia-smi.exe",
                   r"C:\Program Files\NVIDIA Corporation\NVSMI\nvidia-smi.exe"]:
            if os.path.exists(p):
                nvidia_smi = p
                break

    if nvidia_smi:
        try:
            result = subprocess.run(
                [nvidia_smi, "--query-gpu=name,memory.total,compute_cap",
                 "--format=csv,noheader,nounits"],
                capture_output=True, text=True, timeout=15
            )
            if result.returncode == 0 and result.stdout.strip():
                # 解析第一行
                parts = [p.strip() for p in result.stdout.strip().split(",")]
                if len(parts) >= 2:
                    name = parts[0]
                    vram = int(parts[1]) if parts[1].isdigit() else 0
                    cc = parts[2] if len(parts) > 2 else ""
                    arch = _nvidia_arch(name, cc)
                    return {
                        "vendor": "nvidia",
                        "name": name,
                        "compute_capability": cc,
                        "vram_mb": vram,
                        "arch": arch,
                    }
        except Exception:
            pass

    # ── Apple Silicon ──
    if system == "Darwin":
        try:
            result = subprocess.run(["sysctl", "-n", "machdep.cpu.brand_string"],
                                    capture_output=True, text=True, timeout=5)
            cpu = result.stdout.strip()
            if "Apple" in cpu:
                return {"vendor": "apple", "name": cpu, "arch": "mps", "vram_mb": 0, "compute_capability": ""}
        except Exception:
            pass
        # 回退：检查架构
        if platform.machine() == "arm64":
            return {"vendor": "apple", "name": "Apple Silicon", "arch": "mps", "vram_mb": 0, "compute_capability": ""}
        # Intel Mac
        return {"vendor": "intel", "name": "Intel Mac (无 GPU 加速)", "arch": "cpu", "vram_mb": 0, "compute_capability": ""}

    # ── AMD (Linux) ──
    if system == "Linux":
        try:
            result = subprocess.run(["lspci"], capture_output=True, text=True, timeout=10)
            for line in result.stdout.split("\n"):
                if "AMD" in line and ("VGA" in line or "Display" in line or "3D" in line):
                    return {"vendor": "amd", "name": line.strip(), "arch": "rocm", "vram_mb": 0, "compute_capability": ""}
        except Exception:
            pass

    # ── 无 GPU ──
    return {"vendor": "none", "name": "未检测到 GPU", "arch": "cpu", "vram_mb": 0, "compute_capability": ""}


def _nvidia_arch(name: str, cc: str) -> str:
    """根据 GPU 名称和计算能力判断架构代际"""
    name_upper = name.upper()

    # Blackwell (50 系) — 需要 PyTorch preview/nightly
    if any(x in name_upper for x in ["RTX 50", "RTX 5090", "RTX 5080", "RTX 5070", "RTX 5060", "B100", "B200", "BLACKWELL"]):
        return "blackwell"

    # Ada Lovelace (40 系)
    if any(x in name_upper for x in ["RTX 40", "RTX 4090", "RTX 4080", "RTX 4070", "RTX 4060", "RTX 4050", "L40", "ADA"]):
        return "ada"

    # Hopper (H100, H800)
    if any(x in name_upper for x in ["H100", "H800", "HOPPER"]):
        return "hopper"

    # Ampere (30 系)
    if any(x in name_upper for x in ["RTX 30", "RTX 3090", "RTX 3080", "RTX 3070", "RTX 3060", "RTX 3050", "A100", "A6000", "A5000", "A4000", "AMPERE"]):
        return "ampere"

    # Turing (20 系 / GTX 16xx)
    if any(x in name_upper for x in ["RTX 20", "RTX 2080", "RTX 2070", "RTX 2060", "GTX 16", "TURING", "T4"]):
        return "turing"

    # Volta
    if any(x in name_upper for x in ["V100", "VOLTA", "TITAN V"]):
        return "volta"

    # Pascal (GTX 10xx)
    if any(x in name_upper for x in ["GTX 10", "GTX 1080", "GTX 1070", "GTX 1060", "PASCAL", "P100", "P40"]):
        return "pascal"

    # 根据 compute capability 判断
    if cc:
        try:
            major = float(cc)
            if major >= 12.0: return "blackwell"
            if major >= 8.9:  return "ada"
            if major >= 8.0:  return "ampere"
            if major >= 7.5:  return "turing"
            if major >= 7.0:  return "volta"
            if major >= 6.0:  return "pascal"
        except ValueError:
            pass

    return "unknown"


# ── PyTorch 版本选择 ────────────────────────────────────────────

def get_pytorch_cmd(gpu: dict) -> tuple[str, str]:
    """
    根据 GPU 信息返回 (描述, pip install 命令)。
    """
    arch = gpu["arch"]
    vendor = gpu["vendor"]
    name = gpu["name"]
    system = platform.system()

    if vendor == "nvidia":
        if arch == "blackwell":
            return (
                f"RTX 50 系 (Blackwell) — 需要 PyTorch Nightly + CUDA 12.8",
                ["pip", "install", "--pre", "torch", "torchvision", "torchaudio",
                 "--index-url", "https://download.pytorch.org/whl/nightly/cu128"]
            )
        elif arch in ("ada", "hopper"):
            return (
                f"{name} — PyTorch 2.x + CUDA 12.4",
                ["pip", "install", "torch", "torchvision", "torchaudio",
                 "--index-url", "https://download.pytorch.org/whl/cu124"]
            )
        elif arch == "ampere":
            return (
                f"{name} — PyTorch 2.x + CUDA 12.1",
                ["pip", "install", "torch", "torchvision", "torchaudio",
                 "--index-url", "https://download.pytorch.org/whl/cu121"]
            )
        elif arch in ("turing", "volta", "pascal"):
            return (
                f"{name} — PyTorch 2.x + CUDA 12.1",
                ["pip", "install", "torch", "torchvision", "torchaudio",
                 "--index-url", "https://download.pytorch.org/whl/cu121"]
            )
        else:
            # 未识别的 NVIDIA GPU — 尝试 CUDA 12.4
            warn(f"未识别的 NVIDIA GPU 代际 ({arch})，使用 CUDA 12.4 版本")
            return (
                f"{name} — 通用 CUDA 12.4",
                ["pip", "install", "torch", "torchvision", "torchaudio",
                 "--index-url", "https://download.pytorch.org/whl/cu124"]
            )

    elif vendor == "apple":
        return (
            "Apple Silicon — Metal Performance Shaders (MPS)",
            ["pip", "install", "torch", "torchvision", "torchaudio"]
        )

    elif vendor == "amd":
        return (
            "AMD GPU — ROCm 6.0",
            ["pip", "install", "torch", "torchvision", "torchaudio",
             "--index-url", "https://download.pytorch.org/whl/rocm6.0"]
        )

    else:
        # CPU 模式
        return (
            "未检测到 GPU — CPU 模式",
            ["pip", "install", "torch", "torchvision", "torchaudio",
             "--index-url", "https://download.pytorch.org/whl/cpu"]
        )


# ── 安装流程 ────────────────────────────────────────────────────

def install_base_deps(venv_python: str, root_dir: str):
    """安装 requirements.txt 中的基础依赖"""
    req_path = os.path.join(root_dir, "requirements.txt")
    if not os.path.exists(req_path):
        fail(f"找不到 requirements.txt: {req_path}")
        return False

    info("正在安装 ComfyUI 基础依赖...")
    ret, out = run(
        [venv_python, "-m", "pip", "install", "-r", req_path,
         "--index-url", "https://pypi.org/simple/"],
        desc="基础依赖安装"
    )
    if ret != 0:
        fail("基础依赖安装失败")
        _pip_fail_help(out)
        return False
    ok("基础依赖安装完成")
    return True


def install_pytorch(venv_python: str, gpu: dict) -> bool:
    """安装适配 GPU 的 PyTorch 版本"""
    desc, cmd_list = get_pytorch_cmd(gpu)
    info(f"PyTorch 安装方案: {desc}")

    # 确保 pip 最新
    run([venv_python, "-m", "pip", "install", "--upgrade", "pip"],
        desc="升级 pip", check=False, silent=True)

    ret, out = run([venv_python] + cmd_list[1:], desc="PyTorch 安装")
    if ret != 0:
        fail("PyTorch 安装失败")
        _pytorch_fail_help(gpu, out)
        return False
    ok("PyTorch 安装完成")
    return True


def install_webui_deps(venv_python: str, root_dir: str) -> bool:
    """安装前端项目依赖（如果有 package.json 且用户要构建前端）"""
    webui_dir = os.path.join(root_dir, "..", "comfyui-nodestudio")
    if not os.path.isdir(webui_dir):
        return True  # 不是必需的

    # 检查 node_modules 是否已存在
    node_modules = os.path.join(webui_dir, "node_modules")
    if os.path.isdir(node_modules):
        info("前端依赖已存在，跳过 npm install")
        return True

    npm = shutil.which("npm") or shutil.which("pnpm") or shutil.which("yarn")
    if not npm:
        warn("未找到 Node.js，跳过前端依赖安装（不影响使用已构建的前端）")
        return True

    info("正在安装前端依赖 (npm install)...")
    ret, out = run([npm, "install"], desc="npm install", check=False)
    if ret != 0:
        warn("前端依赖安装失败（不影响后端运行，但开发模式需要）")
        return True
    ok("前端依赖安装完成")
    return True


def validate_torch(venv_python: str, gpu: dict) -> bool:
    """验证 PyTorch 是否能正常使用 GPU"""
    code = """
import torch
print(f"PyTorch {torch.__version__}")
print(f"CUDA available: {torch.cuda.is_available()}")
if torch.cuda.is_available():
    print(f"CUDA version: {torch.version.cuda}")
    print(f"GPU: {torch.cuda.get_device_name(0)}")
    print(f"VRAM: {torch.cuda.get_device_properties(0).total_mem // 1024**2} MB")
    print("OK_CUDA")
elif hasattr(torch.backends, 'mps') and torch.backends.mps.is_available():
    print("MPS available: True")
    print("OK_MPS")
else:
    print("OK_CPU")
"""
    ret, out = run([venv_python, "-c", code], desc="PyTorch 验证", check=False)
    if "OK_CUDA" in out:
        ok("PyTorch CUDA 加速已就绪")
        return True
    elif "OK_MPS" in out:
        ok("PyTorch Metal (MPS) 加速已就绪")
        return True
    elif "OK_CPU" in out:
        if gpu["vendor"] == "nvidia":
            warn("检测到 NVIDIA GPU 但 PyTorch 无法使用 CUDA！")
            _cuda_troubleshoot(gpu)
            return True  # 不算致命错误
        else:
            info("PyTorch CPU 模式已就绪")
            return True
    else:
        warn("PyTorch 验证返回异常，但可能仍可运行")
        print(f"  {DIM}{out.strip()[-300:]}{RESET}")
        return True


# ── 错误排障指南 ────────────────────────────────────────────────

def _pip_fail_help(output: str):
    print(f"""
  {YELLOW}{BOLD}排障建议：{RESET}
  1. 检查网络连接，国内用户可尝试:
     pip install -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple/
  2. 确保系统时间正确（SSL 证书验证需要）
  3. 如果提示权限不足，不要用 sudo，使用虚拟环境即可
""")


def _pytorch_fail_help(gpu: dict, output: str):
    arch = gpu["arch"]
    print(f"""
  {YELLOW}{BOLD}排障建议：{RESET}""")
    if arch == "blackwell":
        print(f"""  50 系显卡 (Blackwell) 必须使用 Nightly 版本。
  如果 nightly 安装失败，请检查:
  1. 网络连接是否正常（需要从 download.pytorch.org 下载）
  2. 可以手动安装: pip install --pre torch torchvision torchaudio --index-url https://download.pytorch.org/whl/nightly/cu128
""")
    elif gpu["vendor"] == "nvidia":
        print(f"""  NVIDIA GPU 检测到，但 PyTorch CUDA 版本安装失败。
  可能原因:
  1. CUDA 驱动版本太旧 — 运行 nvidia-smi 查看驱动版本
  2. 网络问题 — 手动安装: pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu124
  3. 如果仍然失败，可以降级为 CPU 版本: pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cpu
""")
    else:
        print(f"""  PyTorch 安装失败。
  1. 检查网络连接
  2. 手动安装 CPU 版本: pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cpu
""")


def _cuda_troubleshoot(gpu: dict):
    print(f"""
  {YELLOW}{BOLD}CUDA 排障指南：{RESET}
  1. 运行 {CYAN}nvidia-smi{RESET} 查看驱动是否正常
  2. 如果 nvidia-smi 报错，说明驱动未安装或版本不兼容
     - 下载最新驱动: {CYAN}https://www.nvidia.com/download/{RESET}
  3. 如果 nvidia-smi 正常但 PyTorch 看不到 GPU：
     - 重新安装 PyTorch CUDA 版本:
       {CYAN}pip uninstall torch torchvision torchaudio -y{RESET}
       然后重新运行本安装向导
  4. 50 系显卡 (RTX 5090/5080/5070) 目前需要:
     - NVIDIA 驱动 >= 570
     - PyTorch Nightly 版本
""")


# ── 主流程 ──────────────────────────────────────────────────────

def main():
    banner()

    root_dir = os.path.dirname(os.path.abspath(__file__))
    venv_dir = os.path.join(root_dir, ".venv")
    venv_python = os.path.join(venv_dir, "Scripts" if os.name == "nt" else "bin", "python.exe" if os.name == "nt" else "python")

    if not os.path.exists(venv_python):
        fail("未找到虚拟环境！")
        print(f"  请先运行启动脚本（.bat / .command / .sh）来创建虚拟环境。")
        sys.exit(1)

    total_steps = 5
    step_num = 0

    # ── 步骤 1: 检测系统与 GPU ──
    step_num += 1
    section(f"步骤 {step_num}/{total_steps}  检测系统与 GPU")
    info(f"操作系统: {platform.system()} {platform.release()} ({platform.machine()})")
    info(f"Python: {sys.version.split()[0]}")

    gpu = detect_gpu()
    if gpu["vendor"] == "nvidia":
        vram_str = f", {gpu['vram_mb']} MB 显存" if gpu["vram_mb"] else ""
        info(f"GPU: {gpu['name']} ({gpu['arch']}{vram_str})")
        if gpu["arch"] == "blackwell":
            warn("检测到 RTX 50 系显卡！需要 PyTorch Nightly 版本。")
            info("确保已安装 NVIDIA 驱动 >= 570")
    elif gpu["vendor"] == "apple":
        ok(f"{gpu['name']} — 将使用 Metal (MPS) 加速")
    elif gpu["vendor"] == "amd":
        info(f"AMD GPU: {gpu['name']} — 将使用 ROCm")
    else:
        warn("未检测到 GPU，将安装 CPU 版 PyTorch（生成图片会很慢）")

    # ── 步骤 2: 升级 pip ──
    step_num += 1
    section(f"步骤 {step_num}/{total_steps}  准备 pip")
    run([venv_python, "-m", "pip", "install", "--upgrade", "pip", "setuptools", "wheel"],
        desc="升级 pip", check=False)
    ok("pip 已就绪")

    # ── 步骤 3: 安装基础依赖 ──
    step_num += 1
    section(f"步骤 {step_num}/{total_steps}  安装 ComfyUI 基础依赖")
    if not install_base_deps(venv_python, root_dir):
        print(f"\n  {RED}安装失败，请根据上述提示排查后重新运行。{RESET}")
        sys.exit(1)

    # ── 步骤 4: 安装 PyTorch ──
    step_num += 1
    section(f"步骤 {step_num}/{total_steps}  安装 PyTorch (适配 GPU)")
    if not install_pytorch(venv_python, gpu):
        print(f"\n  {YELLOW}PyTorch 安装失败，但基础环境已就绪。{RESET}")
        print(f"  请手动安装 PyTorch 后重新运行验证。")
        sys.exit(1)

    # ── 步骤 5: 验证环境 ──
    step_num += 1
    section(f"步骤 {step_num}/{total_steps}  验证环境")
    if not validate_torch(venv_python, gpu):
        warn("环境验证有警告，但可能仍可运行")

    # ── 可选：前端依赖 ──
    install_webui_deps(venv_python, root_dir)

    # ── 完成 ──
    print(f"""
  {BG_GREEN}{WHITE}{BOLD}  安装完成！{RESET}

  {BOLD}启动方式：{RESET}
    {CYAN}Windows{RESET}: 双击 {BOLD}start_comfyui_and_webui.bat{RESET}
    {CYAN}Mac{RESET}:     双击 {BOLD}start_comfyui_and_webui.command{RESET}
    {CYAN}Linux{RESET}:   {BOLD}./start_comfyui_and_webui.sh{RESET}

  {BOLD}启动后访问：{RESET}{CYAN}http://127.0.0.1:8288{RESET}
""")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print(f"\n\n  {YELLOW}安装已取消。{RESET}")
        sys.exit(0)
    except Exception as e:
        print(f"\n  {RED}意外错误: {e}{RESET}")
        sys.exit(1)
