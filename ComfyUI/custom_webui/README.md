# Custom WebUI for ComfyUI

这个模块实现了一个独立 WebUI，用于连接后台 ComfyUI：
- 侧边栏固定工作流（文生图/图生图/图生视频）
- 素材上传到 `/api/assets`
- 参数映射到 workflow JSON
- 批量提交到 `/prompt`
- 队列/任务/资产查询
- WebSocket 实时日志

## 快速启动

在仓库根目录双击：

`start_comfyui_and_webui.bat`

它会：
1. 后台启动 ComfyUI（`--enable-assets --disable-auto-launch`）
2. 启动 custom webui backend（默认 `127.0.0.1:8288`）
3. 自动打开浏览器到新的 WebUI 页面

## 目录说明

- `backend/`: Aiohttp 后端
- `frontend/`: 静态页面
- `workflows/`: workflow JSON 与 mapping
- `tests/`: 端到端验证脚本

## 你需要替换的内容

1. 用你在 ComfyUI 画布导出的真实 JSON 替换：
   - `workflows/txt2img.json`
   - `workflows/img2img.json`
   - `workflows/img2video.json`
2. 根据真实节点 ID 调整每个 `*.mapping.json` 的 `field_mapping`。
3. 确保 `CheckpointLoaderSimple` 节点使用你机器里存在的模型名。

## 批量提交请求体格式

```json
{
  "workflow_id": "txt2img",
  "jobs": [
    {"params": {"prompt": "a cat", "negative_prompt": "bad", "seed": 1, "steps": 20, "cfg": 7.5, "width": 1024, "height": 1024}},
    {"params": {"prompt": "a dog", "negative_prompt": "blur", "seed": 2, "steps": 24, "cfg": 6.5, "width": 768, "height": 768}}
  ],
  "client_id": "optional_custom_client_id"
}
```
