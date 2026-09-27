from __future__ import annotations

import copy
import json
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from .convert_workflow import auto_convert_all, _expand_uuid_wrappers

_asset_file_map: dict[str, str] = {}
_map_file_path: Path | None = None

def init_asset_file_map(workflows_dir: Path) -> None:
    """初始化并加载持久化的资产哈希文件映射表"""
    global _map_file_path
    _map_file_path = workflows_dir / ".asset_file_map.json"
    if _map_file_path.exists():
        try:
            data = json.loads(_map_file_path.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                _asset_file_map.update(data)
        except Exception as e:
            logging.warning(f"Failed to load asset file map: {e}")

def register_asset_file(asset_hash: str, filename: str) -> None:
    """注册 blake3 哈希到文件名的映射（上传资产时调用）"""
    if asset_hash and filename:
        _asset_file_map[asset_hash] = filename
        if _map_file_path:
            try:
                _map_file_path.write_text(json.dumps(_asset_file_map, indent=2, ensure_ascii=False), encoding="utf-8")
            except Exception as e:
                logging.warning(f"Failed to save asset file map: {e}")

def resolve_asset_hash(asset_hash: str) -> str | None:
    """根据 blake3 哈希查找对应的文件名"""
    return _asset_file_map.get(asset_hash)


@dataclass
class WorkflowDefinition:
    workflow_id: str
    name: str
    category: str
    workflow_file: Path
    mapping_file: Path
    ui_schema: dict[str, Any]
    field_mapping: dict[str, str]


class WorkflowRegistry:
    def __init__(self, workflows_dir: Path) -> None:
        self.workflows_dir = workflows_dir
        self._definitions: dict[str, WorkflowDefinition] = {}
        init_asset_file_map(workflows_dir)
        self.reload()

    def reload(self) -> None:
        auto_convert_all()
        self._definitions.clear()
        for mapping_file in sorted(self.workflows_dir.glob("*.mapping.json")):
            data = json.loads(mapping_file.read_text(encoding="utf-8"))
            workflow_id = data["workflow_id"]
            workflow_file = self.workflows_dir / data["workflow_file"]
            if not workflow_file.exists():
                logging.warning(f"工作流 JSON 文件缺失，跳过: {workflow_file.name} (mapping: {mapping_file.name})")
                continue
            self._definitions[workflow_id] = WorkflowDefinition(
                workflow_id=workflow_id,
                name=data.get("name", workflow_id),
                category=data.get("category", "other"),
                workflow_file=workflow_file,
                mapping_file=mapping_file,
                ui_schema=data.get("ui_schema", {}),
                field_mapping=data.get("field_mapping", {}),
            )
        ids = sorted(self._definitions.keys())
        logging.info(f"已加载 {len(self._definitions)} 个工作流:")
        for wid in ids:
            logging.info(f"  - {wid}")

    def list_workflows(self) -> list[dict[str, Any]]:
        return [
            {
                "workflow_id": x.workflow_id,
                "name": x.name,
                "category": x.category,
                "ui_schema": x.ui_schema,
                "workflow_file": x.workflow_file.name,
                "mapping_file": x.mapping_file.name,
            }
            for x in sorted(self._definitions.values(), key=lambda w: w.workflow_id)
        ]

    def get(self, workflow_id: str) -> WorkflowDefinition:
        if workflow_id in self._definitions:
            return self._definitions[workflow_id]
        # 模糊匹配：规范化后比较（去空格、统一分隔符等）
        normalized_req = workflow_id.strip().replace(' ', '_').replace('-', '_')
        candidates = []
        for wid in self._definitions:
            normalized_wid = wid.strip().replace(' ', '_').replace('-', '_')
            if normalized_wid == normalized_req or normalized_wid in normalized_req or normalized_req in normalized_wid:
                candidates.append(wid)
        if len(candidates) == 1:
            logging.info(f"模糊匹配工作流: '{workflow_id}' → '{candidates[0]}'")
            return self._definitions[candidates[0]]
        hint = ""
        if candidates:
            hint = f"，是否想用: {', '.join(candidates[:3])}"
        all_ids = sorted(self._definitions.keys())
        raise KeyError(f"Unknown workflow: '{workflow_id}'{hint}。可用工作流({len(all_ids)}): {json.dumps(all_ids, ensure_ascii=False)}")

    def build_prompt_graph(
        self,
        workflow_id: str,
        params: dict[str, Any],
        asset_hashes: dict[str, str] | None = None,
    ) -> tuple[dict[str, Any], dict[str, Any] | None]:
        """加载工作流 JSON，设置用户参数，展开 UUID 折叠节点后返回 prompt graph。"""
        definition = self.get(workflow_id)
        graph = json.loads(definition.workflow_file.read_text(encoding="utf-8"))
        graph = copy.deepcopy(graph)

        # 构建字段类型查找表 + 默认值查找表
        field_types: dict[str, str] = {}
        field_defaults: dict[str, Any] = {}
        for f in definition.ui_schema.get("fields", []):
            field_types[f["name"]] = f.get("type", "string")
            if "default" in f:
                field_defaults[f["name"]] = f["default"]

        merged_params = dict(params)
        if asset_hashes:
            merged_params.update(asset_hashes)

        # 种子别名互通：确保前端批量传递的 seed 能自动同步给 noise_seed（以及反向）
        if "seed" in merged_params and merged_params["seed"] is not None:
            merged_params["noise_seed"] = merged_params["seed"]
        elif "noise_seed" in merged_params and merged_params["noise_seed"] is not None:
            merged_params["seed"] = merged_params["noise_seed"]

        for ui_field, target in definition.field_mapping.items():
            # 只有当 merged_params 中根本没有提供这个参数时，才使用 ui_schema 默认值（确保 -10 widget ref 被解析）
            if ui_field not in merged_params:
                value = field_defaults.get(ui_field)
            else:
                value = merged_params[ui_field]

            if value is None:
                continue

            # 解析 blake3 哈希为实际文件名（LoadImage 等节点需要真实文件路径）
            if isinstance(value, str) and value.startswith("blake3:"):
                resolved = (asset_hashes or {}).get(value) or resolve_asset_hash(value)
                if resolved:
                    value = resolved
                else:
                    logging.warning(f"无法解析 blake3 哈希 {value[:50]}...（字段 {ui_field}），保留默认值")
                    continue
            elif isinstance(value, str):
                resolved = (asset_hashes or {}).get(value) or resolve_asset_hash(value)
                if resolved:
                    value = resolved
            # 根据 ui_schema 类型转换参数值，确保 ComfyUI 验证通过
            value = self._coerce_param_type(value, field_types.get(ui_field, "string"))
            try:
                self._set_graph_value(graph, target, value)
            except KeyError as e:
                logging.warning(f"跳过字段 '{ui_field}' (target={target}): {e}")

        # 确保图里所有 RandomNoise 节点的 noise_seed 保持与传入的有效种子同步
        effective_seed = merged_params.get("noise_seed")
        if effective_seed is not None:
            try:
                seed_int = int(effective_seed)
                for nid, node_data in graph.items():
                    if isinstance(node_data, dict) and node_data.get("class_type") == "RandomNoise":
                        if "inputs" in node_data and "noise_seed" in node_data["inputs"]:
                            node_data["inputs"]["noise_seed"] = seed_int
            except (ValueError, TypeError):
                pass

        # 遍历图节点做针对性参数清洗和容错，防止非法参数破坏 ComfyUI 校验
        for nid, node_data in graph.items():
            if not isinstance(node_data, dict):
                continue
            inputs = node_data.get("inputs")
            if not isinstance(inputs, dict):
                continue
            ctype = str(node_data.get("class_type", ""))

            # 针对 TextGenerate / TextGenerateLTX2Prompt 等文本生成节点
            if "TextGenerate" in ctype:
                # 1. max_length 必须是合法正整数，彻底防范被误传为 "on" 等字符串
                ml = inputs.get("max_length")
                if ml is not None:
                    try:
                        inputs["max_length"] = int(ml) if str(ml).strip().isdigit() else 256
                    except (ValueError, TypeError):
                        inputs["max_length"] = 256
                else:
                    inputs["max_length"] = 256

                # 2. mtp 必须显式存在且在合法列表中，如缺失、为空或非法强制赋值为 "auto"
                mtp_val = str(inputs.get("mtp") or "auto").strip()
                if mtp_val not in ("auto", "off", "2", "3", "4", "5"):
                    mtp_val = "auto"
                inputs["mtp"] = mtp_val

                # 3. sampling_mode 若非法修正为 on
                if inputs.get("sampling_mode") not in ("on", "off"):
                    inputs["sampling_mode"] = "on"

                # 4. sampling_mode.* 采样参数边界保护与防错位自愈（防止 400 validation error）
                raw_temp = inputs.get("sampling_mode.temperature")
                raw_topk = inputs.get("sampling_mode.top_k")
                raw_minp = inputs.get("sampling_mode.min_p")
                raw_rep = inputs.get("sampling_mode.repetition_penalty")

                try:
                    t_val = float(raw_temp) if raw_temp is not None else 0.7
                except (ValueError, TypeError):
                    t_val = 0.7

                try:
                    mp_val = float(raw_minp) if raw_minp is not None else 0.05
                except (ValueError, TypeError):
                    mp_val = 0.05

                # 若发生错位（例如 temp > 2.0，如被误填为 64.0），安全纠偏
                if t_val > 2.0:
                    logging.warning(f"检测到 sampling_mode.temperature={t_val} 超过上限 2.0 (参数错位或误设)，自动纠正为 0.7")
                    inputs["sampling_mode.temperature"] = 0.7
                    if raw_topk is None or (isinstance(raw_topk, (int, float)) and raw_topk < 1.0):
                        inputs["sampling_mode.top_k"] = int(t_val)
                else:
                    inputs["sampling_mode.temperature"] = max(0.01, min(2.0, t_val))

                if mp_val > 1.0:
                    logging.warning(f"检测到 sampling_mode.min_p={mp_val} 超过上限 1.0 (参数错位或误设)，自动纠正为 0.05")
                    inputs["sampling_mode.min_p"] = 0.05
                    if raw_rep is None or raw_rep == 0:
                        inputs["sampling_mode.repetition_penalty"] = mp_val
                else:
                    inputs["sampling_mode.min_p"] = max(0.0, min(1.0, mp_val))

                # top_k 限制在 [0, 1000]
                try:
                    tk_val = int(float(inputs.get("sampling_mode.top_k", 64)))
                    inputs["sampling_mode.top_k"] = max(0, min(1000, tk_val))
                except (ValueError, TypeError):
                    inputs["sampling_mode.top_k"] = 64

                # top_p 限制在 [0.0, 1.0]
                try:
                    tp_val = float(inputs.get("sampling_mode.top_p", 0.95))
                    inputs["sampling_mode.top_p"] = max(0.0, min(1.0, tp_val))
                except (ValueError, TypeError):
                    inputs["sampling_mode.top_p"] = 0.95

                # repetition_penalty 限制在 [0.0, 5.0]
                try:
                    rp_val = float(inputs.get("sampling_mode.repetition_penalty", 1.05))
                    inputs["sampling_mode.repetition_penalty"] = max(0.0, min(5.0, rp_val))
                except (ValueError, TypeError):
                    inputs["sampling_mode.repetition_penalty"] = 1.05

                # presence_penalty 限制在 [0.0, 5.0]
                if "sampling_mode.presence_penalty" in inputs:
                    try:
                        pp_val = float(inputs.get("sampling_mode.presence_penalty", 0.0))
                        inputs["sampling_mode.presence_penalty"] = max(0.0, min(5.0, pp_val))
                    except (ValueError, TypeError):
                        inputs["sampling_mode.presence_penalty"] = 0.0

                # seed
                if "sampling_mode.seed" in inputs:
                    try:
                        inputs["sampling_mode.seed"] = int(inputs["sampling_mode.seed"])
                    except (ValueError, TypeError):
                        inputs["sampling_mode.seed"] = 0

            # 通用保护：任意节点的 max_length 必须为 int，不能为 "on" 等字符串
            if "max_length" in inputs and not isinstance(inputs["max_length"], int):
                try:
                    inputs["max_length"] = int(inputs["max_length"]) if str(inputs["max_length"]).strip().isdigit() else 256
                except (ValueError, TypeError):
                    inputs["max_length"] = 256

            # 通用保护：任意节点的 mtp 若为空字符串，修正为 auto
            if "mtp" in inputs and str(inputs["mtp"]).strip() == "":
                inputs["mtp"] = "auto"

        # LTX-Video 帧数规范化：LTXV 要求帧数必须满足 8k+1 规律 (如 17, 25, 33, 41, 49, 121 等)
        # 前端默认偶数帧 (如 16) 若直接传入会破坏潜空间重构导致崩溃，在此自动就近纠正
        has_ltxv = any("LTXV" in str(nd.get("class_type", "")) for nd in graph.values() if isinstance(nd, dict))
        if has_ltxv:
            for nid, node_data in graph.items():
                if isinstance(node_data, dict):
                    inp = node_data.get("inputs")
                    if isinstance(inp, dict):
                        for k in ("value", "length", "frame_count", "frames_number"):
                            if k in inp and isinstance(inp[k], int) and inp[k] > 0 and (inp[k] - 1) % 8 != 0:
                                k_val = round((inp[k] - 1) / 8)
                                inp[k] = max(9, k_val * 8 + 1)

        # 展开 UUID Group Node，将 _subgraph 内部节点提升到主图
        graph = _expand_uuid_wrappers(graph)

        # 展开后保护：检查实际模型是否存在并对设备做自适应降级，保证本地与远端（如 Mac）环境各取所需
        try:
            import folder_paths
            avail_diffusion = set(folder_paths.get_filename_list("diffusion_models") or [])
            avail_clip = set(folder_paths.get_filename_list("text_encoders") or folder_paths.get_filename_list("clip") or [])
            avail_vae = set(folder_paths.get_filename_list("vae") or [])
        except Exception:
            avail_diffusion = set()
            avail_clip = set()
            avail_vae = set()

        try:
            import torch
            has_cuda = torch.cuda.is_available()
        except Exception:
            has_cuda = False

        import re
        def _smart_match(req: str, candidates: set[str]) -> str:
            if not req or not candidates or req in candidates:
                return req  # 当前环境（如远端 Mac）实际存在该模型时，坚决保留原配置，不作任何修改！
            # 若当前环境缺失该模型，提取核心家族名（剥离 .safetensors 及 _bf16/_int8/_fp8/_w4a8 等后缀）
            stem = re.sub(r"\.(safetensors|gguf|pt|bin|ckpt)$", "", req, flags=re.I)
            core = re.sub(r"(_bf16|_fp16|_fp8.*|_int8.*|_w4a8.*|_int4.*|_quant.*)$", "", stem, flags=re.I)
            matched = [m for m in candidates if core.lower() in m.lower()]
            return matched[0] if matched else req

        for nid, node_data in graph.items():
            if not isinstance(node_data, dict):
                continue
            inputs = node_data.get("inputs")
            if not isinstance(inputs, dict):
                continue
            ctype = str(node_data.get("class_type", ""))

            # 设备容错：在非 CUDA 环境（如远端 Mac MPS / CPU），强制将 device="gpu" 回退为 "auto"
            if not has_cuda and inputs.get("device") == "gpu":
                inputs["device"] = "auto"

            # UNET 模型智能自适应（有原版用原版，缺失才动态替换为现有版本）
            if ctype in ("UNETLoader",) or "unet_name" in inputs:
                req_unet = inputs.get("unet_name")
                if isinstance(req_unet, str) and avail_diffusion:
                    target_unet = _smart_match(req_unet, avail_diffusion)
                    if target_unet != req_unet:
                        logging.warning(
                            f"当前环境未找到 '{req_unet}'，自动切换为本地已有模型 '{target_unet}'"
                        )
                        inputs["unet_name"] = target_unet
                        if "weight_dtype" in inputs and inputs["weight_dtype"] != "default":
                            inputs["weight_dtype"] = "default"

            # Text Encoder (CLIP) 智能自适应
            if "clip_name" in inputs and isinstance(inputs.get("clip_name"), str) and avail_clip:
                req_clip = inputs["clip_name"]
                target_clip = _smart_match(req_clip, avail_clip)
                if target_clip != req_clip:
                    logging.warning(f"当前环境未找到 '{req_clip}'，自动切换为本地已有模型 '{target_clip}'")
                    inputs["clip_name"] = target_clip

            # VAE 模型智能自适应
            if "vae_name" in inputs and isinstance(inputs.get("vae_name"), str) and avail_vae:
                req_vae = inputs["vae_name"]
                target_vae = _smart_match(req_vae, avail_vae)
                if target_vae != req_vae:
                    logging.warning(f"当前环境未找到 '{req_vae}'，自动切换为本地已有模型 '{target_vae}'")
                    inputs["vae_name"] = target_vae

        return graph, None

    @staticmethod
    def _coerce_param_type(value: Any, field_type: str) -> Any:
        """将参数值转换为 ui_schema 声明的类型，避免 ComfyUI 验证类型不匹配。"""
        if value is None:
            return value
        if field_type == "number":
            if isinstance(value, str):
                try:
                    return int(value)
                except ValueError:
                    try:
                        return float(value)
                    except ValueError:
                        logging.warning(f"无法将值 {repr(value)} 转换为 number，将被丢弃以避免校验失败")
                        return None
            return value
        if field_type == "boolean":
            if isinstance(value, str):
                return value.lower() in ("true", "1", "yes", "on")
            return bool(value)
        return value  # string / combo 保持原样

    @staticmethod
    def _set_graph_value(graph: dict[str, Any], target: str, value: Any) -> None:
        # target 格式:
        #   "nodeId.inputs.key"              — 直接节点输入
        #   "parentId.childId.inputs.key"    — 嵌套子图（旧格式，UUID 已展开后不再出现）
        parts = target.split(".")
        try:
            inputs_idx = parts.index("inputs")
        except ValueError:
            raise ValueError(f"Unsupported mapping target: {target}")
        if inputs_idx < 1:
            raise ValueError(f"Unsupported mapping target: {target}")

        node_path = parts[:inputs_idx]   # e.g. ["466__456"] 或旧格式 ["466", "456"]
        key = ".".join(parts[inputs_idx + 1:])

        # 沿着节点路径逐层进入子图
        current_graph = graph
        for i, nid in enumerate(node_path):
            if nid not in current_graph:
                raise KeyError(f"Node not found in workflow: {nid} (target: {target})")
            node_data = current_graph[nid]
            is_last = (i == len(node_path) - 1)

            if is_last:
                # 路径终点：在此节点设置输入值
                node_data["inputs"][key] = value
            elif '_subgraph' in node_data:
                # 中间节点：进入子图继续遍历
                sg = node_data['_subgraph']
                # 兼容新旧格式：新格式 {'nodes': {...}, ...}，旧格式直接是节点 dict
                current_graph = sg['nodes'] if isinstance(sg, dict) and 'nodes' in sg else sg
            else:
                raise KeyError(
                    f"Node {nid} has no subgraph, cannot traverse to {'.'.join(node_path[i+1:])}"
                )
