"""启动环境诊断 —— 检测 PyTorch 后端、模型加载状态、Apple Silicon 兼容性"""

from __future__ import annotations

import logging
import os
import platform
import sys
from pathlib import Path

logger = logging.getLogger(__name__)


def _human_size(size_bytes: float) -> str:
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if abs(size_bytes) < 1024:
            return f"{size_bytes:.1f} {unit}"
        size_bytes /= 1024
    return f"{size_bytes:.1f} PB"


def run_startup_diagnostics() -> None:
    lines: list[str] = []
    lines.append("=" * 64)
    lines.append("  启动环境诊断")
    lines.append("=" * 64)

    # ---- 系统信息 ----
    lines.append(f"[系统] {platform.platform()}")
    lines.append(f"[Python] {sys.version.split()[0]} ({sys.executable})")
    arch = platform.machine()
    is_mac = sys.platform == "darwin"
    is_apple_silicon = is_mac and arch == "arm64"
    lines.append(f"[架构] {arch} | Apple Silicon: {'是' if is_apple_silicon else '否'}")

    # ---- PyTorch ----
    try:
        import torch
        lines.append(f"[PyTorch] {torch.__version__}")

        cuda_available = torch.cuda.is_available()
        mps_available = torch.backends.mps.is_available() if hasattr(torch.backends, "mps") else False
        mps_built = torch.backends.mps.is_built() if hasattr(torch.backends, "mps") else False

        if cuda_available:
            device_count = torch.cuda.device_count()
            lines.append(f"[后端] CUDA ({device_count} GPU)")
            for i in range(device_count):
                props = torch.cuda.get_device_properties(i)
                vram_gb = props.total_memory / (1024 ** 3)
                lines.append(f"  GPU {i}: {props.name} | VRAM {vram_gb:.1f} GB | CC {props.major}.{props.minor}")
        elif mps_available:
            lines.append("[后端] MPS (Metal Performance Shaders)")
            lines.append(f"  MPS built: {mps_built}")
            # 检查 MPS 内存水位线
            hw_ratio = os.environ.get("PYTORCH_MPS_HIGH_WATERMARK_RATIO", "未设置(默认0.5)")
            lines.append(f"  PYTORCH_MPS_HIGH_WATERMARK_RATIO = {hw_ratio}")
            if hw_ratio == "未设置(默认0.5)":
                lines.append("  [!] 建议: export PYTORCH_MPS_HIGH_WATERMARK_RATIO=0.0 解除MPS内存限制")
            # MPS 说明
            lines.append("  [i] Apple Silicon 上 MPS GPU 运算的部分开销（Metal shader 编译、数据调度）会体现在 CPU 占用中")
            lines.append("  [i] 活动监视器中 50-70% CPU 属于正常范围，不代表 MPS 回退到 CPU")
        else:
            lines.append("[后端] CPU 模式 (无加速)")
            lines.append("  [!] 生成将非常缓慢, 建议安装支持MPS/CUDA的PyTorch版本")

        # 注意力实现
        try:
            has_sdpa = hasattr(torch.nn.functional, "scaled_dot_product_attention")
            lines.append(f"[注意力] scaled_dot_product_attention: {'可用' if has_sdpa else '不可用'}")

            if hasattr(torch.backends.cuda, "enable_flash_sdp"):
                flash_enabled = torch.backends.cuda.enable_flash_sdp
                lines.append(f"  Flash SDP: {'已启用' if flash_enabled else '未启用'}")
            if hasattr(torch.backends.cuda, "enable_mem_efficient_sdp"):
                mem_eff = torch.backends.cuda.enable_mem_efficient_sdp
                lines.append(f"  Memory-efficient SDP: {'已启用' if mem_eff else '未启用'}")
        except Exception:
            pass

        # Apple Silicon 专属建议
        if is_apple_silicon and mps_available:
            lines.append("[Apple Silicon 说明]")
            lines.append("  1. 活动监视器 CPU 50-70% 是 MPS 正常开销（Metal shader 编译+数据调度），非 CPU 回退")
            lines.append("  2. 真正 CPU 回退的特征是生成极慢 + CPU 持续 90%+")
            lines.append("  3. 可通过 ComfyUI 日志中 'MPS' 关键字确认实际使用的后端")
            lines.append("  4. M5 Pro 64GB 内存充足, 可同时加载多个模型避免重复加载")

    except ImportError:
        lines.append("[PyTorch] [ERROR] 未安装")

    # ---- 模型目录 ----
    models_base: Path | None = None
    try:
        models_base = Path(__file__).resolve().parents[2] / "models"
        if not models_base.exists():
            models_base = Path(os.getcwd()) / "ComfyUI" / "models"

        if models_base.exists():
            total_size = 0
            model_dirs: list[tuple[str, float, int]] = []
            for child in sorted(models_base.iterdir()):
                if child.is_dir():
                    try:
                        dir_size = sum(
                            f.stat().st_size for f in child.rglob("*") if f.is_file()
                        )
                    except Exception:
                        dir_size = 0
                    total_size += dir_size
                    file_count = sum(1 for f in child.rglob("*") if f.is_file())
                    if dir_size > 1024:  # 只报告非空目录
                        model_dirs.append((child.name, dir_size, file_count))

            lines.append(f"[模型目录] {models_base}")
            lines.append(f"  总计: {_human_size(total_size)} ({len(model_dirs)} 个子目录)")
            for name, size, count in model_dirs:
                lines.append(f"  {name}: {_human_size(size)} ({count} 文件)")
        else:
            lines.append(f"[模型目录] 未找到: {models_base}")
    except Exception as e:
        lines.append(f"[模型目录] 检测失败: {e}")

    # ---- 关键模型文件 ----
    lines.append("[关键模型检测]")
    _check_key_models(models_base, lines)

    # ---- 环境变量 ----
    lines.append("[环境变量]")
    for var in ("COMFY_BASE_URL", "WEBUI_HOST", "WEBUI_PORT", "WEBUI_REQUEST_TIMEOUT",
                "PYTORCH_MPS_HIGH_WATERMARK_RATIO", "PYTORCH_ENABLE_MPS_FALLBACK",
                "OMP_NUM_THREADS", "MKL_NUM_THREADS"):
        val = os.environ.get(var, "")
        if val:
            lines.append(f"  {var} = {val}")
        else:
            lines.append(f"  {var} = (未设置)")

    lines.append("=" * 64)

    # 输出到日志
    for line in lines:
        logger.info(line)


