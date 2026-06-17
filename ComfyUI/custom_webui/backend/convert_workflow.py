import copy
import sys, json, re
from pathlib import Path
from typing import Any

WORKFLOWS_DIR = Path(__file__).resolve().parent.parent / "workflows"
# ComfyUI 标准保存路径
_USER_DEFAULT_DIR = Path(__file__).resolve().parent.parent.parent / "user" / "default"
USER_WORKFLOW_DIRS = [
    _USER_DEFAULT_DIR / "workflows",  # 复数：ComfyUI 标准路径
    _USER_DEFAULT_DIR / "workflow",   # 单数：兼容旧路径
]

SKIP_TYPES = {'MarkdownNote', 'Note', 'PrimitiveNode', 'Reroute', 'SetNode'}

# 持有可编辑文本值的 Primitive 节点类型（其值通过 UUID Group Node 的 link 暴露）
PRIMITIVE_VALUE_TYPES = {'PrimitiveStringMultiline'}

# 不暴露 UI 参数的节点类型（模型加载器等，用户不需要在工作流中切换）
HIDDEN_UI_TYPES = {
    'CheckpointLoaderSimple', 'CheckpointLoader',
    'VAELoader',
    'CLIPLoader', 'DualCLIPLoader',
    'LoraLoader', 'LoraLoaderModelOnly',
    'ControlNetLoader',
    'unCLIPCheckpointLoader', 'ImageOnlyCheckpointLoader',
}

# 不暴露 UI 的字段名（模型/VAE/CLIP/unet 选择器，可能出现在任意节点类型中）
HIDDEN_FIELD_NAMES = {
    'ckpt_name', 'checkpoint_name',
    'vae_name',
    'clip_name', 'clip_name1', 'clip_name2',
    'unet_name', 'model_name',
    'lora_name', 'lora_name_1', 'lora_name_2', 'lora_name_3',
    'control_net_name',
    # LoadImage/LoadVideo 内部模式切换参数
    'upload',
    # 各种节点的内部/通用参数
    'text_encoder',
    'device', 'weight_dtype',  # 加载器内部硬件参数
    'type',  # DualCLIPLoaderGGUF 等节点的内部 type 参数
    'upscale_method', 'scale_by',  # ImageScaleBy 内部参数
    'value', 'value_1', 'value_2', 'value_3', 'value_4', 'value_5',
    'value_6', 'value_7', 'value_8', 'value_9', 'value_10',
}

def _is_hidden_field_name(name: str) -> bool:
    """检查字段名是否应隐藏（包括通用 value/value_N 模式）"""
    if name in HIDDEN_FIELD_NAMES:
        return True
    # 匹配 value_数字 模式（如 value_1, value_99 等）
    if re.match(r'^value_\d+$', name):
        return True
    return False


def _title_to_field_name(title: str) -> str | None:
    """将用户设置的标题转换为安全的字段名，如 "FPS" → "fps", "Duration (seconds)" → "duration_seconds"

    返回 None 表示标题不可用（空或太短）。
    """
    if not title or not isinstance(title, str):
        return None
    # 移除括号及其内容，保留主体部分
    clean = re.sub(r'\([^)]*\)', '', title)
    # 替换非字母数字为下划线，转小写
    safe = re.sub(r'[^a-zA-Z0-9一-鿿]+', '_', clean).strip('_').lower()
    if not safe or len(safe) < 2:
        return None
    # 限制长度避免字段名过长
    return safe[:40]


# UUID 格式的 class_type 表示 ComfyUI Group Node（包装器节点），其内部子节点已在图中独立存在
UUID_TYPE_RE = re.compile(
    r'^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$',
    re.IGNORECASE,
)

# 纯连接器节点：不需要暴露用户参数，但需要保留在图里
CONNECTOR_TYPES = {
    'VAEEncode', 'VAEDecode', 'SaveImage', 'PreviewImage', 'SaveImageWebsocket',
    'EmptyLatentImage', 'UpscaleModelLoader', 'ImageScale', 'ImageScaleBy',
    'ImageUpscaleWithModel', 'SetLatentNoiseMask', 'LatentUpscale', 'LatentUpscaleBy',
    'ImageBatch', 'LatentBatch', 'LatentComposite', 'LatentCompositeMasked',
    'CropLatent', 'RepeatLatentBatch', 'ImpactLatentBatchBlend',
    # 视频专用连接器节点
    'TrimVideoLatent', 'VHS_VideoCombine', 'VHS_LoadVideo', 'VHS_LoadVideoPath',
    'SaveAnimatedWEBP', 'SaveAnimatedPNG', 'VideoCombine',
    'EmptyHunyuanLatentVideo', 'EmptySD3LatentVideo',
}

# 字段名别名映射 — 统一不同节点类型的同义参数
FIELD_ALIASES = {
    'video_frames': 'frame_count',
    'num_frames': 'frame_count',
    'length': 'frame_count',
    'frame_length': 'frame_count',
    'total_frames': 'frame_count',
    'motion_bucket_id': 'motion_bucket_id',
    'fps': 'fps',
    'frame_rate': 'fps',
    'augmentation_level': 'augmentation_level',
    'image_width': 'width',
    'image_height': 'height',
}

KSAMPLER_WIDGET_MAP = {
    0: ('seed', lambda v: int(v) if v is not None else 1, {'type': 'number', 'default': 1, 'min': 0, 'max': 0xffffffffffffffff}),
    2: ('steps', int, {'type': 'number', 'default': 20, 'min': 1, 'max': 10000}),
    3: ('cfg', float, {'type': 'number', 'default': 7.5, 'min': 1, 'max': 30, 'step': 0.5}),
    4: ('sampler_name', str, {'type': 'combo', 'default': 'euler'}),
    5: ('scheduler', str, {'type': 'combo', 'default': 'normal'}),
    6: ('denoise', float, {'type': 'number', 'default': 1.0, 'min': 0, 'max': 1, 'step': 0.05}),
}

SAMPLER_NAMES = ['euler', 'euler_ancestral', 'heun', 'heunpp2', 'dpm_2', 'dpm_2_ancestral',
    'lms', 'dpm_fast', 'dpm_adaptive', 'dpmpp_2s_ancestral', 'dpmpp_sde', 'dpmpp_sde_gpu',
    'dpmpp_2m', 'dpmpp_2m_sde', 'dpmpp_2m_sde_gpu', 'dpmpp_3m_sde', 'dpmpp_3m_sde_gpu',
    'ddim', 'uni_pc', 'uni_pc_bh2', 'lcm', 'ipndm', 'ipndm_v', 'res_multistep',
    'res_multistep_cfg', 'res_multistep_ancestral', 'res_multistep_ancestral_cfg',
    'gradient_estimation', 'restart']

SCHEDULERS = ['normal', 'karras', 'exponential', 'sgm_uniform', 'simple', 'ddim_uniform',
    'beta', 'linear_quadratic', 'kl_optimal', 'align_your_steps', 'ays']

