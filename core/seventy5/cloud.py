"""The whole demo as one web service: `python -m seventy5.cloud`.

Why: the phone app should work on its own, with no laptop and no hotspot. One HTTPS address
serves everything the app needs, routed by path:

    /api/*, /bot/*  7even5ive core (cards, approvals, tools, health, the bot webhook)
    /v1/*           PortMax's phone API (portal settings, runner.js, page upload)
    /dev            the core's development web page
    everything else the mock college portal the app's WebView logs in to

Because the mock portal lives at the service's own address, PortMax accepts uploads only of
pages fetched from that address: PUBLIC_URL (or Render's RENDER_EXTERNAL_URL) when set, else
the scheme and host the upload itself arrives at (behind CloudFront, its HTTPS address).
State is SQLite inside the container and is reseeded from the demo morning on every start;
nothing here is real student data.
"""

from __future__ import annotations

import os
import sys
from contextvars import ContextVar
from typing import Any

PREFIXES_CORE = ("/api/", "/bot/")
# The address the phone is using for this request. All three apps share it, so the portal
# pages it uploads must come from exactly here.
REQUEST_ORIGIN: ContextVar[str | None] = ContextVar("REQUEST_ORIGIN", default=None)


def origin_of(scope: dict[str, Any]) -> str | None:
    """scheme://host the client used. Behind CloudFront the scheme is in its own header."""
    headers = {k.decode("latin-1").lower(): v.decode("latin-1") for k, v in scope.get("headers", [])}
    host = headers.get("host")
    if not host:
        return None
    scheme = headers.get("cloudfront-forwarded-proto") or headers.get("x-forwarded-proto")
    if not scheme and "x-amz-cf-id" in headers:
        # Through CloudFront without its protocol header: the distribution redirects every
        # viewer to HTTPS, so the phone used HTTPS.
        scheme = "https"
    scheme = (scheme or scope.get("scheme", "http")).split(",")[0].strip()
    return f"{scheme}://{host}"


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
        REQUEST_ORIGIN.set(origin_of(scope))
        if path.startswith(PREFIXES_CORE):
            await self.core(scope, receive, send)
        elif path.startswith("/v1/"):
            await self.portmax(scope, receive, send)
        elif path == "/dev":
            await self.core({**scope, "path": "/", "raw_path": b"/"}, receive, send)
        else:
            await self.portal(scope, receive, send)


def public_url() -> str | None:
    """A fixed public address, when the host knows it up front (Render does)."""
    url = os.environ.get("PUBLIC_URL") or os.environ.get("RENDER_EXTERNAL_URL")
    return url.rstrip("/") if url else None


def build_router() -> Router:
    from portmax.api import DevTokens, create_api
    from portmax.connector import Connector, load_connector
    from portmax.mock_portal.app import PortalConfig, create_app
    from portmax.store import Store

    from . import demo
    from .config import settings

    fixed = public_url()
    os.environ.setdefault("PORTMAX_DEV_TOKENS", f"{demo.TOKEN}:{demo.PORTAL_ID}")
    _, core, _, live, lines = demo.prepare()
    print(f"mode: {'LIVE Jev + Claude' if live else 'offline, recorded answers'}")
    print("\n".join(lines))

    def connectors(college: str) -> Connector:
        # The mock portal is this service. Pages must come from the address the phone uses for
        # it: the fixed public URL if the host gives one, else the address of this request
        # (EC2 behind CloudFront learns its HTTPS address only once CloudFront exists).
        connector = load_connector(college)
        origin = fixed or REQUEST_ORIGIN.get()
        if college != "mockcollege" or not origin:
            return connector
        manifest = connector.manifest.model_copy(update={"base_url": origin})
        return Connector(manifest=manifest, plan=connector.plan, parsers=connector.parsers,
                         root=connector.root)

    portmax = create_api(Store(settings.portmax_database_url), DevTokens(), connectors)
    portal = create_app(config=PortalConfig(captcha="fixed"))
    where = fixed or "the address each request arrives at"
    print(f"\n7even5ive is serving; portal pages must come from {where}", flush=True)
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
