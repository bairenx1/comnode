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
        definition = self.get(workflow_id)
        graph = json.loads(definition.workflow_file.read_text(encoding="utf-8"))
        graph = copy.deepcopy(graph)

        merged_params = dict(params)
        if asset_hashes:
            merged_params.update(asset_hashes)

        # 先通过 _subgraph 遍历设置参数值
        for ui_field, target in definition.field_mapping.items():
            if ui_field not in merged_params or merged_params.get(ui_field) in (None, "", [], {}):
                continue
            self._set_graph_value(graph, target, merged_params[ui_field])

        # 展开 UUID Group Node 包装器，将其内部节点提升到主图
        self._inline_uuid_wrappers(graph)

        # 再提取 ComfyUI 原生定义并清理内部字段
        comfy_defs: dict[str, dict[str, Any]] = {}
        for nid, nd in list(graph.items()):
            if isinstance(nd, dict) and '_comfy_def' in nd:
                comfy_defs[nd['class_type']] = nd.pop('_comfy_def')
            if isinstance(nd, dict) and '_subgraph' in nd:
                del nd['_subgraph']

        extra_data = None
        if comfy_defs:
            extra_data = {
                "extra_pnginfo": {
                    "workflow": {
                        "definitions": {
                            "subgraphs": comfy_defs,
                        },
                    }
                }
            }
        return graph, extra_data

    @staticmethod
    def _inline_uuid_wrappers(graph: dict[str, Any]) -> None:
        """展开所有 UUID Group Node 包装器，将其 _subgraph 中的内部节点提升到主图

        处理三项关键逻辑：
        1. 为内部节点 ID 添加前缀避免冲突
        2. 解析 -10 引用（子图外部输入 → 主图外部连接）
        3. 解析 -20 引用（子图外部输出 → 重路由外部消费者）
        """
        wrapper_ids = [
            nid for nid, nd in graph.items()
            if isinstance(nd, dict) and _UUID_TYPE_RE.match(nd.get('class_type', ''))
            and '_subgraph' in nd
        ]
        if not wrapper_ids:
            return

        for wrapper_id in wrapper_ids:
            wrapper = graph[wrapper_id]
            subgraph = wrapper.get('_subgraph', {})
            comfy_def = wrapper.get('_comfy_def', {})
            wrapper_inputs = wrapper.get('inputs', {})
            wrapper_input_names = comfy_def.get('wrapper_input_names', [])

            # 构建 slot → 外部连接 映射
            slot_to_external: dict[int, list] = {}
            for slot_idx, name in enumerate(wrapper_input_names):
                if name in wrapper_inputs:
                    slot_to_external[slot_idx] = wrapper_inputs[name]

            # 构建 ID 重映射表
            prefix = f'{wrapper_id}__'
            id_remap: dict[str, str] = {}
            for old_id in subgraph:
                id_remap[str(old_id)] = f'{prefix}{old_id}'

            # 构建内部节点默认值映射（从 _comfy_def.nodes 提取 widget 默认值）
            # 当 -10 引用无法从外部解析时，使用此默认值作为回退
            node_defaults: dict[str, dict[str, Any]] = {}
            for native_node in comfy_def.get('nodes', []):
                nn_id = str(native_node.get('id', ''))
                if not nn_id:
                    continue
                node_defaults[nn_id] = {}
                widgets_values = native_node.get('widgets_values', [])
                widget_idx = 0
                for inp in native_node.get('inputs', []):
                    if inp.get('widget'):
                        val = None
                        if isinstance(widgets_values, list) and widget_idx < len(widgets_values):
                            val = widgets_values[widget_idx]
                        elif isinstance(widgets_values, dict):
                            val = widgets_values.get(inp.get('name'))
                        if val is not None:
                            node_defaults[nn_id][inp['name']] = val
                        widget_idx += 1

            # 解析 -20 引用：哪个内部节点的哪个输出连接到包装器外部输出
            minus20_outputs: dict[int, tuple[str, int]] = {}
            for link in comfy_def.get('links', []):
                if isinstance(link, dict):
                    origin_id = str(link.get('origin_id', ''))
                    target_id = str(link.get('target_id', ''))
                    if target_id == '-20':
                        minus20_outputs[link['target_slot']] = (origin_id, link['origin_slot'])
                elif isinstance(link, list) and len(link) >= 5:
                    if str(link[3]) == '-20':
                        minus20_outputs[link[4]] = (str(link[1]), link[2])

            # 复制内部节点到主图，解析 -10 引用并重映射内部引用
            for old_id, node_data in subgraph.items():
                new_id = id_remap[str(old_id)]
                new_node = copy.deepcopy(node_data)

                for inp_key, inp_val in list(new_node.get('inputs', {}).items()):
                    # 解析 -10 引用：替换为外部连接或内部默认值
                    if isinstance(inp_val, list) and len(inp_val) == 2 and inp_val[0] == '-10':
                        slot = inp_val[1]
                        if slot in slot_to_external:
                            new_node['inputs'][inp_key] = list(slot_to_external[slot])
                        else:
                            defaults = node_defaults.get(str(old_id), {})
                            if inp_key in defaults:
                                new_node['inputs'][inp_key] = defaults[inp_key]
                            else:
                                new_node['inputs'][inp_key] = None
                    # 重映射内部节点引用
                    elif isinstance(inp_val, list) and len(inp_val) == 2 and isinstance(inp_val[0], str):
                        if inp_val[0] in id_remap:
                            new_node['inputs'][inp_key] = [id_remap[inp_val[0]], inp_val[1]]

                graph[new_id] = new_node

            # 重路由外部消费者：将指向包装器输出的连接改为指向内部输出节点
            processed_ids = set(id_remap.values()) | set(wrapper_ids)
            for wrapper_slot, (internal_id, internal_slot) in minus20_outputs.items():
                internal_new_id = id_remap.get(internal_id)
                if not internal_new_id:
                    continue
                for nid, nd in graph.items():
                    if nid in processed_ids:
                        continue
                    for inp_key, inp_val in nd.get('inputs', {}).items():
                        if (isinstance(inp_val, list) and len(inp_val) == 2
                                and inp_val[0] == wrapper_id and inp_val[1] == wrapper_slot):
                            nd['inputs'][inp_key] = [internal_new_id, internal_slot]

            # 删除 UUID 包装器节点
            del graph[wrapper_id]

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