# 需要暴露用户参数的节点类型配置
SPECIAL_NODE_CONFIGS = {
    'CheckpointLoaderSimple': {
        'ckpt_name': {'type': 'combo', 'label': '底模', 'field': 'ckpt_name'},
    },
    'CheckpointLoader': {
        'ckpt_name': {'type': 'combo', 'label': '底模', 'field': 'ckpt_name'},
    },
    'VAELoader': {
        'vae_name': {'type': 'combo', 'label': 'VAE', 'field': 'vae_name'},
    },
    'CLIPLoader': {
        'clip_name': {'type': 'combo', 'label': 'CLIP 模型', 'field': 'clip_name'},
    },
    'DualCLIPLoader': {
        'clip_name1': {'type': 'combo', 'label': 'CLIP 模型', 'field': 'clip_name'},
    },
    'unCLIPCheckpointLoader': {
        'ckpt_name': {'type': 'combo', 'label': '底模', 'field': 'ckpt_name'},
    },
    'LoraLoader': {
        'lora_name': {'type': 'combo', 'label': 'LoRA 模型', 'field': 'lora_name'},
        'strength_model': {'type': 'number', 'label': '模型强度', 'field': 'strength_model', 'default': 1.0, 'min': -10, 'max': 10, 'step': 0.05},
        'strength_clip': {'type': 'number', 'label': 'CLIP 强度', 'field': 'strength_clip', 'default': 1.0, 'min': -10, 'max': 10, 'step': 0.05},
    },
    'LoraLoaderModelOnly': {
        'lora_name': {'type': 'combo', 'label': 'LoRA 模型', 'field': 'lora_name'},
        'strength_model': {'type': 'number', 'label': '模型强度', 'field': 'strength_model', 'default': 1.0, 'min': -10, 'max': 10, 'step': 0.05},
    },
    'ControlNetLoader': {
        'control_net_name': {'type': 'combo', 'label': 'ControlNet', 'field': 'control_net_name'},
    },
    'ControlNetApply': {
        'strength': {'type': 'number', 'label': '控制强度', 'field': 'cn_strength', 'default': 1.0, 'min': 0, 'max': 10, 'step': 0.05},
    },
    'ControlNetApplyAdvanced': {
        'strength': {'type': 'number', 'label': '控制强度', 'field': 'cn_strength', 'default': 1.0, 'min': 0, 'max': 10, 'step': 0.05},
        'start_percent': {'type': 'number', 'label': '起始百分比', 'field': 'start_percent', 'default': 0.0, 'min': 0, 'max': 1, 'step': 0.05},
        'end_percent': {'type': 'number', 'label': '结束百分比', 'field': 'end_percent', 'default': 1.0, 'min': 0, 'max': 1, 'step': 0.05},
    },
    'LoadImage': {
        'image': {'type': 'string', 'label': '输入图片', 'field': 'image_asset_hash'},
    },
    'LoadVideo': {
        'video': {'type': 'string', 'label': '输入视频', 'field': 'video_asset_hash'},
    },
    'ImageOnlyCheckpointLoader': {
        'ckpt_name': {'type': 'combo', 'label': '底模', 'field': 'ckpt_name'},
    },
    'FreeU': {
        'b1': {'type': 'number', 'label': 'FreeU B1', 'field': 'freeu_b1', 'default': 1.1, 'min': 0, 'max': 10, 'step': 0.1},
        'b2': {'type': 'number', 'label': 'FreeU B2', 'field': 'freeu_b2', 'default': 1.2, 'min': 0, 'max': 10, 'step': 0.1},
        's1': {'type': 'number', 'label': 'FreeU S1', 'field': 'freeu_s1', 'default': 0.9, 'min': 0, 'max': 10, 'step': 0.1},
        's2': {'type': 'number', 'label': 'FreeU S2', 'field': 'freeu_s2', 'default': 0.2, 'min': 0, 'max': 10, 'step': 0.1},
    },
    'FreeU_V2': {
        'b1': {'type': 'number', 'label': 'FreeU V2 B1', 'field': 'freeu_b1', 'default': 1.3, 'min': 0, 'max': 10, 'step': 0.1},
        'b2': {'type': 'number', 'label': 'FreeU V2 B2', 'field': 'freeu_b2', 'default': 1.4, 'min': 0, 'max': 10, 'step': 0.1},
        's1': {'type': 'number', 'label': 'FreeU V2 S1', 'field': 'freeu_s1', 'default': 0.9, 'min': 0, 'max': 10, 'step': 0.1},
        's2': {'type': 'number', 'label': 'FreeU V2 S2', 'field': 'freeu_s2', 'default': 0.2, 'min': 0, 'max': 10, 'step': 0.1},
    },
    'KSamplerAdvanced': {
        0: ('noise_seed', lambda v: int(v) if v is not None else 1, {'type': 'number', 'label': '噪声种子', 'default': 1, 'min': 0, 'max': 0xffffffffffffffff}),
        2: ('steps', int, {'type': 'number', 'default': 20, 'min': 1, 'max': 10000}),
        3: ('cfg', float, {'type': 'number', 'default': 7.5, 'min': 1, 'max': 30, 'step': 0.5}),
        4: ('sampler_name', str, {'type': 'combo', 'default': 'euler'}),
        5: ('scheduler', str, {'type': 'combo', 'default': 'normal'}),
        6: ('start_at_step', int, {'type': 'number', 'default': 0, 'min': 0, 'max': 10000}),
        7: ('end_at_step', int, {'type': 'number', 'default': 10000, 'min': 0, 'max': 10000}),
    },
    # ===================== 视频节点类型 =====================
    'SVD_img2vid_Conditioning': {
        'width': {'type': 'number', 'label': '宽度', 'field': 'width', 'default': 1024, 'min': 16, 'max': 16384, 'step': 8},
        'height': {'type': 'number', 'label': '高度', 'field': 'height', 'default': 576, 'min': 16, 'max': 16384, 'step': 8},
        'video_frames': {'type': 'number', 'label': '视频帧数', 'field': 'frame_count', 'default': 14, 'min': 1, 'max': 4096},
        'motion_bucket_id': {'type': 'number', 'label': '运动幅度', 'field': 'motion_bucket_id', 'default': 127, 'min': 1, 'max': 1023},
        'fps': {'type': 'number', 'label': '帧率', 'field': 'fps', 'default': 6, 'min': 1, 'max': 1024},
        'augmentation_level': {'type': 'number', 'label': '增强级别', 'field': 'augmentation_level', 'default': 0.0, 'min': 0, 'max': 10, 'step': 0.01},
    },
    'VideoLinearCFGGuidance': {
        'min_cfg': {'type': 'number', 'label': '最小CFG', 'field': 'min_cfg', 'default': 1.0, 'min': 0, 'max': 100, 'step': 0.5},
    },
    'VideoTriangleCFGGuidance': {
        'min_cfg': {'type': 'number', 'label': '最小CFG', 'field': 'min_cfg', 'default': 1.0, 'min': 0, 'max': 100, 'step': 0.5},
    },
    # WAN 系列视频节点 — width/height/length/batch_size
    'WanImageToVideo': {
        'width': {'type': 'number', 'label': '宽度', 'field': 'width', 'default': 832, 'min': 16, 'max': 16384, 'step': 16},
        'height': {'type': 'number', 'label': '高度', 'field': 'height', 'default': 480, 'min': 16, 'max': 16384, 'step': 16},
        'length': {'type': 'number', 'label': '视频长度', 'field': 'frame_count', 'default': 81, 'min': 1, 'max': 16384, 'step': 4},
        'batch_size': {'type': 'number', 'label': '批次数量', 'field': 'batch_size', 'default': 1, 'min': 1, 'max': 4096},
    },
    'WanFunControlToVideo': {
        'width': {'type': 'number', 'label': '宽度', 'field': 'width', 'default': 832, 'min': 16, 'max': 16384, 'step': 16},
        'height': {'type': 'number', 'label': '高度', 'field': 'height', 'default': 480, 'min': 16, 'max': 16384, 'step': 16},
        'length': {'type': 'number', 'label': '视频长度', 'field': 'frame_count', 'default': 81, 'min': 1, 'max': 16384, 'step': 4},
        'batch_size': {'type': 'number', 'label': '批次数量', 'field': 'batch_size', 'default': 1, 'min': 1, 'max': 4096},
    },
    'WanFirstLastFrameToVideo': {
        'width': {'type': 'number', 'label': '宽度', 'field': 'width', 'default': 832, 'min': 16, 'max': 16384, 'step': 16},
        'height': {'type': 'number', 'label': '高度', 'field': 'height', 'default': 480, 'min': 16, 'max': 16384, 'step': 16},
        'length': {'type': 'number', 'label': '视频长度', 'field': 'frame_count', 'default': 81, 'min': 1, 'max': 16384, 'step': 4},
        'batch_size': {'type': 'number', 'label': '批次数量', 'field': 'batch_size', 'default': 1, 'min': 1, 'max': 4096},
    },
    'WanVaceToVideo': {
        'width': {'type': 'number', 'label': '宽度', 'field': 'width', 'default': 832, 'min': 16, 'max': 16384, 'step': 16},
        'height': {'type': 'number', 'label': '高度', 'field': 'height', 'default': 480, 'min': 16, 'max': 16384, 'step': 16},
        'length': {'type': 'number', 'label': '视频长度', 'field': 'frame_count', 'default': 81, 'min': 1, 'max': 16384, 'step': 4},
        'batch_size': {'type': 'number', 'label': '批次数量', 'field': 'batch_size', 'default': 1, 'min': 1, 'max': 4096},
        'strength': {'type': 'number', 'label': '控制强度', 'field': 'vace_strength', 'default': 1.0, 'min': 0, 'max': 1000, 'step': 0.01},
    },
    'WanCameraImageToVideo': {
        'width': {'type': 'number', 'label': '宽度', 'field': 'width', 'default': 832, 'min': 16, 'max': 16384, 'step': 16},
        'height': {'type': 'number', 'label': '高度', 'field': 'height', 'default': 480, 'min': 16, 'max': 16384, 'step': 16},
        'length': {'type': 'number', 'label': '视频长度', 'field': 'frame_count', 'default': 81, 'min': 1, 'max': 16384, 'step': 4},
        'batch_size': {'type': 'number', 'label': '批次数量', 'field': 'batch_size', 'default': 1, 'min': 1, 'max': 4096},
    },
    'WanTrackToVideo': {
        'width': {'type': 'number', 'label': '宽度', 'field': 'width', 'default': 832, 'min': 16, 'max': 16384, 'step': 16},
        'height': {'type': 'number', 'label': '高度', 'field': 'height', 'default': 480, 'min': 16, 'max': 16384, 'step': 16},
        'length': {'type': 'number', 'label': '视频长度', 'field': 'frame_count', 'default': 81, 'min': 1, 'max': 16384, 'step': 4},
        'batch_size': {'type': 'number', 'label': '批次数量', 'field': 'batch_size', 'default': 1, 'min': 1, 'max': 4096},
        'temperature': {'type': 'number', 'label': '轨迹温度', 'field': 'track_temperature', 'default': 220.0, 'min': 1, 'max': 1000, 'step': 0.1},
        'topk': {'type': 'number', 'label': 'TopK', 'field': 'track_topk', 'default': 2, 'min': 1, 'max': 10},
    },
    'WanSoundImageToVideo': {
        'width': {'type': 'number', 'label': '宽度', 'field': 'width', 'default': 832, 'min': 16, 'max': 16384, 'step': 16},
        'height': {'type': 'number', 'label': '高度', 'field': 'height', 'default': 480, 'min': 16, 'max': 16384, 'step': 16},
        'length': {'type': 'number', 'label': '视频长度', 'field': 'frame_count', 'default': 77, 'min': 1, 'max': 16384, 'step': 4},
        'batch_size': {'type': 'number', 'label': '批次数量', 'field': 'batch_size', 'default': 1, 'min': 1, 'max': 4096},
    },
    'WanHuMoImageToVideo': {
        'width': {'type': 'number', 'label': '宽度', 'field': 'width', 'default': 832, 'min': 16, 'max': 16384, 'step': 16},
        'height': {'type': 'number', 'label': '高度', 'field': 'height', 'default': 480, 'min': 16, 'max': 16384, 'step': 16},
        'length': {'type': 'number', 'label': '视频长度', 'field': 'frame_count', 'default': 97, 'min': 1, 'max': 16384, 'step': 4},
        'batch_size': {'type': 'number', 'label': '批次数量', 'field': 'batch_size', 'default': 1, 'min': 1, 'max': 4096},
    },
    'WanAnimateToVideo': {
        'width': {'type': 'number', 'label': '宽度', 'field': 'width', 'default': 832, 'min': 16, 'max': 16384, 'step': 16},
        'height': {'type': 'number', 'label': '高度', 'field': 'height', 'default': 480, 'min': 16, 'max': 16384, 'step': 16},
        'length': {'type': 'number', 'label': '视频长度', 'field': 'frame_count', 'default': 77, 'min': 1, 'max': 16384, 'step': 4},
        'batch_size': {'type': 'number', 'label': '批次数量', 'field': 'batch_size', 'default': 1, 'min': 1, 'max': 4096},
        'continue_motion_max_frames': {'type': 'number', 'label': '运动延续帧数', 'field': 'continue_motion_max_frames', 'default': 5, 'min': 1, 'max': 16384, 'step': 4},
    },
    'Wan22FunControlToVideo': {
        'width': {'type': 'number', 'label': '宽度', 'field': 'width', 'default': 832, 'min': 16, 'max': 16384, 'step': 16},
        'height': {'type': 'number', 'label': '高度', 'field': 'height', 'default': 480, 'min': 16, 'max': 16384, 'step': 16},
        'length': {'type': 'number', 'label': '视频长度', 'field': 'frame_count', 'default': 81, 'min': 1, 'max': 16384, 'step': 4},
        'batch_size': {'type': 'number', 'label': '批次数量', 'field': 'batch_size', 'default': 1, 'min': 1, 'max': 4096},
    },
    'WanFunInpaintToVideo': {
        'width': {'type': 'number', 'label': '宽度', 'field': 'width', 'default': 832, 'min': 16, 'max': 16384, 'step': 16},
        'height': {'type': 'number', 'label': '高度', 'field': 'height', 'default': 480, 'min': 16, 'max': 16384, 'step': 16},
        'length': {'type': 'number', 'label': '视频长度', 'field': 'frame_count', 'default': 81, 'min': 1, 'max': 16384, 'step': 4},
        'batch_size': {'type': 'number', 'label': '批次数量', 'field': 'batch_size', 'default': 1, 'min': 1, 'max': 4096},
    },
    'WanSCAILToVideo': {
        'width': {'type': 'number', 'label': '宽度', 'field': 'width', 'default': 512, 'min': 32, 'max': 16384, 'step': 32},
        'height': {'type': 'number', 'label': '高度', 'field': 'height', 'default': 896, 'min': 32, 'max': 16384, 'step': 32},
        'length': {'type': 'number', 'label': '视频长度', 'field': 'frame_count', 'default': 81, 'min': 1, 'max': 16384, 'step': 4},
        'batch_size': {'type': 'number', 'label': '批次数量', 'field': 'batch_size', 'default': 1, 'min': 1, 'max': 4096},
        'pose_strength': {'type': 'number', 'label': '姿态强度', 'field': 'pose_strength', 'default': 1.0, 'min': 0, 'max': 10, 'step': 0.01},
        'pose_start': {'type': 'number', 'label': '姿态起始步', 'field': 'pose_start', 'default': 0.0, 'min': 0, 'max': 1, 'step': 0.01},
        'pose_end': {'type': 'number', 'label': '姿态结束步', 'field': 'pose_end', 'default': 1.0, 'min': 0, 'max': 1, 'step': 0.01},
    },
    'Wan22ImageToVideoLatent': {
        'width': {'type': 'number', 'label': '宽度', 'field': 'width', 'default': 1280, 'min': 32, 'max': 16384, 'step': 32},
        'height': {'type': 'number', 'label': '高度', 'field': 'height', 'default': 704, 'min': 32, 'max': 16384, 'step': 32},
        'length': {'type': 'number', 'label': '视频长度', 'field': 'frame_count', 'default': 49, 'min': 1, 'max': 16384, 'step': 4},
        'batch_size': {'type': 'number', 'label': '批次数量', 'field': 'batch_size', 'default': 1, 'min': 1, 'max': 4096},
    },
    'WanInfiniteTalkToVideo': {
        'width': {'type': 'number', 'label': '宽度', 'field': 'width', 'default': 832, 'min': 16, 'max': 16384, 'step': 16},
        'height': {'type': 'number', 'label': '高度', 'field': 'height', 'default': 480, 'min': 16, 'max': 16384, 'step': 16},
        'length': {'type': 'number', 'label': '视频长度', 'field': 'frame_count', 'default': 81, 'min': 1, 'max': 16384, 'step': 4},
        'motion_frame_count': {'type': 'number', 'label': '运动帧数', 'field': 'motion_frame_count', 'default': 9, 'min': 1, 'max': 33, 'step': 1},
        'audio_scale': {'type': 'number', 'label': '音频强度', 'field': 'audio_scale', 'default': 1.0, 'min': -10.0, 'max': 10.0, 'step': 0.01},
    },
    # WanPhantomSubjectToVideo 特殊输出（负向分两种），参数同 WanImageToVideo
    'WanPhantomSubjectToVideo': {
        'width': {'type': 'number', 'label': '宽度', 'field': 'width', 'default': 832, 'min': 16, 'max': 16384, 'step': 16},
        'height': {'type': 'number', 'label': '高度', 'field': 'height', 'default': 480, 'min': 16, 'max': 16384, 'step': 16},
        'length': {'type': 'number', 'label': '视频长度', 'field': 'frame_count', 'default': 81, 'min': 1, 'max': 16384, 'step': 4},
        'batch_size': {'type': 'number', 'label': '批次数量', 'field': 'batch_size', 'default': 1, 'min': 1, 'max': 4096},
    },
}


