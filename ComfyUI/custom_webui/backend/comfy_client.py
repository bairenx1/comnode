from __future__ import annotations

import json
import re
import uuid
from typing import Any

import aiohttp


class ComfyClient:
    def __init__(self, base_url: str, timeout_sec: int = 120) -> None:
        self.base_url = base_url.rstrip("/")
        self._timeout = aiohttp.ClientTimeout(total=timeout_sec)
        self._session: aiohttp.ClientSession | None = None

    async def close(self) -> None:
        if self._session is not None:
            await self._session.close()
            self._session = None

    async def _ensure_session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession(timeout=self._timeout)
        return self._session

    def ws_url(self) -> str:
        http_url = self.base_url
        if http_url.startswith("https://"):
            return "wss://" + http_url[len("https://") :] + "/ws"
        return "ws://" + http_url[len("http://") :] + "/ws"

    async def submit_prompt(
        self,
        prompt_graph: dict[str, Any],
        client_id: str | None = None,
        extra_data: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        payload = {"prompt": prompt_graph}
        payload["client_id"] = client_id or uuid.uuid4().hex
        if extra_data:
            payload["extra_data"] = extra_data
        return await self._post_json("/prompt", payload)

    async def interrupt(self) -> dict[str, Any]:
        session = await self._ensure_session()
        async with session.post(f"{self.base_url}/interrupt") as resp:
            resp.raise_for_status()
            return await resp.json()

    async def get_queue(self) -> dict[str, Any]:
        return await self._get_json("/queue")

    async def get_history(self, prompt_id: str | None = None) -> dict[str, Any]:
        if prompt_id:
            return await self._get_json(f"/history/{prompt_id}")
        return await self._get_json("/history")

    async def get_job(self, prompt_id: str) -> dict[str, Any]:
        return await self._get_json(f"/history/{prompt_id}")

    async def list_assets(self, query: dict[str, str]) -> dict[str, Any]:
        return await self._get_json("/api/assets", params=query)

    async def upload_asset(
        self,
        file_bytes: bytes,
        filename: str,
        tags: list[str],
        user_metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        form = aiohttp.FormData()
        form.add_field("file", file_bytes, filename=filename, content_type="application/octet-stream")
        form.add_field("tags", json.dumps(tags))
        if user_metadata:
            form.add_field("user_metadata", json.dumps(user_metadata))
        session = await self._ensure_session()
        async with session.post(f"{self.base_url}/api/assets", data=form) as resp:
            resp.raise_for_status()
            return await resp.json()

    async def delete_asset(self, asset_id: str, delete_content: bool = False) -> dict[str, Any]:
        session = await self._ensure_session()
        params = {"delete_content": "1" if delete_content else "0"}
        async with session.delete(f"{self.base_url}/api/assets/{asset_id}", params=params) as resp:
            resp.raise_for_status()
            return await resp.json()

    async def get_asset_content(self, asset_id: str) -> tuple[bytes, str, str]:
        """返回 (文件内容, content_type, filename)"""
        session = await self._ensure_session()
        async with session.get(f"{self.base_url}/api/assets/{asset_id}/content") as resp:
            resp.raise_for_status()
            content_type = resp.headers.get("Content-Type", "application/octet-stream")
            disposition = resp.headers.get("Content-Disposition", "")
            filename = "download"
            if "filename=" in disposition:
                m = re.search(r'filename[^;=\n]*=["\']?([^"\';\n]*)', disposition)
                if m:
                    filename = m.group(1)
            return await resp.read(), content_type, filename

    async def _get_json(self, path: str, params: dict[str, str] | None = None) -> dict[str, Any]:
        session = await self._ensure_session()
        async with session.get(f"{self.base_url}{path}", params=params) as resp:
            resp.raise_for_status()
            return await resp.json()

    async def _post_json(self, path: str, payload: dict[str, Any]) -> dict[str, Any]:
        session = await self._ensure_session()
        async with session.post(f"{self.base_url}{path}", json=payload) as resp:
            if resp.status >= 400:
                try:
                    body = await resp.json()
                    err_msg = body.get("error", {})
                    if isinstance(err_msg, dict):
                        err_msg = err_msg.get("message", str(body))
                except Exception:
                    err_msg = await resp.text()
                raise aiohttp.ClientResponseError(
                    resp.request_info,
                    resp.history,
                    status=resp.status,
                    message=f"{err_msg}",
                    headers=resp.headers,
                )
            return await resp.json()
