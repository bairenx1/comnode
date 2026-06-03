from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Settings:
    comfy_base_url: str = os.getenv("COMFY_BASE_URL", "http://127.0.0.1:8188")
    webui_host: str = os.getenv("WEBUI_HOST", "127.0.0.1")
    webui_port: int = int(os.getenv("WEBUI_PORT", "8288"))
    workflows_dir: Path = Path(
        os.getenv(
            "WORKFLOWS_DIR",
            str(Path(__file__).resolve().parents[1] / "workflows"),
        )
    )
    frontend_dir: Path = Path(
        os.getenv(
            "FRONTEND_DIR",
            str(Path(__file__).resolve().parents[1] / "frontend"),
        )
    )
    request_timeout_sec: int = int(os.getenv("WEBUI_REQUEST_TIMEOUT", "120"))


SETTINGS = Settings()