def _build_link_maps(nodes, links):
    """解析链接关系，构建正向和反向映射（兼容 list 和 dict 两种链接格式）"""
    link_map = {}         # link_id -> (from_node, from_slot, to_node, to_slot)
    reverse_map = {}      # (to_node_id, input_name) -> [(from_node_id, from_slot)]

    # 标准化链接格式：dict -> list
    normalized_links = []
    for link in links:
        if isinstance(link, dict):
            normalized_links.append([
                link['id'], link['origin_id'], link['origin_slot'],
                link['target_id'], link['target_slot'],
                link.get('type', '*'),
            ])
        else:
            normalized_links.append(link)

    for link in normalized_links:
        link_id = link[0]
        from_node = str(link[1])
        from_slot = link[2]
        to_node = str(link[3])
        to_slot = link[4]
        link_map[link_id] = (from_node, from_slot, to_node, to_slot)

    # 构建反向映射：找到每个目标节点输入端对应的源节点
    for link in normalized_links:
        link_id, from_node, from_slot, to_node, to_slot, *_ = link
        to_node_s = str(to_node)
        from_node_s = str(from_node)
        # 在目标节点的 inputs 中查找匹配的 link_id 对应的 input name
        for node in nodes:
            if str(node['id']) == to_node_s:
                for inp in node.get('inputs', []):
                    if inp.get('link') == link_id:
                        key = (to_node_s, inp['name'])
                        if key not in reverse_map:
                            reverse_map[key] = []
                        reverse_map[key].append((from_node_s, from_slot))
                        break
                break

    return link_map, reverse_map


def _resolve_reroute_links(link_map, nodes_by_id):
    """解析 link_map 中经过 Reroute/SetNode 等透传节点的链接，替换为直接源节点

    Reroute 和 SetNode 都是纯连接器（1 输入 → 1 输出），转换时会被跳过。
    但其他节点可能引用它们作为输入源，需要穿透它们找到真正的源节点。
    """
    resolved = {}
    for link_id, (from_node, from_slot, to_node, to_slot) in link_map.items():
        src_nid = str(from_node)
        src_slot = from_slot
        visited = set()
        while src_nid in nodes_by_id:
            node = nodes_by_id[src_nid]
            if node.get('type') not in ('Reroute', 'SetNode'):
                break
            if src_nid in visited:
                break  # 防止循环引用
            visited.add(src_nid)
            inputs = node.get('inputs', [])
            if not inputs:
                break
            inner_link = inputs[0].get('link')
            if inner_link is None or inner_link not in link_map:
                break
            src_nid, src_slot, _, _ = link_map[inner_link]
            src_nid = str(src_nid)
        resolved[link_id] = (src_nid, src_slot, to_node, to_slot)
    return resolved


def _trace_clip_polarity(nodes, reverse_map):
    """通过链接追踪 CLIPTextEncode 节点是正向还是负向提示词

    遍历所有 KSampler 节点，找到其 positive/negative 输入连接到的 CLIPTextEncode
    """
    clip_polarity: dict[str, str] = {}
    nodes_by_id = {str(n['id']): n for n in nodes}
    source_types = ('KSampler', 'KSamplerAdvanced', 'SamplerCustom',
                    'SamplerCustomAdvanced', 'CFGGuider')
    pos_inputs = ('positive', 'positive_cond', 'positive_conditioning')
    neg_inputs = ('negative', 'negative_cond', 'negative_conditioning')
    all_inputs = pos_inputs + neg_inputs

    def _trace_back(node_id: str, polarity: str, visited: set) -> None:
        if node_id in visited:
            return
        visited.add(node_id)
        node = nodes_by_id.get(node_id)
        if not node:
            return
        if 'CLIPTextEncode' in node.get('type', ''):
            clip_polarity[node_id] = polarity
            return
        # 穿透中间节点，继续向上一层追踪
        for inp_name in all_inputs:
            key = (node_id, inp_name)
            if key in reverse_map:
                for from_node_id, _ in reverse_map[key]:
                    is_pos = 'positive' in inp_name
                    child_polarity = 'prompt' if is_pos else 'negative_prompt'
                    _trace_back(from_node_id, child_polarity, visited)

    for node in nodes:
        nid = str(node['id'])
        ntype = node.get('type', '')
        if ntype not in source_types:
            continue
        for inp_name in pos_inputs:
            key = (nid, inp_name)
            if key in reverse_map:
                for from_node_id, _ in reverse_map[key]:
                    _trace_back(from_node_id, 'prompt', set())
        for inp_name in neg_inputs:
            key = (nid, inp_name)
            if key in reverse_map:
                for from_node_id, _ in reverse_map[key]:
                    _trace_back(from_node_id, 'negative_prompt', set())

    return clip_polarity


