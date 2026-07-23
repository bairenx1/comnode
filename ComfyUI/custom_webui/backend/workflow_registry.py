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

        # 展开 UUID Group Node，将 _subgraph 内部节点提升到主图
        graph = _expand_uuid_wrappers(graph)

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
                        return value
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
