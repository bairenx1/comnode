import sys
import platform

try:
    import torch

    # NVIDIA CUDA
    if torch.cuda.is_available():
        print(f"[CUDA OK] GPU: {torch.cuda.get_device_name(0)}")
        sys.exit(0)

    # Apple MPS (Metal Performance Shaders)
    if platform.system() == "Darwin" and torch.backends.mps.is_available():
        if torch.backends.mps.is_built():
            print("[MPS OK] Apple Metal 加速可用 (Apple Silicon)")
            sys.exit(0)
        else:
            print("[MPS] PyTorch 未以 MPS 支持编译，使用 CPU 模式")
            sys.exit(1)

    print("[加速] 无可用的 GPU/MPS 加速，使用 CPU 模式")
    sys.exit(1)
except ImportError:
    print("[加速] PyTorch 未安装，使用 CPU 模式")
    sys.exit(1)
except Exception as e:
    print(f"[加速] 检测错误: {e}，使用 CPU 模式")
    sys.exit(1)