def _infer_loadimage_role(node_id, link_map, nodes):
    """追踪 LoadImage 节点的下游连接，判断其角色（主输入图/参考图）

    返回 (field_name, label)：主输入图用 'image_asset_hash'，参考图用 'target_asset_hash'
    """
    # 收集该 LoadImage 的所有输出连接
    downstream_nodes = []
    for (from_node, from_slot, to_node, to_slot) in link_map.values():
        if from_node == node_id:
            downstream_nodes.append((to_node, to_slot))

    nodes_by_id = {str(n['id']): n for n in nodes}

    # 查找下游节点类型
    for to_node, to_slot in downstream_nodes:
        n = nodes_by_id.get(to_node)
        if n is None:
            continue
        ntype = n.get('type', '')

        # 连接 VAEEncode → 进入采样流程 → 主输入图
        if 'VAEEncode' in ntype:
            return 'image_asset_hash', '输入图片'

        # UUID Group Node：穿透查看内部连接
        if UUID_TYPE_RE.match(ntype):
            sub_data = n.get('subgraph') or n.get('workflow') or n.get('data')
            if sub_data and isinstance(sub_data, dict) and sub_data.get('nodes'):
                sub_nodes = sub_data['nodes']
                sub_links = sub_data.get('links', [])
                # 构建子图链接映射
                sub_link_map = {}
                for sl in sub_links:
                    sub_link_map[sl['id']] = (
                        str(sl['origin_id']), sl['origin_slot'],
                        str(sl['target_id']), sl['target_slot'],
                    )
                # 查找 -10（子图输入节点）在此 slot 的连接
                sub_input_slot = to_slot
                for _, (from_id, from_slot, to_id, to_slot2) in sub_link_map.items():
                    if from_id == '-10' and from_slot == sub_input_slot:
                        # 递归检查子图目标节点
                        for sn in sub_nodes:
                            if str(sn['id']) == to_id:
                                sntype = sn.get('type', '')
                                if 'VAEEncode' in sntype:
                                    return 'image_asset_hash', '输入图片'
                                # 继续追踪（如 FluxKontextImageScale → VAEEncode）
                                for _, (fid, fslot, tid, tslot) in sub_link_map.items():
                                    if fid == to_id:
                                        for sn2 in sub_nodes:
                                            if str(sn2['id']) == tid and 'VAEEncode' in sn2.get('type', ''):
                                                return 'image_asset_hash', '输入图片'

    # 非 VAEEncode 连接 → 参考图
    if downstream_nodes:
        return 'target_asset_hash', '参考图片'

    return 'image_asset_hash', '输入图片'


def _is_widget_input(inp):
    """判断一个 input 是否是控件类型（可编辑参数）"""
    if inp.get('widget'):
        return True
    t = inp.get('type', '')
    return t in ('INT', 'FLOAT', 'STRING', 'COMBO', 'BOOLEAN', 'INT:seed')


def _get_input_type(inp):
    """安全获取输入类型字符串（type 可能是 str 或 list）"""
    t = inp.get('type') or 'STRING'
    if isinstance(t, list):
        return str(t[0]).upper() if t else 'STRING'
    return str(t).upper()


def _get_input_value(inp, widgets_values, widget_idx):
    """从 widgets_values 中按索引或按名称获取输入值（兼容 list 和 dict 格式）"""
    val = None
    if isinstance(widgets_values, dict):
        # dict 格式：按键名查找
        val = widgets_values.get(inp.get('name'))
    elif isinstance(widgets_values, list) and widget_idx < len(widgets_values):
        # list 格式：按索引查找
        val = widgets_values[widget_idx]
    if val is None:
        val = inp.get('default')
    return val


def _convert_single_value(val, inp_type):
    """将值按类型转换"""
    if val is None:
        return None
    t = (inp_type or '').upper()
    try:
        if t.startswith('INT'):
            return int(val)
        elif t.startswith('FLOAT'):
            return float(val)
        elif t == 'BOOLEAN':
            if isinstance(val, bool):
                return val
            return str(val).lower() in ('true', '1', 'yes')
        elif t == 'COMBO':
            return str(val)
        else:
            return str(val) if not isinstance(val, (int, float, bool)) else val
    except (ValueError, TypeError):
        return val


def _classify_prompt(inp_name: str, label: str = '') -> str:
    """判断输入是否为提示词类型，返回 'prompt' / 'negative_prompt' / ''"""
    name_lower = inp_name.lower()
    label_lower = (label or '').lower()
    pos = {'prompt', 'positive_prompt', 'positive prompt', 'text'}
    neg = {'negative_prompt', 'negative_text', 'negative text'}
    if name_lower in pos or label_lower in pos:
        return 'prompt'
    if name_lower in neg or label_lower in neg:
        return 'negative_prompt'
    return ''


def _is_seed_name(inp_name: str, label: str = '') -> bool:
    """判断输入是否为种子类型"""
    name_lower = inp_name.lower()
    label_lower = (label or '').lower()
    return name_lower in ('noise_seed', 'seed') or 'seed' in label_lower


