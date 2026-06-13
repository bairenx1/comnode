from __future__ import annotations

import copy
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from .convert_workflow import auto_convert_all

# UUID class_type 表示 ComfyUI Group Node，必须过滤掉
_UUID_TYPE_RE = re.compile(
    r'^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$',
    re.IGNORECASE,
)


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
    ) -> dict[str, Any]:
        definition = self.get(workflow_id)
        graph = json.loads(definition.workflow_file.read_text(encoding="utf-8"))
        graph = copy.deepcopy(graph)

        # 安全过滤：移除 UUID 类型的 Group Node 包装器（convert 阶段理论上已过滤，此处做兜底）
        uuids_to_remove = [nid for nid, nd in graph.items()
                           if isinstance(nd, dict) and _UUID_TYPE_RE.match(nd.get('class_type', ''))]
        for nid in uuids_to_remove:
            del graph[nid]

        merged_params = dict(params)
        if asset_hashes:
            merged_params.update(asset_hashes)

        for ui_field, target in definition.field_mapping.items():
            if ui_field not in merged_params or merged_params.get(ui_field) in (None, "", [], {}):
                continue
            self._set_graph_value(graph, target, merged_params[ui_field])
        return graph

    @staticmethod
    def _set_graph_value(graph: dict[str, Any], target: str, value: Any) -> None:
        # target 格式:
        #   "nodeId.inputs.key"              — 直接节点输入
        #   "parentId.childId.inputs.key"    — 嵌套子图（UUID wrapper → 内部节点）
        parts = target.split(".")
        try:
            inputs_idx = parts.index("inputs")
        except ValueError:
            raise ValueError(f"Unsupported mapping target: {target}")
        if inputs_idx < 1:
            raise ValueError(f"Unsupported mapping target: {target}")

        node_path = parts[:inputs_idx]   # e.g. ["320", "313"] 或 ["584"]
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
                current_graph = node_data['_subgraph']
            else:
                raise KeyError(
                    f"Node {nid} has no subgraph, cannot traverse to {'.'.join(node_path[i+1:])}"
                )
