"""The whole demo as one web service: `python -m seventy5.cloud`.

Why: the phone app should work on its own, with no laptop and no hotspot. One HTTPS address
serves everything the app needs, routed by path:

    /api/*, /bot/*  7even5ive core (cards, approvals, tools, health, the bot webhook)
    /v1/*           PortMax's phone API (portal settings, runner.js, page upload)
    /dev            the core's development web page
    everything else the mock college portal the app's WebView logs in to

Because the mock portal now lives at the service's own address, PortMax is told so: uploads
are accepted only from pages fetched at PUBLIC_URL (Render sets RENDER_EXTERNAL_URL itself).
State is SQLite inside the container and is reseeded from the demo morning on every start;
nothing here is real student data.
"""

from __future__ import annotations

import os
import sys
from typing import Any

PREFIXES_CORE = ("/api/", "/bot/")


class Router:
    """Sends each request to the app that owns its path. Plain ASGI, no extra dependency."""

    def __init__(self, core: Any, portmax: Any, portal: Any) -> None:
        self.core, self.portmax, self.portal = core, portmax, portal

    async def __call__(self, scope: dict[str, Any], receive: Any, send: Any) -> None:
        if scope["type"] == "lifespan":
            # None of the three apps uses startup or shutdown events.
            while True:
                message = await receive()
                if message["type"] == "lifespan.startup":
                    await send({"type": "lifespan.startup.complete"})
                elif message["type"] == "lifespan.shutdown":
                    await send({"type": "lifespan.shutdown.complete"})
                    return
        path = scope.get("path", "")
        if path.startswith(PREFIXES_CORE):
            await self.core(scope, receive, send)
        elif path.startswith("/v1/"):
            await self.portmax(scope, receive, send)
        elif path == "/dev":
            await self.core({**scope, "path": "/", "raw_path": b"/"}, receive, send)
        else:
            await self.portal(scope, receive, send)


def public_url() -> str:
    url = os.environ.get("PUBLIC_URL") or os.environ.get("RENDER_EXTERNAL_URL")
    if not url:
        port = os.environ.get("PORT", "8000")
        url = f"http://127.0.0.1:{port}"
    return url.rstrip("/")


def build_router() -> Router:
    from portmax.api import DevTokens, create_api
    from portmax.connector import with_portal_origins
    from portmax.mock_portal.app import PortalConfig, create_app
    from portmax.store import Store

    from . import demo
    from .config import settings

    origin = public_url()
    os.environ.setdefault("PORTMAX_DEV_TOKENS", f"{demo.TOKEN}:{demo.PORTAL_ID}")
    _, core, _, live, lines = demo.prepare()
    print(f"mode: {'LIVE Jev + Claude' if live else 'offline, recorded answers'}")
    print("\n".join(lines))

    portmax = create_api(
        Store(settings.portmax_database_url),
        DevTokens(),
        with_portal_origins({"mockcollege": origin}),
    )
    portal = create_app(config=PortalConfig(captcha="fixed"))
    print(f"\n7even5ive is serving at {origin} (portal pages must come from there)", flush=True)
    return Router(core, portmax, portal)


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
    import uvicorn

    uvicorn.run(
        build_router(),
        host="0.0.0.0",
        port=int(os.environ.get("PORT", "8000")),
        proxy_headers=True,
        forwarded_allow_ips="*",
    )


if __name__ == "__main__":
    main()