def convert_native_to_api(native_data, definitions=None):
    nodes = native_data.get('nodes', [])
    links = native_data.get('links', [])

    # ---- 过滤被静音的节点（mode=4 = Never）及其关联链接 ----
    muted_ids: set[str] = {str(n['id']) for n in nodes if n.get('mode', 0) == 4}
    if muted_ids:
        nodes = [n for n in nodes if str(n['id']) not in muted_ids]
        links = [l for l in links if str(l[1]) not in muted_ids and str(l[3]) not in muted_ids]

    # ---- 预处理：将 definitions.subgraphs 中的子图数据注入到对应 UUID 节点 ----
    # ComfyUI 原生格式将子图定义在顶层 definitions，而非节点内部
    # 嵌套 Group Node 需要传递外层 definitions 给递归调用
    if definitions is None:
        definitions = native_data.get('definitions', {})
    subgraph_defs: dict[str, dict] = {}
    for sg in definitions.get('subgraphs', []):
        sg_id = sg.get('id', '')
        if sg_id:
            subgraph_defs[sg_id] = {
                'nodes': sg.get('nodes', []),
                'links': sg.get('links', []),
            }

    for node in nodes:
        ntype = node.get('type', '')
        if UUID_TYPE_RE.match(ntype) and ntype in subgraph_defs:
            if not node.get('subgraph') or not node['subgraph'].get('nodes'):
                node['subgraph'] = subgraph_defs[ntype]

    link_map, reverse_map = _build_link_maps(nodes, links)
    clip_polarity = _trace_clip_polarity(nodes, reverse_map)

    # 构建节点 ID 查找表（用于 UUID ref 追踪 PrimitiveNode 值）
    nodes_by_id: dict[str, dict] = {str(n['id']): n for n in nodes}

    # 解析 Reroute 节点链：将 link_map 中通过 Reroute 的引用替换为直接源
    link_map = _resolve_reroute_links(link_map, nodes_by_id)

    node_api = {}
    field_mapping = {}
    ui_fields = []
    seen_ui_field_names = set()
    clip_fallback_count = 0

    # ---- 预扫描：为多个 LoadImage 节点分配唯一字段名 ----
    loadimage_field_map = {}  # node_id -> (field_name, label)
    loadimage_nodes = [(str(n['id']), n) for n in nodes if n.get('type') == 'LoadImage']
    seen_roles: dict[str, int] = {}
    for nid, _ in loadimage_nodes:
        field_name, label = _infer_loadimage_role(nid, link_map, nodes)
        if field_name in seen_roles:
            seen_roles[field_name] += 1
            field_name = f'{field_name}_{seen_roles[field_name]}'
        else:
            seen_roles[field_name] = 1
        loadimage_field_map[nid] = (field_name, label)

    for node in nodes:
        nid = str(node['id'])
        ntype = node.get('type', '')

        if ntype in SKIP_TYPES:
            continue

        widgets_values = node.get('widgets_values', [])
        node_inputs = node.get('inputs', [])
        inputs = {}

        # ---------- 处理子图 / 嵌套工作流 ----------
        subgraph_data = node.get('subgraph') or node.get('workflow') or node.get('data')

        # UUID 类型的 Group Node：如果有嵌入子图 → 展开子节点后跳过包装器
        # 如果是子图引用（无嵌入子节点）→ 保留它，ComfyUI 运行时解析
        if UUID_TYPE_RE.match(ntype):
            if subgraph_data and isinstance(subgraph_data, dict) and subgraph_data.get('nodes'):
                # 有嵌入子图：递归转换子图，保持 UUID 折叠状态
                sub_api, sub_mapping, sub_fields, _ = convert_native_to_api(
                    {'nodes': subgraph_data['nodes'], 'links': subgraph_data.get('links', [])},
                    definitions=definitions,
                )

                # ---- 先从 UUID 包装器输入提取 UI 字段（优先级高于子图内部字段） ----
                sg_nodes = {str(sn['id']): sn for sn in subgraph_data['nodes']}
                proxy_list = node.get('properties', {}).get('proxyWidgets', [])
                proxy_idx = 0  # 按位置匹配未链接的 widget 输入

                # 预计算内部节点的完整 widget 列表（含隐藏 widget）
                # 部分节点有不在 inputs 中的隐藏 widget（如 KSampler 的 control_after_generate）
                _node_visible_widgets: dict[str, list[str]] = {}
                _node_hidden_widget_pos: dict[str, dict[int, str]] = {}
                for _sn_id, _sn in sg_nodes.items():
                    _ntype = _sn.get('type', '')
                    _visible = [inp['name'] for inp in _sn.get('inputs', []) if 'widget' in inp]
                    _node_visible_widgets[_sn_id] = _visible
                    _hidden: dict[int, str] = {}
                    # KSampler 系列：control_after_generate 在 seed (索引0) 之后
                    if _ntype in ('KSampler', 'KSamplerAdvanced'):
                        _hidden[1] = 'control_after_generate'
                    if _hidden:
                        _node_hidden_widget_pos[_sn_id] = _hidden

                def _get_proxy_info():
                    """从当前 proxyWidget 对应的内部节点提取 (internal_nid, internal_inp, value)"""
                    nonlocal proxy_idx
                    if proxy_idx < len(proxy_list) and len(proxy_list[proxy_idx]) >= 2:
                        pw = proxy_list[proxy_idx]
                        proxy_idx += 1
                        internal_nid = str(pw[0])
                        internal_inp = str(pw[1])
                        pn = sg_nodes.get(internal_nid)
                        val = None
                        if pn:
                            wv = pn.get('widgets_values', [])
                            if isinstance(wv, list) and wv:
                                # 构建完整 widget 顺序表（可见 + 已知隐藏）
                                visible = _node_visible_widgets.get(internal_nid, [])
                                hidden = _node_hidden_widget_pos.get(internal_nid, {})
                                all_widgets = list(visible)
                                for pos in sorted(hidden.keys(), reverse=True):
                                    all_widgets.insert(pos, hidden[pos])
                                try:
                                    idx = all_widgets.index(internal_inp)
                                    if idx < len(wv):
                                        val = wv[idx]
                                except ValueError:
                                    pass
                            elif isinstance(wv, dict):
                                val = wv.get(internal_inp)
                        return internal_nid, internal_inp, val
                    else:
                        proxy_idx += 1
                    return None, None, None

                for inp in node_inputs:
                    inp_name = inp['name']
                    inp_type = _get_input_type(inp)
                    label = (inp.get('label') or '').strip()
                    link = inp.get('link')

                    if link is not None:
                        # 如果是 widget 输入，仍占一个 proxyWidget 位（跳过它）
                        if _is_widget_input(inp):
                            _get_proxy_info()
                        # 保存外部连接，供 workflow_registry 子图展开时解析 -10 引用
                        if link in link_map:
                            src_nid, src_slot, _, _ = link_map[link]
                            inputs[inp_name] = [src_nid, src_slot]
                        if inp_type in ('IMAGE', 'MASK'):
                            # 如果是链接到 LoadImage，跳过（LoadImage 自己已生成图片字段）
                            src_type = ''
                            src_nid = None
                            mapping_target = f'{nid}.inputs.{inp_name}'
                            if link in link_map:
                                src_nid = link_map[link][0]
                                src_node = nodes_by_id.get(src_nid)
                                src_type = src_node.get('type', '') if src_node else ''
                                if src_node:
                                    src_inputs = src_node.get('inputs', [])
                                    src_slot = link_map[link][1]
                                    if isinstance(src_inputs, list) and src_slot < len(src_inputs):
                                        src_inp = src_inputs[src_slot]
                                        if isinstance(src_inp, dict):
                                            mapping_target = f'{src_nid}.inputs.{src_inp.get("name", inp_name)}'
                            if src_type == 'LoadImage':
                                continue
                            img_count = sum(1 for f in ui_fields if f.get('role') == 'image_upload')
                            if img_count == 0:
                                safe_name = 'image_asset_hash'
                            elif img_count == 1:
                                safe_name = 'target_asset_hash'
                            else:
                                safe_name = f'target_asset_hash_{img_count}'
                            if safe_name not in seen_ui_field_names:
                                seen_ui_field_names.add(safe_name)
                                field_mapping[safe_name] = mapping_target
                                ui_fields.append({
                                    'name': safe_name, 'type': 'string',
                                    'label': label or inp_name,
                                    'role': 'image_upload', 'default': '',
                                })
                        elif inp_type == 'STRING':
                            prompt_type = _classify_prompt(inp_name)
                            if not prompt_type:
                                continue
                            # 链接型提示词：从源节点提取默认文本，映射到源节点
                            default_val = ''
                            mapping_target = f'{nid}.inputs.{inp_name}'
                            if link in link_map:
                                src_nid, src_slot = link_map[link][:2]
                                src_node = nodes_by_id.get(src_nid)
                                if src_node:
                                    wv = src_node.get('widgets_values', [])
                                    if isinstance(wv, list) and src_slot < len(wv):
                                        default_val = str(wv[src_slot]) if wv[src_slot] else ''
                                    # 查找源节点的输入名（按 slot 顺序）
                                    src_inputs = src_node.get('inputs', [])
                                    if isinstance(src_inputs, list) and src_slot < len(src_inputs):
                                        src_inp = src_inputs[src_slot]
                                        if isinstance(src_inp, dict):
                                            mapping_target = f'{src_nid}.inputs.{src_inp.get("name", inp_name)}'
                            field_name = prompt_type
                            if field_name not in seen_ui_field_names:
                                seen_ui_field_names.add(field_name)
                                field_mapping[field_name] = mapping_target
                                ui_fields.append({
                                    'name': field_name, 'type': 'string',
                                    'default': default_val,
                                })
                        continue

                    # 只有带 widget 的输入才对应 proxyWidget 槽位
                    # 否则跳过（如可选的 IMAGE/MASK 输入不占槽位）
                    if not _is_widget_input(inp):
                        continue

                    # 未链接的 widget 输入：获取对应 proxyWidget 和内部节点值
                    internal_nid, internal_inp, proxy_val = _get_proxy_info()
                    # proxyWidget 引用的内部节点必须在子图中存在且不在 SKIP_TYPES 中
                    # PrimitiveNode 等会被跳过不写入 node_api → 改用 wrapper 自身输入作为 mapping 目标
                    if internal_nid and internal_nid not in sg_nodes:
                        print(f'WARN [UUID:{nid}] proxyWidget 引用不存在的内部节点 {internal_nid}，跳过')
                        continue
                    if internal_nid and internal_nid in sg_nodes:
                        internal_ntype = sg_nodes[internal_nid].get('type', '')
                        if internal_ntype in SKIP_TYPES:
                            # PrimitiveNode: 值在 _get_proxy_info 中已提取为 proxy_val，映射目标改为 wrapper 自身
                            # -10 引用会将 wrapper 输入路由到实际消费者节点
                            internal_nid = None
                    # 生成正确的嵌套路径：wrapperId.内部节点ID.inputs.内部输入名
                    inner_target = f'{nid}.{internal_nid}.inputs.{internal_inp}' if internal_nid else f'{nid}.inputs.{inp_name}'

                    # 图片类型（未链接的 IMAGE/MASK widget）
                    if inp_type in ('IMAGE', 'MASK'):
                        img_count = sum(1 for f in ui_fields if f.get('role') == 'image_upload')
                        if img_count == 0:
                            safe_name = 'image_asset_hash'
                        elif img_count == 1:
                            safe_name = 'target_asset_hash'
                        else:
                            safe_name = f'target_asset_hash_{img_count}'
                        default_val = str(proxy_val) if proxy_val is not None and not isinstance(proxy_val, (bool,)) else ''
                        if safe_name not in seen_ui_field_names:
                            seen_ui_field_names.add(safe_name)
                            field_mapping[safe_name] = inner_target
                            ui_fields.append({
                                'name': safe_name, 'type': 'string',
                                'label': label or inp_name,
                                'role': 'image_upload', 'default': default_val,
                            })

                    # 字符串 + 提示词标签/名称 → 提示词字段
                    elif inp_type == 'STRING':
                        prompt_type = _classify_prompt(inp_name, label)
                        if not prompt_type:
                            continue
                        field_name = prompt_type
                        default_val = str(proxy_val) if isinstance(proxy_val, str) else ''
                        if field_name not in seen_ui_field_names:
                            seen_ui_field_names.add(field_name)
                            field_mapping[field_name] = inner_target
                            ui_fields.append({
                                'name': field_name, 'type': 'string',
                                'default': default_val,
                            })

                    # seed / noise_seed
                    elif inp_type == 'INT' and _is_seed_name(inp_name, label):
                        field_name = 'seed'
                        default_val = int(proxy_val) if isinstance(proxy_val, (int, float)) else 0
                        if field_name not in seen_ui_field_names:
                            seen_ui_field_names.add(field_name)
                            field_mapping[field_name] = inner_target
                            ui_fields.append({
                                'name': field_name, 'type': 'number',
                                'default': default_val,
                                'min': 0,
                                'max': 0xffffffffffffffff,
                            })

                    # 通用 widget 处理：FLOAT、BOOLEAN、COMBO、非 seed 的 INT 等
                    else:
                        # 如果内部节点是模型加载器类型 → 跳过（不暴露到前端）
                        if internal_nid:
                            pn = sg_nodes.get(internal_nid)
                            if pn and pn.get('type', '') in HIDDEN_UI_TYPES:
                                continue
                        # 优先用内部节点的标题作为字段名，否则用输入名/label
                        internal_title = ''
                        if internal_nid:
                            pn = sg_nodes.get(internal_nid)
                            if pn:
                                internal_title = pn.get('title', '') or ''
                        field_name = _title_to_field_name(internal_title)
                        if not field_name:
                            # 回退到 label 或内部输入名
                            field_name = _title_to_field_name(label) or _title_to_field_name(internal_inp) or internal_inp
                        # 若回退名字在隐藏列表中 → 用 wrapper 输入名再试
                        if _is_hidden_field_name(field_name):
                            field_name = _title_to_field_name(inp_name) or inp_name
                        # 内部输入名是模型/VAE/CLIP 选择器且无标题覆盖 → 不暴露
                        if _is_hidden_field_name(internal_inp) and not internal_title:
                            continue
                        if not field_name or field_name in seen_ui_field_names or _is_hidden_field_name(field_name):
                            continue
                        # 确定类型
                        if inp_type == 'BOOLEAN':
                            field_type = 'boolean'
                            default_val = bool(proxy_val) if proxy_val is not None else False
                        elif inp_type in ('INT', 'FLOAT'):
                            field_type = 'number'
                            default_val = proxy_val if isinstance(proxy_val, (int, float)) else (0 if inp_type == 'INT' else 0.0)
                        elif inp_type == 'COMBO':
                            field_type = 'combo'
                            default_val = str(proxy_val) if proxy_val is not None else ''
                        else:
                            field_type = 'string'
                            default_val = str(proxy_val) if proxy_val is not None else ''
                        seen_ui_field_names.add(field_name)
                        field_mapping[field_name] = inner_target
                        entry = {'name': field_name, 'type': field_type, 'default': default_val}
                        if label:
                            entry['label'] = label
                        if inp_type == 'COMBO':
                            pn = sg_nodes.get(internal_nid) if internal_nid else None
                            pn_inputs = pn.get('inputs', []) if pn else []
                            for pi in pn_inputs:
                                if pi.get('name') == internal_inp and isinstance(pi.get('options'), list):
                                    entry['options'] = pi['options']
                                    break
                        ui_fields.append(entry)

                # UUID Group Node 保持折叠状态，不展开子图
                # 存储子图供 build_prompt_graph 阶段展开，前端只暴露包装器输入参数
                # raw_nodes/raw_links 用于 -10/-20 引用解析

                node_api[nid] = {
                    'class_type': ntype,
                    'inputs': inputs,
                    '_subgraph': {
                        'nodes': sub_api,
                        'raw_nodes': subgraph_data['nodes'],
                        'raw_links': subgraph_data.get('links', []),
                        'wrapper_input_defs': node_inputs,
                    },
                }

                continue
            else:
                # 子图引用（无嵌入子节点）：保留，ComfyUI subgraph_manager 会解析
                pass

        if subgraph_data and isinstance(subgraph_data, dict):
            sub_nodes = subgraph_data.get('nodes')
            if sub_nodes and not UUID_TYPE_RE.match(ntype):
                sub_api, sub_mapping, sub_fields, _ = convert_native_to_api(
                    {'nodes': sub_nodes, 'links': subgraph_data.get('links', [])},
                    definitions=definitions,
                )
                for fname, target in sub_mapping.items():
                    full_target = f'{nid}.{target}'
                    sub_fname = fname
                    if sub_fname in seen_ui_field_names:
                        sub_fname = f'{nid}_{fname}'
                    field_mapping[sub_fname] = full_target
                    if sub_fname not in seen_ui_field_names:
                        seen_ui_field_names.add(sub_fname)
                        for sf in sub_fields:
                            if sf['name'] == fname:
                                sub_entry = dict(sf)
                                sub_entry['name'] = sub_fname
                                ui_fields.append(sub_entry)
                                break
                node_api[nid] = {'class_type': ntype, 'inputs': inputs if inputs else {}, '_subgraph': sub_api}
                continue

        # ---------- KSampler / KSamplerAdvanced ----------
        is_ksampler = ntype in ('KSampler', 'KSamplerAdvanced')

        if is_ksampler:
            widget_config = KSAMPLER_WIDGET_MAP
            for idx, (field_name, cast_fn, cfg) in widget_config.items():
                if idx < len(widgets_values) and widgets_values[idx] is not None:
                    val = widgets_values[idx]
                    try:
                        val = cast_fn(val)
                    except (ValueError, TypeError):
                        val = cfg.get('default', 0)
                    inputs[field_name] = val
                    field_mapping[field_name] = f'{nid}.inputs.{field_name}'
                    field_cfg = dict(cfg)
                    if field_name == 'sampler_name':
                        field_cfg['options'] = SAMPLER_NAMES
                    elif field_name == 'scheduler':
                        field_cfg['options'] = SCHEDULERS
                    if field_cfg.pop('label', None):
                        pass
                    fname = field_name
                    if fname not in seen_ui_field_names:
                        seen_ui_field_names.add(fname)
                        ui_fields.append({'name': fname, **field_cfg})

            # 处理链接输入 (model, positive, negative, latent_image)
            for inp in node_inputs:
                inp_name = inp['name']
                link = inp.get('link')
                if link is not None and link in link_map:
                    from_node, from_slot, _, _ = link_map[link]
                    inputs[inp_name] = [from_node, from_slot]

            if inputs:
                node_api[nid] = {'class_type': ntype, 'inputs': inputs}
            continue

        # ---------- CLIPTextEncode 系列 ----------
        is_clip = 'CLIPTextEncode' in ntype

        if is_clip:
            for inp in node_inputs:
                inp_name = inp['name']
                link = inp.get('link')
                if link is not None and link in link_map:
                    from_node, from_slot, _, _ = link_map[link]
                    inputs[inp_name] = [from_node, from_slot]
                elif inp_name == 'text':
                    # 正负向判定：优先用链接追踪，其次按出现顺序回退
                    is_neg = clip_polarity.get(nid) == 'negative_prompt'
                    if nid not in clip_polarity:
                        clip_fallback_count += 1
                        is_neg = clip_fallback_count > 1

                    # 查找 text 值：计算 text 在所有 widget 输入中的位置
                    text_val = None
                    widget_pos = 0
                    for ni in node_inputs:
                        if ni.get('name') == 'text':
                            if widget_pos < len(widgets_values):
                                text_val = widgets_values[widget_pos]
                            break
                        if ni.get('link') is None and _is_widget_input(ni):
                            widget_pos += 1
                    if text_val is None:
                        text_val = inp.get('default', '')

                    inputs[inp_name] = text_val
                    fname = 'negative_prompt' if is_neg else 'prompt'
                    # 如果 prompt 已被其他节点（如 TextGenerate 类）占用，退化为 negative_prompt
                    if fname == 'prompt' and fname in seen_ui_field_names:
                        fname = 'negative_prompt'
                    field_mapping[fname] = f'{nid}.inputs.text'
                    if fname not in seen_ui_field_names:
                        seen_ui_field_names.add(fname)
                        ui_fields.append({
                            'name': fname,
                            'type': 'string',
                            'default': text_val,
                        })

            if inputs:
                node_api[nid] = {'class_type': ntype, 'inputs': inputs}
            continue

        # ---------- 特殊配置节点 (Checkpoint, LoRA, ControlNet 等) ----------
        special_cfg = SPECIAL_NODE_CONFIGS.get(ntype)

        if special_cfg:
            widget_idx = 0
            for inp in node_inputs:
                inp_name = inp['name']
                link = inp.get('link')
                if link is not None and link in link_map:
                    from_node, from_slot, _, _ = link_map[link]
                    inputs[inp_name] = [from_node, from_slot]
                    if _is_widget_input(inp):
                        widget_idx += 1
                    continue

                cfg = special_cfg.get(inp_name)
                if cfg:
                    val = _get_input_value(inp, widgets_values, widget_idx)
                    if val is None:
                        val = cfg.get('default', inp.get('default', ''))

                    if val is not None:
                        inputs[inp_name] = val
                        # LoadImage 节点使用预扫描分配的唯一字段名
                        if ntype == 'LoadImage' and nid in loadimage_field_map:
                            field_name, label = loadimage_field_map[nid]
                        else:
                            field_name = cfg['field']
                            label = cfg.get('label', '')
                        # 模型/LoRA/VAE 加载器：参数用于图执行但不暴露给前端
                        if ntype not in HIDDEN_UI_TYPES and not _is_hidden_field_name(field_name):
                            field_mapping[field_name] = f'{nid}.inputs.{inp_name}'
                            if field_name not in seen_ui_field_names:
                                seen_ui_field_names.add(field_name)
                                entry = {
                                    'name': field_name,
                                    'type': cfg['type'],
                                    'default': val,
                                }
                                if label:
                                    entry['label'] = label
                                # 图片上传类型标记 role，供前端识别
                                if ntype == 'LoadImage':
                                    entry['role'] = 'image_upload'
                                for k in ('min', 'max', 'step', 'options', 'tooltip'):
                                    if k in cfg:
                                        entry[k] = cfg[k]
                                ui_fields.append(entry)
                else:
                    # 该输入不在特殊配置中，但仍是 widget 类型则原样保留
                    if _is_widget_input(inp):
                        val = _get_input_value(inp, widgets_values, widget_idx)
                        if val is not None:
                            inputs[inp_name] = val
                            safe_name = FIELD_ALIASES.get(inp_name, inp_name)
                            if ntype not in HIDDEN_UI_TYPES and not _is_hidden_field_name(safe_name):
                                if safe_name not in seen_ui_field_names:
                                    seen_ui_field_names.add(safe_name)
                                    inp_type = _get_input_type(inp)
                                    entry = {'name': safe_name, 'type': 'number' if inp_type in ('INT', 'FLOAT') else 'string', 'default': val}
                                    if inp.get('min') is not None:
                                        entry['min'] = inp['min']
                                    if inp.get('max') is not None:
                                        entry['max'] = inp['max']
                                    if inp.get('step') is not None:
                                        entry['step'] = inp['step']
                                    field_mapping[safe_name] = f'{nid}.inputs.{inp_name}'
                                    ui_fields.append(entry)

                widget_idx += 1

            if inputs:
                node_api[nid] = {'class_type': ntype, 'inputs': inputs}
            continue

        # ---------- 通用/未知节点类型：提取所有 widget 参数 ----------
        is_uuid_ref = bool(UUID_TYPE_RE.match(ntype))  # UUID 子图引用节点
        widget_idx = 0
        for inp in node_inputs:
            inp_name = inp['name']
            link = inp.get('link')
            if link is not None and link in link_map:
                from_node, from_slot, _, _ = link_map[link]
                inputs[inp_name] = [from_node, from_slot]
                if _is_widget_input(inp):
                    widget_idx += 1

                # 追踪链接到 Primitive 节点的值作为 UI 字段（所有节点类型通用）
                src_node = nodes_by_id.get(str(from_node))
                src_type = src_node.get('type', '') if src_node else ''
                if src_type in PRIMITIVE_VALUE_TYPES or src_type in ('PrimitiveInt', 'PrimitiveFloat'):
                    wv = src_node.get('widgets_values', [])
                    if isinstance(wv, list) and from_slot < len(wv):
                        prim_val = wv[from_slot]
                    elif isinstance(wv, dict):
                        prim_val = list(wv.values())[from_slot] if from_slot < len(wv) else ''
                    else:
                        prim_val = ''
                    safe_name = FIELD_ALIASES.get(inp_name, inp_name)
                    if safe_name not in seen_ui_field_names and not _is_hidden_field_name(safe_name):
                        seen_ui_field_names.add(safe_name)
                        inp_t = _get_input_type(inp)
                        entry = {
                            'name': safe_name,
                            'type': 'string' if inp_t == 'STRING' else 'number',
                            'default': prim_val,
                        }
                        field_mapping[safe_name] = f'{from_node}.inputs.value'
                        ui_fields.append(entry)

                continue

            # UUID 子图引用节点的 IMAGE/MASK 类型输入 → 图片上传字段
            # 不写入 inputs（ComfyUI 不认空字符串），只生成 UI 字段和映射
            inp_type = _get_input_type(inp)
            if is_uuid_ref and inp_type in ('IMAGE', 'MASK') and link is None:
                image_count = sum(1 for f in ui_fields if f.get('role') == 'image_upload')
                if image_count == 0:
                    safe_name = 'image_asset_hash'
                elif image_count == 1:
                    safe_name = 'target_asset_hash'
                else:
                    safe_name = f'{inp_name}_asset_hash'
                label = inp.get('label') or inp.get('name')
                if safe_name not in seen_ui_field_names:
                    seen_ui_field_names.add(safe_name)
                    entry = {
                        'name': safe_name,
                        'type': 'string',
                        'role': 'image_upload',
                        'label': label,
                        'default': '',
                    }
                    field_mapping[safe_name] = f'{nid}.inputs.{inp_name}'
                    ui_fields.append(entry)
                widget_idx += 1
                continue

            if _is_widget_input(inp):
                val = _get_input_value(inp, widgets_values, widget_idx)
                if val is not None:
                    inputs[inp_name] = val
                elif is_uuid_ref:
                    # UUID 子图引用节点：widget 值取自 subgraph 定义，取默认值
                    inp_type = _get_input_type(inp)
                    if inp_type.startswith('INT'):
                        default_val = inp.get('default', 0)
                        if default_val is not None:
                            inputs[inp_name] = int(default_val)
                        else:
                            inputs[inp_name] = 0
                    elif inp_type.startswith('FLOAT'):
                        default_val = inp.get('default', 0.0)
                        if default_val is not None:
                            inputs[inp_name] = float(default_val)
                        else:
                            inputs[inp_name] = 0.0
                    elif inp_type == 'BOOLEAN':
                        inputs[inp_name] = bool(inp.get('default', False))
                    elif inp_type == 'COMBO':
                        inputs[inp_name] = str(inp.get('default', ''))
                    else:
                        inputs[inp_name] = str(inp.get('default', ''))
                # 为所有 widget 输入生成 UI 字段（跳过模型相关字段）
                safe_name = FIELD_ALIASES.get(inp_name, inp_name)
                if safe_name not in seen_ui_field_names and not _is_hidden_field_name(safe_name):
                    seen_ui_field_names.add(safe_name)
                    inp_type = _get_input_type(inp)
                    field_type = 'boolean' if inp_type == 'BOOLEAN' else ('number' if inp_type in ('INT', 'FLOAT') else 'string')
                    if inp_type == 'COMBO' and isinstance(inp.get('options'), list):
                        field_type = 'combo'
                    entry = {'name': safe_name, 'type': field_type, 'default': inputs.get(inp_name, inp.get('default', ''))}
                    if inp.get('min') is not None:
                        entry['min'] = inp['min']
                    if inp.get('max') is not None:
                        entry['max'] = inp['max']
                    if inp.get('step') is not None:
                        entry['step'] = inp['step']
                    if field_type == 'combo':
                        entry['options'] = inp['options']
                    field_mapping[safe_name] = f'{nid}.inputs.{inp_name}'
                    ui_fields.append(entry)
                widget_idx += 1
                continue

            # 非链接、非 widget 但有默认值的参数
            default = inp.get('default')
            if default is not None and inp_name not in ('model', 'vae', 'clip', 'image',
                    'pixels', 'samples', 'latent', 'latent_image', 'conditioning',
                    'control_net', 'positive', 'negative', 'samples_from',
                    'images', 'audio', 'video', 'mask', 'noise'):
                val = _get_input_value(inp, widgets_values, widget_idx)
                if val is None:
                    val = default
                if val is not None:
                    inputs[inp_name] = val
                    safe_name = FIELD_ALIASES.get(inp_name, inp_name)
                    if safe_name not in seen_ui_field_names and not _is_hidden_field_name(safe_name):
                        seen_ui_field_names.add(safe_name)
                        inp_type = _get_input_type(inp)
                        field_type = 'boolean' if inp_type == 'BOOLEAN' else ('number' if inp_type in ('INT', 'FLOAT') else 'string')
                        entry = {'name': safe_name, 'type': field_type, 'default': val}
                        if inp.get('min') is not None:
                            entry['min'] = inp['min']
                        if inp.get('max') is not None:
                            entry['max'] = inp['max']
                        if inp.get('step') is not None:
                            entry['step'] = inp['step']
                        if inp_type == 'COMBO' and isinstance(inp.get('options'), list):
                            entry['type'] = 'combo'
                            entry['options'] = inp['options']
                        field_mapping[safe_name] = f'{nid}.inputs.{inp_name}'
                        ui_fields.append(entry)

        # 只处理连接器节点链路（无 widget 的节点）
        if not inputs and ntype in CONNECTOR_TYPES:
            for inp in node_inputs:
                inp_name = inp['name']
                link = inp.get('link')
                if link is not None and link in link_map:
                    from_node, from_slot, _, _ = link_map[link]
                    inputs[inp_name] = [from_node, from_slot]

        # UUID 子图引用节点必须保留（ComfyUI 运行时解析），即使 inputs 为空
        # CONNECTOR_TYPES 节点（如 GetNode）也必须保留，因为其他节点通过 link 引用其输出
        if inputs or is_uuid_ref or ntype in CONNECTOR_TYPES:
            node_api[nid] = {'class_type': ntype, 'inputs': inputs}

    # 构建 SetNode → 源节点 映射表（用于解析 UUID 子图中的 GetNode 引用）
    # SetNode/GetNode 是 KJNodes 的前端虚拟连接系统：
    #   SetNode（具名锚点）← 源节点输出
    #   GetNode（同名查找）→ 下游节点，运行时透明代理到 SetNode 的输入值
    # 在 UUID 子图展开时，需将 GetNode 引用解析为实际源节点
    setnode_map: dict[str, tuple[str, int]] = {}
    for node in nodes:
        if node.get('type') == 'SetNode':
            wv = node.get('widgets_values', [])
            name = wv[0] if isinstance(wv, list) and wv else ''
            if not name:
                continue
            for inp in node.get('inputs', []):
                link_id = inp.get('link')
                if link_id is not None and link_id in link_map:
                    src_nid, src_slot, _, _ = link_map[link_id]
                    setnode_map[name] = (src_nid, src_slot)
                    break

    # UUID Group Node 保持折叠状态，在 build_prompt_graph 阶段展开
    return node_api, field_mapping, ui_fields, setnode_map


