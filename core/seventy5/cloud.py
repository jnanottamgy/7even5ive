"""The whole demo as one web service: `python -m seventy5.cloud`.

Why: the phone app should work on its own, with no laptop and no hotspot. One HTTPS address
serves everything the app needs, routed by path:

    /api/*, /bot/*  7even5ive core (cards, approvals, tools, health, the bot webhook)
    /v1/*           PortMax's phone API (portal settings, runner.js, page upload)
    /mcp            MCP over HTTP for the student's own Claude Code, Codex or other MCP app
    /oauth/*, /.well-known/oauth-*   how those apps sign in as the student (connector.py)
    /demo/*         demo-only actions for the app's demo tour (see demo_api); never in api.py
    /dev            the core's development web page
    everything else the mock college portal the app's WebView logs in to

Because the mock portal lives at the service's own address, PortMax accepts uploads only of
pages fetched from that address: PUBLIC_URL (or Render's RENDER_EXTERNAL_URL) when set, else
the scheme and host the upload itself arrives at (behind CloudFront, its HTTPS address).
Data: with a Supabase DATABASE_URL, real accounts live there and the demo student's morning is
refreshed once a day; without one, SQLite inside the container, reseeded on every start. The demo
student's data is invented; the demo actions below touch nothing else.
"""

from __future__ import annotations

import os
import sys
from contextvars import ContextVar
from typing import Any

PREFIXES_CORE = ("/api/", "/bot/")
# The MCP connector's sign-in (connector.py): its OAuth metadata and endpoints.
PREFIXES_CONNECTOR = ("/oauth/", "/.well-known/oauth-")
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
        self.demo: Any = None  # the demo-only actions (demo_api), set by build_router
        self.app: Any = None  # the core's App behind `core`; a demo reset replaces both
        self.mcp: Any = None  # MCP over HTTP (mcp_server.http_app), set by build_router
        self.connector: Any = None  # its OAuth sign-in (connector.oauth_app), set by build_router

    async def __call__(self, scope: dict[str, Any], receive: Any, send: Any) -> None:
        if scope["type"] == "lifespan":
            await self._lifespan(receive, send)
            return
        path = scope.get("path", "")
        REQUEST_ORIGIN.set(origin_of(scope))
        if path.startswith(PREFIXES_CORE):
            await self.core(scope, receive, send)
        elif path.startswith("/v1/"):
            await self.portmax(scope, receive, send)
        elif path in ("/mcp", "/mcp/") and self.mcp is not None:
            await self.mcp(scope, receive, send)
        elif path.startswith(PREFIXES_CONNECTOR) and self.connector is not None:
            await self.connector(scope, receive, send)
        elif path.startswith("/demo/") and self.demo is not None:
            await self.demo(scope, receive, send)
        elif path == "/dev":
            await self.core({**scope, "path": "/", "raw_path": b"/"}, receive, send)
        else:
            await self.portal(scope, receive, send)


    async def _lifespan(self, receive: Any, send: Any) -> None:
        """The background loop (reminders, calls, mail) runs for as long as the service is up.

        It lives here, not in the core app, because a demo reset swaps the core app for a fresh
        one: each job looks up the current app when it runs. PortMax's API and the mock portal
        have no startup work. On Lambda (lambda_demo) there is no lifespan and no loop.
        """
        from .scheduler import Scheduler

        scheduler = None
        while True:
            message = await receive()
            if message["type"] == "lifespan.startup":
                if self.app is not None:
                    scheduler = Scheduler(lambda: self.app.db, current_jobs(self))
                    scheduler.start()
                await send({"type": "lifespan.startup.complete"})
            elif message["type"] == "lifespan.shutdown":
                if scheduler is not None:
                    await scheduler.stop()
                await send({"type": "lifespan.shutdown.complete"})
                return


# When the demo student gets a fresh morning each day, India time: before anyone is up.
DEMO_REFRESH_AT = "05:00"


