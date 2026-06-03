from aiohttp import web

from .app import create_app
from .config import SETTINGS


def main() -> None:
    web.run_app(create_app(), host=SETTINGS.webui_host, port=SETTINGS.webui_port)


if __name__ == "__main__":
    main()