def _expand_uuid_wrappers(graph: dict[str, Any]) -> dict[str, Any]:
    """展开所有 UUID Group Node，将 _subgraph 内部节点提升到主图。

    调用时机：build_prompt_graph 中 _set_graph_value 之后、提交 ComfyUI 之前。
    用户参数已设置完毕，展开只做结构转换（-10/-20 解析 + ID 重映射）。
    """
    import copy as _copy
    graph = _copy.deepcopy(graph)

    # 提取全局 SetNode→源节点 映射（由 convert_native_to_api 在转换时构建）
    setnode_map: dict[str, tuple[str, int]] = {}
    for k, v in graph.pop('_setnode_map', {}).items():
        if isinstance(v, list) and len(v) == 2:
            setnode_map[k] = (str(v[0]), int(v[1]))

    # 记录所有已展开 wrapper 的输出映射，用于后处理修复顺序问题
    # {wrapper_nid: {output_slot: (internal_nid, internal_slot)}}
    _wrapper_out_maps: dict[str, dict[int, tuple[str, int]]] = {}

    # 收集 UUID 包装器（可能有嵌套，循环处理直到没有）
    while True:
        wrapper_nids = [
            nid for nid, nd in graph.items()
            if isinstance(nd.get('_subgraph'), dict)
        ]
        if not wrapper_nids:
            break

        for wrapper_nid in wrapper_nids:
            wrapper = graph.get(wrapper_nid)
            if not wrapper:
                continue
            sg = wrapper['_subgraph']
            sub_nodes = sg['nodes']
            raw_links = sg['raw_links']
            wrapper_input_defs = sg.get('wrapper_input_defs', [])

            # ---- 1. ID 重映射 ----
            id_remap = {str(in_nid): f'{wrapper_nid}__{in_nid}' for in_nid in sub_nodes}

            # ---- 2. 构建槽位映射 ----
            # wrapper 输入定义（按槽位顺序） → 外部链接或 None
            slot_to_external: dict[int, list | None] = {}
            for slot_idx, inp_def in enumerate(wrapper_input_defs):
                name = inp_def.get('name', '')
                ext_ref = wrapper.get('inputs', {}).get(name)
                if isinstance(ext_ref, list) and len(ext_ref) == 2 and not (len(ext_ref) == 2 and ext_ref[0] == '-10'):
                    slot_to_external[slot_idx] = ext_ref
                else:
                    slot_to_external[slot_idx] = None

            # ---- 从 raw_nodes 构建查找表 + 解析 GetNode 引用 ----
            raw_nodes_map = {str(n['id']): n for n in sg.get('raw_nodes', [])}
            # GetNode 解析：通过 SetNode 虚拟名称找到实际源节点
            getnode_resolved: dict[str, list] = {}
            for in_nid, raw_node in raw_nodes_map.items():
                if raw_node.get('type') == 'GetNode':
                    wv = raw_node.get('widgets_values', [])
                    set_name = wv[0] if isinstance(wv, list) and wv else ''
                    if set_name and set_name in setnode_map:
                        src_nid, src_slot = setnode_map[set_name]
                        getnode_resolved[str(in_nid)] = [str(src_nid), int(src_slot)]

            # ### 2b. 构建 -20 输出映射
            # output_map: {wrapper_output_slot: (internal_nid, internal_slot)}
            # getnode_output_map: {wrapper_output_slot: [resolved_src_nid, resolved_src_slot]}
            output_map: dict[int, tuple[str, int]] = {}
            getnode_output_map: dict[int, list] = {}
            for link in raw_links:
                if isinstance(link, dict) and link.get('target_id') == -20:
                    origin_id = str(link['origin_id'])
                    if origin_id in sub_nodes:
                        output_map[link['target_slot']] = (origin_id, link['origin_slot'])
                    elif origin_id in getnode_resolved:
                        # GetNode 输出 → 用 SetNode 源替换，绕过 GetNode
                        getnode_output_map[link['target_slot']] = getnode_resolved[origin_id]

            # 记录输出映射，供后处理修复顺序问题
            _wrapper_out_maps[wrapper_nid] = output_map.copy()

            # ---- 3. 构建 widget 默认值查找表 ----
            widget_defaults: dict[str, dict[str, Any]] = {}

            def _get_widget_default(raw_node: dict, input_name: str) -> Any | None:
                """从原始节点获取指定 widget 输入的默认值（含隐藏 widget 偏移）"""
                wv = raw_node.get('widgets_values', [])
                if not isinstance(wv, list):
                    return wv.get(input_name) if isinstance(wv, dict) else None
                # 构建完整 widget 顺序表（可见 + 已知隐藏）
                ntype = raw_node.get('type', '')
                visible = [inp['name'] for inp in raw_node.get('inputs', []) if 'widget' in inp]
                all_widgets = list(visible)
                if ntype in ('KSampler', 'KSamplerAdvanced'):
                    all_widgets.insert(1, 'control_after_generate')
                try:
                    idx = all_widgets.index(input_name)
                    if idx < len(wv):
                        return wv[idx]
                except ValueError:
                    pass
                return None

            for in_nid, raw_node in raw_nodes_map.items():
                defaults: dict[str, Any] = {}
                for inp in raw_node.get('inputs', []):
                    if 'widget' in inp:
                        val = _get_widget_default(raw_node, inp['name'])
                        if val is not None:
                            defaults[inp['name']] = val
                widget_defaults[in_nid] = defaults

            # ---- 4. 更新外部节点对 wrapper 输出的引用 ----
            for ext_nid, ext_node in graph.items():
                if ext_nid == wrapper_nid:
                    continue
                for inp_name, inp_val in list(ext_node.get('inputs', {}).items()):
                    if isinstance(inp_val, list) and len(inp_val) == 2 and inp_val[0] == wrapper_nid:
                        out_slot = inp_val[1]
                        if out_slot in output_map:
                            in_nid, in_slot = output_map[out_slot]
                            ext_node['inputs'][inp_name] = [id_remap[in_nid], in_slot]
                        elif out_slot in getnode_output_map:
                            # GetNode 的 -20 输出：用解析后的 SetNode 源替换
                            ext_node['inputs'][inp_name] = list(getnode_output_map[out_slot])

            # ---- 5. 处理内部节点：更新引用 + 解决 -10 ----
            promoted: dict[str, Any] = {}
            for in_nid, in_node in sub_nodes.items():
                new_id = id_remap[in_nid]
                new_node = _copy.deepcopy(in_node)

                for inp_name, inp_val in list(new_node.get('inputs', {}).items()):
                    if not isinstance(inp_val, list) or len(inp_val) != 2:
                        continue
                    ref_nid, ref_slot = str(inp_val[0]), inp_val[1]

                    if ref_nid == '-10':
                        ext_ref = slot_to_external.get(ref_slot)
                        if ext_ref is not None:
                            new_node['inputs'][inp_name] = [str(ext_ref[0]), ext_ref[1]] if isinstance(ext_ref, list) else ext_ref
                        else:
                            # 未链接 widget：_set_graph_value 可能已设置用户值
                            # 如果仍为 -10，使用原始默认值
                            defaults = widget_defaults.get(in_nid, {})
                            if inp_name in defaults:
                                new_node['inputs'][inp_name] = defaults[inp_name]
                            else:
                                # 无默认值可用，移除 -10 引用（ComfyUI 会使用节点自身默认）
                                del new_node['inputs'][inp_name]
                    elif ref_nid in id_remap:
                        new_node['inputs'][inp_name] = [id_remap[ref_nid], ref_slot]
                    elif ref_nid in getnode_resolved:
                        # GetNode 引用 → 用 SetNode 源替换
                        resolved_target = getnode_resolved[ref_nid]
                        new_node['inputs'][inp_name] = [str(resolved_target[0]), resolved_target[1]]

                promoted[new_id] = new_node

            # ---- 6. 提升内部节点，删除包装器 ----
            graph.update(promoted)
            del graph[wrapper_nid]

    # ---- 7. 后处理：修复因展开顺序导致的死引用 ----
    # 某些 GetNode 通过 setnode_map 解析为 wrapper ID（如 ["236", 2]），
    # 但该 wrapper 可能已被先展开并删除。通过 _wrapper_out_maps 二次解析。
    if _wrapper_out_maps:
        changed = True
        while changed:
            changed = False
            for node_data in graph.values():
                for inp_name, inp_val in list(node_data.get('inputs', {}).items()):
                    if not isinstance(inp_val, list) or len(inp_val) != 2:
                        continue
                    ref_nid = str(inp_val[0])
                    if ref_nid in _wrapper_out_maps:
                        out_map = _wrapper_out_maps[ref_nid]
                        ref_slot = inp_val[1]
                        if ref_slot in out_map:
                            in_nid, in_slot = out_map[ref_slot]
                            node_data['inputs'][inp_name] = [f'{ref_nid}__{in_nid}', in_slot]
                            changed = True

    return graph