def _check_key_models(models_base: Path | None, lines: list[str]) -> None:
    """检查 jieyatu / xinliututu 等用到的大模型是否存在"""
    if models_base is None:
        lines.append("  (模型目录未找到, 跳过)")
        return

    # 这些是 jieyatu / xinliututu 工作流引用的模型
    key_models = [
        ("CLIP", "clip/qwen_2.5_vl_7b_fp8_scaled.safetensors"),
        ("UNET", "unet/qwen_image_edit_2509_fp8_e4m3fn.safetensors"),
        ("VAE", "vae/qwen_image_vae.safetensors"),
        ("LoRA", "loras/Qwen-Image-Edit-2509-Lightning-4steps-V1.0-bf16.safetensors"),
    ]

    for label, rel_path in key_models:
        path = models_base / rel_path
        if path.exists():
            size = _human_size(path.stat().st_size)
            lines.append(f"  [OK] {label}: {rel_path} ({size})")
        else:
            # 尝试模糊搜索
            parent = models_base / rel_path.split("/")[0]
            fname = rel_path.split("/")[-1]
            if parent.exists():
                found = list(parent.glob(f"*{fname[:20]}*"))
                if found:
                    lines.append(f"  [?] {label}: 近似匹配 {found[0].name}")
                else:
                    lines.append(f"  [MISS] {label}: {rel_path} (文件不存在)")
            else:
                lines.append(f"  [MISS] {label}: {rel_path} (目录不存在)")
