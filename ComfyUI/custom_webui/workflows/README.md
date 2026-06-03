# 固定工作流目录

请把你在 ComfyUI 画布中导出的 JSON 放在这个目录。

## 命名建议
- `txt2img.json`
- `img2img.json`
- `img2video.json`

## 映射文件
每个工作流需要一个 `*.mapping.json`：
- `workflow_id`: 业务 ID
- `workflow_file`: 对应 workflow JSON 文件名
- `field_mapping`: UI 字段到 `nodeId.inputs.key` 的映射

示例见同目录 `txt2img.mapping.json` 等文件。