def _convert_workflow_files(source_dir: Path, converted: int, force: bool = False) -> int:
    """扫描目录中的 JSON 工作流文件并转换（跳过未修改的，force=True 强制重新转换）"""
    if not source_dir.exists():
        return converted
    for fpath in sorted(source_dir.glob('*.json')):
        try:
            # 检查是否需要重新转换：输出文件是否存在且比源文件新
            workflow_id = re.sub(r'[^a-zA-Z0-9_]', '_', fpath.stem).lower()
            if not workflow_id:
                workflow_id = f'workflow_{converted}'
            api_path = WORKFLOWS_DIR / f'{workflow_id}.json'
            mapping_path = WORKFLOWS_DIR / f'{workflow_id}.mapping.json'
            if not force:
                src_mtime = fpath.stat().st_mtime
                if api_path.exists() and mapping_path.exists():
                    if api_path.stat().st_mtime >= src_mtime:
                        converted += 1
                        continue

            native = json.loads(fpath.read_text(encoding='utf-8'))
            if 'nodes' not in native:
                continue
            api_data, field_mapping, ui_fields, setnode_map = convert_native_to_api(native)
            if not api_data:
                continue
            # 存储 SetNode→源节点 映射，供 _expand_uuid_wrappers 解析 GetNode 引用
            api_data['_setnode_map'] = {k: list(v) for k, v in setnode_map.items()}
            api_path.write_text(json.dumps(api_data, indent=2, ensure_ascii=False), encoding='utf-8')
            name = native.get('extra', {}).get('workflow_name', fpath.stem)
            mapping = {
                'workflow_id': workflow_id,
                'name': name,
                'category': 'converted',
                'workflow_file': f'{workflow_id}.json',
                'mapping_file': f'{workflow_id}.mapping.json',
                'ui_schema': {'fields': ui_fields},
                'field_mapping': field_mapping,
            }
            mapping_path.write_text(json.dumps(mapping, indent=2, ensure_ascii=False), encoding='utf-8')
            print(f'OK {fpath.name} -> {workflow_id}')
            converted += 1
        except Exception as e:
            print(f'ERR {fpath.name}: {e}')
    return converted


def auto_convert_all(force: bool = False):
    converted = 0
    for src_dir in USER_WORKFLOW_DIRS:
        converted = _convert_workflow_files(src_dir, converted, force=force)
    print(f'Converted {converted} workflows')
    return converted


if __name__ == '__main__':
    auto_convert_all()
