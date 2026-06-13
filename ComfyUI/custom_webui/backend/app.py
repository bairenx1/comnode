from __future__ import annotations

import asyncio
import json
import uuid
from pathlib import Path

import aiohttp
from aiohttp import web

from .comfy_client import ComfyClient
from .config import SETTINGS
from .workflow_registry import WorkflowRegistry
from .convert_workflow import auto_convert_all


def create_app() -> web.Application:
    app = web.Application(client_max_size=1024 * 1024 * 200)
    routes = web.RouteTableDef()

    registry = WorkflowRegistry(SETTINGS.workflows_dir)
    comfy = ComfyClient(SETTINGS.comfy_base_url, SETTINGS.request_timeout_sec)

    app["registry"] = registry
    app["comfy"] = comfy

    def comfy_down_response(err: Exception) -> web.Response:
        msg = str(err)
        status = 503
        # 如果是 ComfyUI 返回的 4xx/5xx，透传真正错误
        if isinstance(err, aiohttp.ClientResponseError):
            status = 502
            hint = f"ComfyUI 返回错误 ({err.status}): {msg}"
        else:
            hint = f"无法连接 ComfyUI 后端: {msg}\n请确认 ComfyUI 已启动（默认 http://127.0.0.1:8188）"
        return web.json_response(
            {"error": "comfyui_error", "message": hint},
            status=status,
        )

    @routes.get("/api/health")
    async def health(_: web.Request) -> web.Response:
        return web.json_response({"ok": True, "comfy_base_url": SETTINGS.comfy_base_url})

    @routes.get("/api/workflows")
    async def list_workflows(_: web.Request) -> web.Response:
        registry.reload()
        return web.json_response({"workflows": registry.list_workflows()})

    @routes.post("/api/workflows/refresh")
    async def refresh_workflows(_: web.Request) -> web.Response:
        count = auto_convert_all()
        registry.reload()
        return web.json_response({"converted": count, "workflows": registry.list_workflows()})

    @routes.post("/api/queue/batch")
    async def queue_batch(request: web.Request) -> web.Response:
        try:
            body = await request.json()
            workflow_id = body["workflow_id"]
            jobs = body.get("jobs", [])
            client_id = body.get("client_id", uuid.uuid4().hex)
            queued = []
            for job in jobs:
                params = job.get("params", {})
                assets = job.get("asset_hashes", {})
                try:
                    prompt_graph, comfy_extra = registry.build_prompt_graph(workflow_id, params, assets)
                except KeyError as e:
                    return web.json_response(
                        {"error": "unknown_workflow", "message": f"工作流 '{workflow_id}' 不存在: {e}"},
                        status=400,
                    )
                extra = {"source": "custom_webui", "workflow_id": workflow_id}
                if comfy_extra:
                    extra.update(comfy_extra)
                result = await comfy.submit_prompt(
                    prompt_graph,
                    client_id=client_id,
                    extra_data=extra,
                )
                queued.append(
                    {
                        "prompt_id": result.get("prompt_id"),
                        "number": result.get("number"),
                        "node_errors": result.get("node_errors", {}),
                        "request": job,
                    }
                )
            return web.json_response({"client_id": client_id, "queued": queued})
        except aiohttp.ClientError as e:
            return comfy_down_response(e)
        except Exception as e:
            return web.json_response(
                {"error": "internal_error", "message": str(e)},
                status=500,
            )

    @routes.get("/api/jobs/{prompt_id}")
    async def get_job(request: web.Request) -> web.Response:
        try:
            prompt_id = request.match_info["prompt_id"]
            history = await comfy.get_history(prompt_id)
            return web.json_response({"history": history.get(prompt_id)})
        except aiohttp.ClientError as e:
            return comfy_down_response(e)

    @routes.get("/api/queue")
    async def get_queue(_: web.Request) -> web.Response:
        try:
            return web.json_response(await comfy.get_queue())
        except aiohttp.ClientError as e:
            return comfy_down_response(e)

    @routes.get("/api/assets")
    async def list_assets(request: web.Request) -> web.Response:
        try:
            query = {k: v for k, v in request.rel_url.query.items()}
            result = await comfy.list_assets(query)
            return web.json_response(result)
        except aiohttp.ClientError as e:
            return comfy_down_response(e)

    @routes.post("/api/assets/upload")
    async def upload_asset(request: web.Request) -> web.Response:
        try:
            data = await request.post()
            file_item = data.get("file")
            if file_item is None or not getattr(file_item, "file", None):
                return web.json_response({"error": "file is required"}, status=400)
            tags = data.get("tags", "input")
            tags_list = [x.strip() for x in str(tags).split(",") if x.strip()]
            file_bytes = file_item.file.read()
            result = await comfy.upload_asset(
                file_bytes=file_bytes,
                filename=file_item.filename or "upload.bin",
                tags=tags_list,
                user_metadata={"uploader": "custom_webui"},
            )
            return web.json_response(result)
        except aiohttp.ClientError as e:
            return comfy_down_response(e)

    @routes.delete("/api/assets/{asset_id}")
    async def delete_asset(request: web.Request) -> web.Response:
        try:
            asset_id = request.match_info["asset_id"]
            delete_content = request.query.get("delete_content", "0")
            result = await comfy.delete_asset(asset_id, delete_content=delete_content == "1")
            return web.json_response(result)
        except aiohttp.ClientError as e:
            return comfy_down_response(e)

    @routes.get("/api/assets/{asset_id}/content")
    async def download_asset(request: web.Request) -> web.Response:
        try:
            asset_id = request.match_info["asset_id"]
            content, content_type, filename = await comfy.get_asset_content(asset_id)
            from urllib.parse import quote
            disposition = f'attachment; filename="{quote(filename)}"'
            return web.Response(
                body=content,
                content_type=content_type,
                headers={"Content-Disposition": disposition},
            )
        except aiohttp.ClientError as e:
            return comfy_down_response(e)

    @routes.get("/api/ws")
    async def ws_proxy(request: web.Request) -> web.WebSocketResponse:
        ws_server = web.WebSocketResponse()
        await ws_server.prepare(request)
        target_url = comfy.ws_url()

        try:
            async with aiohttp.ClientSession() as session:
                async with session.ws_connect(
                    target_url + "?" + request.query_string
                ) as ws_client:

                    async def pump(source, sink):
                        async for msg in source:
                            if msg.type == aiohttp.WSMsgType.TEXT:
                                await sink.send_str(msg.data)
                            elif msg.type == aiohttp.WSMsgType.BINARY:
                                await sink.send_bytes(msg.data)
                            elif msg.type in (aiohttp.WSMsgType.CLOSE, aiohttp.WSMsgType.CLOSING, aiohttp.WSMsgType.CLOSED):
                                break

                    task_c2s = asyncio.ensure_future(pump(ws_server, ws_client))
                    task_s2c = asyncio.ensure_future(pump(ws_client, ws_server))
                    done, pending = await asyncio.wait(
                        [task_c2s, task_s2c],
                        return_when=asyncio.FIRST_COMPLETED,
                    )
                    for t in pending:
                        t.cancel()
        except aiohttp.WSServerHandshakeError as e:
            try:
                await ws_server.send_json({"type": "error", "message": f"ComfyUI WebSocket 连接失败: {str(e)}"})
            except Exception:
                pass
        except Exception as e:
            try:
                await ws_server.send_json({"type": "error", "message": str(e)})
            except Exception:
                pass

        return ws_server

    @routes.get("/view")
    async def view_proxy(request: web.Request) -> web.StreamResponse:
        try:
            query = request.rel_url.query_string
            target_url = f"{SETTINGS.comfy_base_url}/view?{query}"
            async with aiohttp.ClientSession() as session:
                async with session.get(target_url) as resp:
                    resp.raise_for_status()
                    body = await resp.read()
                    return web.Response(body=body, content_type=resp.content_type)
        except aiohttp.ClientError as e:
            return web.Response(status=502, text=f"Proxy error: {e}")

    @routes.get("/api/view")
    async def api_view_proxy(request: web.Request) -> web.StreamResponse:
        try:
            query = request.rel_url.query_string
            target_url = f"{SETTINGS.comfy_base_url}/api/view?{query}"
            async with aiohttp.ClientSession() as session:
                async with session.get(target_url) as resp:
                    resp.raise_for_status()
                    body = await resp.read()
                    return web.Response(body=body, content_type=resp.content_type)
        except aiohttp.ClientError as e:
            return web.Response(status=502, text=f"Proxy error: {e}")

    @routes.get("/api/ws-info")
    async def ws_info(_: web.Request) -> web.Response:
        proxied_ws_url = f"ws://{SETTINGS.webui_host}:{SETTINGS.webui_port}/api/ws"
        proxied_base_url = f"http://{SETTINGS.webui_host}:{SETTINGS.webui_port}"
        return web.json_response({"ws_url": proxied_ws_url, "base_url": proxied_base_url, "comfy_base_url": SETTINGS.comfy_base_url})

    @routes.get("/")
    async def index(_: web.Request) -> web.FileResponse:
        return web.FileResponse(SETTINGS.frontend_dir / "index.html")

    app.add_routes(routes)
    app.router.add_static("/assets", path=str(SETTINGS.frontend_dir / "assets"), name="frontend-assets")

    async def on_shutdown(app_ref: web.Application) -> None:
        client: ComfyClient = app_ref["comfy"]
        await client.close()

    app.on_shutdown.append(on_shutdown)
    return app

