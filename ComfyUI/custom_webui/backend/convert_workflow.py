import sys, json, re
from pathlib import Path

WORKFLOWS_DIR = Path(__file__).resolve().parent.parent / "workflows"
USER_WORKFLOWS_DIR = Path(__file__).resolve().parent.parent.parent / "user" / "default" / "workflows"

SKIP_TYPES = {'MarkdownNote', 'Note', 'PrimitiveNode', 'Reroute'}

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
    """解析链接关系，构建正向和反向映射"""
    link_map = {}         # link_id -> (from_node, from_slot, to_node, to_slot)
    reverse_map = {}      # (to_node_id, input_name) -> [(from_node_id, from_slot)]

    for link in links:
        link_id = link[0]
        from_node = str(link[1])
        from_slot = link[2]
        to_node = str(link[3])
        to_slot = link[4]
        link_map[link_id] = (from_node, from_slot, to_node, to_slot)

    # 构建反向映射：找到每个目标节点输入端对应的源节点
    for link in links:
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


def _trace_clip_polarity(nodes, reverse_map):
    """通过链接追踪 CLIPTextEncode 节点是正向还是负向提示词

    遍历所有 KSampler 节点，找到其 positive/negative 输入连接到的 CLIPTextEncode
    """
    clip_polarity = {}  # clip_node_id -> 'prompt' | 'negative_prompt'

    for node in nodes:
        nid = str(node['id'])
        ntype = node.get('type', '')

        if ntype not in ('KSampler', 'KSamplerAdvanced', 'SamplerCustom', 'SamplerCustomAdvanced'):
            continue

        # 正向提示词
        for input_name in ('positive', 'positive_cond', 'positive_conditioning'):
            pos_key = (nid, input_name)
            if pos_key in reverse_map:
                for from_node_id, _ in reverse_map[pos_key]:
                    for n2 in nodes:
                        if (str(n2['id']) == from_node_id and
                                'CLIPTextEncode' in n2.get('type', '')):
                            clip_polarity[from_node_id] = 'prompt'
                            break

        # 负向提示词
        for input_name in ('negative', 'negative_cond', 'negative_conditioning'):
            neg_key = (nid, input_name)
            if neg_key in reverse_map:
                for from_node_id, _ in reverse_map[neg_key]:
                    for n2 in nodes:
                        if (str(n2['id']) == from_node_id and
                                'CLIPTextEncode' in n2.get('type', '')):
                            clip_polarity[from_node_id] = 'negative_prompt'
                            break

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

    # 查找下游节点类型
    for to_node, to_slot in downstream_nodes:
        for n in nodes:
            if str(n['id']) == to_node:
                ntype = n.get('type', '')
                # 连接 VAEEncode → 进入采样流程 → 主输入图
                if 'VAEEncode' in ntype:
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


def _get_input_value(inp, widgets_values, widget_idx):
    """从 widgets_values 中按索引或按名称获取输入值"""
    val = None
    if widget_idx < len(widgets_values):
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


def convert_native_to_api(native_data):
    nodes = native_data.get('nodes', [])
    links = native_data.get('links', [])

    link_map, reverse_map = _build_link_maps(nodes, links)
    clip_polarity = _trace_clip_polarity(nodes, reverse_map)

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

        # 跳过 UUID 类型的 Group Node 包装器（其内部子节点已在图中独立存在）
        if UUID_TYPE_RE.match(ntype):
            continue

        widgets_values = node.get('widgets_values', [])
        node_inputs = node.get('inputs', [])
        inputs = {}

        # ---------- 处理子图 / 嵌套工作流 ----------
        subgraph_data = node.get('subgraph') or node.get('workflow') or node.get('data')
        if subgraph_data and isinstance(subgraph_data, dict):
            sub_nodes = subgraph_data.get('nodes')
            if sub_nodes:
                sub_api, sub_mapping, sub_fields = convert_native_to_api(
                    {'nodes': sub_nodes, 'links': subgraph_data.get('links', [])}
                )
                for fname, target in sub_mapping.items():
                    full_target = f'{nid}.{target}'
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

                    # 查找 text 值
                    text_val = None
                    for wi, wv in enumerate(widgets_values):
                        if wi < len(node_inputs) and node_inputs[wi].get('name') == 'text':
                            text_val = wv
                            break
                    if text_val is None:
                        text_val = inp.get('default', '')

                    inputs[inp_name] = text_val
                    fname = 'negative_prompt' if is_neg else 'prompt'
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
                            if safe_name not in seen_ui_field_names:
                                seen_ui_field_names.add(safe_name)
                                inp_type = inp.get('type', 'STRING')
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
        widget_idx = 0
        for inp in node_inputs:
            inp_name = inp['name']
            link = inp.get('link')
            if link is not None and link in link_map:
                from_node, from_slot, _, _ = link_map[link]
                inputs[inp_name] = [from_node, from_slot]
                widget_idx += 1
                continue

            if _is_widget_input(inp):
                val = _get_input_value(inp, widgets_values, widget_idx)
                if val is not None:
                    inputs[inp_name] = val
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
                    if safe_name not in seen_ui_field_names:
                        seen_ui_field_names.add(safe_name)
                        inp_type = inp.get('type', 'STRING').upper()
                        field_type = 'number' if inp_type in ('INT', 'FLOAT') else 'string'
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
            widget_idx += 1

        # 只处理连接器节点链路（无 widget 的节点）
        if not inputs and ntype in CONNECTOR_TYPES:
            for inp in node_inputs:
                inp_name = inp['name']
                link = inp.get('link')
                if link is not None and link in link_map:
                    from_node, from_slot, _, _ = link_map[link]
                    inputs[inp_name] = [from_node, from_slot]

        if inputs:
            node_api[nid] = {'class_type': ntype, 'inputs': inputs}

    return node_api, field_mapping, ui_fields


def auto_convert_all():
    converted = 0
    for fpath in sorted(USER_WORKFLOWS_DIR.glob('*.json')):
        try:
            native = json.loads(fpath.read_text(encoding='utf-8'))
            if 'nodes' not in native:
                continue
            api_data, field_mapping, ui_fields = convert_native_to_api(native)
            if not api_data:
                print(f'SKIP {fpath.name}: no convertible nodes')
                continue
            workflow_id = re.sub(r'[^a-zA-Z0-9_]', '_', fpath.stem).lower()
            if not workflow_id:
                workflow_id = f'workflow_{converted}'
            api_path = WORKFLOWS_DIR / f'{workflow_id}.json'
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
            mapping_path = WORKFLOWS_DIR / f'{workflow_id}.mapping.json'
            mapping_path.write_text(json.dumps(mapping, indent=2, ensure_ascii=False), encoding='utf-8')
            print(f'OK {fpath.name} -> {workflow_id}')
            converted += 1
        except Exception as e:
            print(f'ERR {fpath.name}: {e}')
    print(f'Converted {converted} workflows')
    return converted


if __name__ == '__main__':
    auto_convert_all()