def current_jobs(router: Router) -> list[Any]:
    """The core app's jobs, each re-bound to whichever app the router holds when it runs, and
    the demo's daily refresh (a warm Lambda or a long-running server may not restart for days)."""
    from dataclasses import replace

    from mailfilter.config import parse_times

    from . import demo
    from .scheduler import Job

    def runner(name: str) -> Any:
        def run() -> object:
            for job in router.app.jobs():
                if job.name == name:
                    return job.run()
            return None

        return run

    jobs = [replace(job, run=runner(job.name)) for job in router.app.jobs()]
    jobs.append(Job("demo-morning", lambda: demo.refresh_if_stale(router.app),
                    at=parse_times(DEMO_REFRESH_AT)))
    return jobs


def public_url() -> str | None:
    """A fixed public address, when the host knows it up front (Render does)."""
    url = os.environ.get("PUBLIC_URL") or os.environ.get("RENDER_EXTERNAL_URL")
    return url.rstrip("/") if url else None


class PortalSignIn:
    """PortMax's sign-in, answered by the core's: whatever the core accepts (a Supabase access
    token, a personal token, the demo's) is the student whose portal data this is."""

    def __init__(self, router: Router) -> None:
        self.router = router

    def student_for(self, token: str) -> str | None:
        from .gateway import Denied

        try:
            sid = self.router.app.gateway.authenticate(token)
        except Denied:
            return None
        row = self.router.app.db.student(sid)
        return str(row["portal_id"]) if row is not None and row["portal_id"] else None


def build_router(db_url: str | None = None) -> Router:
    from portmax.api import create_api
    from portmax.connector import Connector, load_connector
    from portmax.mock_portal.app import PortalConfig, create_app

    from . import demo, mail
    from .tools import portal_store

    fixed = public_url()
    app, core, _, live, lines = demo.prepare(db_url, daily=True)
    # Counts only: logs never carry message or mail text (the hosts' logs may be CloudWatch).
    mode = ("new messages: LIVE Jev + Claude; demo morning: recorded answers" if live
            else "offline, recorded answers")
    print(f"mode: {mode}; replayed {len(lines)} demo messages", flush=True)
    from .report import lines as report

    print("\n".join(report()), flush=True)

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

    portal = create_app(config=PortalConfig(captcha="fixed"))
    router = Router(core, None, portal)
    router.app = app
    # One store each, shared with the core's own reads (tools.portal_store, mail.store); each
    # locks its tables down on Supabase as it opens (db.open_store), as Database does the core's.
    router.portmax = create_api(portal_store(), PortalSignIn(router), connectors)
    mail.store()
    where = fixed or "the address each request arrives at"
    print(f"\n7even5ive is serving; portal pages must come from {where}", flush=True)
    from .mcp_server import http_app

    router.demo = demo_api(router)
    router.mcp = http_app(lambda: router.app)  # always the current app, across demo resets
    from .connector import oauth_app

    router.connector = oauth_app(lambda: router.app)
    return router


QUIZ_TITLE = "DAA Quiz 2 (greedy + DP)"
NOTES_FILE = "OS_Unit4_Deadlocks.pdf"
STRANGER = "919800000000"  # an invented number no student has


