from __future__ import annotations

import copy
import json
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from .convert_workflow import auto_convert_all

# 上传资产时建立的 blake3 哈希 → 文件名 映射表
# 前端提交 blake3 哈希但不会带 asset_hashes 映射，由后端在上传时记录
_asset_file_map: dict[str, str] = {}

def register_asset_file(asset_hash: str, filename: str) -> None:
    """注册 blake3 哈希到文件名的映射（上传资产时调用）"""
    if asset_hash and filename:
        _asset_file_map[asset_hash] = filename

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
        self.reload()

    def reload(self) -> None:
        auto_convert_all()
        self._definitions.clear()
        for mapping_file in sorted(self.workflows_dir.glob("*.mapping.json")):
            data = json.loads(mapping_file.read_text(encoding="utf-8"))
            workflow_id = data["workflow_id"]
            workflow_file = self.workflows_dir / data["workflow_file"]
            if not workflow_file.exists():
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
        if workflow_id not in self._definitions:
            raise KeyError(f"Unknown workflow: {workflow_id}")
        return self._definitions[workflow_id]

    def build_prompt_graph(
        self,
        workflow_id: str,
        params: dict[str, Any],
        asset_hashes: dict[str, str] | None = None,
    ) -> tuple[dict[str, Any], dict[str, Any] | None]:
        """加载工作流 JSON，设置用户参数，返回可直接提交到 ComfyUI 的 prompt graph。

        UUID Group Node 已在 convert_native_to_api 阶段展开，此处无需再处理。
        """
        definition = self.get(workflow_id)
        graph = json.loads(definition.workflow_file.read_text(encoding="utf-8"))
        graph = copy.deepcopy(graph)

        # 构建字段类型查找表，用于类型转换
        field_types: dict[str, str] = {}
        for f in definition.ui_schema.get("fields", []):
            field_types[f["name"]] = f.get("type", "string")

        merged_params = dict(params)
        if asset_hashes:
            merged_params.update(asset_hashes)

        for ui_field, target in definition.field_mapping.items():
            if ui_field not in merged_params or merged_params.get(ui_field) in (None, "", [], {}):
                continue
            value = merged_params[ui_field]
            # 解析 blake3 哈希为实际文件名（LoadImage 等节点需要真实文件路径）
            if isinstance(value, str) and value.startswith("blake3:"):
                # 优先从请求中的 asset_hashes 查，次选从上传时记录的后备映射查
                resolved = (asset_hashes or {}).get(value) or resolve_asset_hash(value)
                if resolved:
                    value = resolved
                else:
                    # 无法解析哈希，跳过此字段（保留工作流中的默认值）
                    logging.warning(f"无法解析 blake3 哈希 {value[:50]}...（字段 {ui_field}），保留默认值")
                    continue
            # 根据 ui_schema 类型转换参数值，确保 ComfyUI 验证通过
            value = self._coerce_param_type(value, field_types.get(ui_field, "string"))
            self._set_graph_value(graph, target, value)

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
                # 中间节点：进入子图继续遍历（兼容旧格式）
                current_graph = node_data['_subgraph']
            else:
                raise KeyError(
                    f"Node {nid} has no subgraph, cannot traverse to {'.'.join(node_path[i+1:])}"
                )