def demo_api(router: Router) -> Any:
    """Demo-only actions for the app's demo tour, at /demo/*. Never part of api.py.

    Why on the server: a WhatsApp forward must be signed with the bot's secret, and a secret
    must never ship inside an app. So the app asks, and this service sends the event through
    the real signed webhook, exactly as the bot would: signature check, dedupe, the bot's
    decision checked in code, filed. All of it is invented demo data for the demo student, and
    only the demo student may ask: a real account gets 403 and nothing changes.
    """
    import hashlib
    import hmac
    import json
    import time
    import uuid

    from fastapi import FastAPI, Header, HTTPException
    from fastapi.testclient import TestClient
    from portmax.mock_portal.app import PortalConfig, create_app

    from . import demo, tools
    from .config import settings
    from .gateway import Denied

    from .auth import Limiter

    api = FastAPI(title="7even5ive demo tour", docs_url=None, redoc_url=None, openapi_url=None)
    resets = {"n": 0}
    # The demo's token is public: a few resets a minute is plenty for a presenter.
    reset_limit = Limiter(3, 60)

    def student(authorization: str | None) -> int:
        try:
            sid = int(router.app.gateway.authenticate(
                (authorization or "").removeprefix("Bearer ").strip()))
        except Denied as err:
            raise HTTPException(401, str(err)) from err
        if not demo.is_demo(router.app.db, sid):
            raise HTTPException(403, "Only the demo account can use the demo tour.")
        return sid

    def events(kind: str) -> dict[str, Any]:
        if kind == "quiz":
            return {"from": demo.PHONE, "text": "DAA quiz in 2 days 10am, greedy + DP",
                    "group": "CSE 3B Announcements",
                    "decision": {"kind": "exam", "subject": "Design and Analysis of Algorithms",
                                 "title": QUIZ_TITLE, "due_at": demo._at(2, 10)}}
        if kind == "notes":
            return {"from": demo.PHONE, "text": "OS unit 4 slides", "attachment": NOTES_FILE,
                    "file_id": "f_demo_notes",
                    "decision": {"kind": "material", "subject": "Operating Systems"}}
        if kind == "stranger":
            return {"from": STRANGER, "text": "Win a free iPhone!!"}
        if kind == "forged":
            return {"from": demo.PHONE, "text": "pretend I'm the bot"}
        raise HTTPException(404, f"no demo event {kind!r}")

    @api.post("/demo/forward/{kind}")
    def forward(kind: str, authorization: str | None = Header(None)) -> dict[str, Any]:
        sid = student(authorization)
        event = {**events(kind), "message_id": f"wamid.demo-{kind}-{uuid.uuid4().hex[:10]}"}
        # The webhook files by sender. Each invented sender must be the demo student (or no one,
        # for the stranger): a real account that linked the number would get the invented event.
        owner = router.app.db.student_by_phone(str(event["from"]))
        expected = None if kind == "stranger" else sid
        if (owner["id"] if owner is not None else None) != expected:
            raise HTTPException(409, "The demo's WhatsApp number is linked to a real account, so"
                                     " the tour can't forward as the bot.")
        body = json.dumps(event).encode()
        ts = int(time.time())
        secret = "not-the-bot-secret" if kind == "forged" else settings.bot_secret
        sig = hmac.new(secret.encode(), f"{ts}.".encode() + body, hashlib.sha256).hexdigest()
        reply = TestClient(router.core).post(
            "/bot/webhook", content=body,
            headers={"X-75-Timestamp": str(ts), "X-75-Signature": sig},
        )
        db = router.app.db
        filed = None
        if kind == "quiz":
            filed = next((c for c in tools.due_this_week(db, sid) if c["title"] == QUIZ_TITLE), None)
        elif kind == "notes":
            filed = next((c for c in tools.materials(db, sid) if c["title"] == NOTES_FILE), None)
        try:
            answer: Any = reply.json()
        except ValueError:
            answer = reply.text
        return {"kind": kind, "webhook_status": reply.status_code, "webhook_reply": answer,
                "filed": filed}

    @api.post("/demo/reset")
    def reset(authorization: str | None = Header(None)) -> dict[str, Any]:
        """A clean demo: the demo student back to the morning, and a fresh mock portal.

        Only the demo student's rows change. Its phones (wake-ups) and call settings stay; no
        other student is touched (on Supabase they share this database)."""
        student(authorization)
        if not reset_limit.allow("reset"):
            raise HTTPException(429, "The demo was reset a moment ago. Try again in a minute.")
        _, lines = demo.morning(router.app)
        router.portal = create_app(config=PortalConfig(captcha="fixed"))
        resets["n"] += 1
        print(f"demo reset {resets['n']}: replayed {len(lines)} demo messages", flush=True)
        return {"ok": True, "replayed": len(lines)}

    return api


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
