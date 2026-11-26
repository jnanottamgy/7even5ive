"""The whole demo as one web service: `python -m seventy5.cloud`.

Why: the phone app should work on its own, with no laptop and no hotspot. One HTTPS address
serves everything the app needs, routed by path:

    /api/*, /bot/*  7even5ive core (cards, approvals, tools, health, the bot webhook)
    /v1/*           PortMax's phone API (portal settings, runner.js, page upload)
    /demo/*         demo-only actions for the app's demo tour (see demo_api); never in api.py
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
        self.demo: Any = None  # the demo-only actions (demo_api), set by build_router
        self.app: Any = None  # the core's App behind `core`; a demo reset replaces both

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


def current_jobs(router: Router) -> list[Any]:
    """The core app's jobs, each re-bound to whichever app the router holds when it runs."""
    from dataclasses import replace

    def runner(name: str) -> Any:
        def run() -> object:
            for job in router.app.jobs():
                if job.name == name:
                    return job.run()
            return None

        return run

    return [replace(job, run=runner(job.name)) for job in router.app.jobs()]


def public_url() -> str | None:
    """A fixed public address, when the host knows it up front (Render does)."""
    url = os.environ.get("PUBLIC_URL") or os.environ.get("RENDER_EXTERNAL_URL")
    return url.rstrip("/") if url else None


def build_router(db_url: str | None = None) -> Router:
    from portmax.api import DevTokens, create_api
    from portmax.connector import Connector, load_connector
    from portmax.mock_portal.app import PortalConfig, create_app
    from portmax.store import Store

    from . import demo
    from .config import settings

    fixed = public_url()
    os.environ.setdefault("PORTMAX_DEV_TOKENS", f"{demo.TOKEN}:{demo.PORTAL_ID}")
    app, core, _, live, lines = demo.prepare(db_url)
    # Counts only: logs never carry message or mail text (the hosts' logs may be CloudWatch).
    mode = "LIVE Jev + Claude" if live else "offline, recorded answers"
    print(f"mode: {mode}; replayed {len(lines)} demo messages", flush=True)

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
    router = Router(core, portmax, portal)
    router.app = app
    router.demo = demo_api(router, db_url or settings.database_url)
    return router


QUIZ_TITLE = "DAA Quiz 2 (greedy + DP)"
NOTES_FILE = "OS_Unit4_Deadlocks.pdf"


def demo_api(router: Router, base_db: str) -> Any:
    """Demo-only actions for the app's demo tour, at /demo/*. Never part of api.py.

    Why on the server: a WhatsApp forward must be signed with the bot's secret, and a secret
    must never ship inside an app. So the app asks, and this service sends the event through
    the real signed webhook, exactly as the bot would: signature check, dedupe, the bot's
    decision checked in code, filed. All of it is invented demo data for the demo student, and
    only that student's token may ask.
    """
    import hashlib
    import hmac
    import json
    import time
    import uuid
    from pathlib import Path

    from fastapi import FastAPI, Header, HTTPException
    from fastapi.testclient import TestClient
    from portmax.mock_portal.app import PortalConfig, create_app

    from . import demo, tools
    from .config import settings
    from .gateway import Denied

    api = FastAPI(title="7even5ive demo tour", docs_url=None, redoc_url=None, openapi_url=None)
    resets = {"n": 0}

    def student(authorization: str | None) -> int:
        try:
            return int(router.app.gateway.authenticate(
                (authorization or "").removeprefix("Bearer ").strip()))
        except Denied as err:
            raise HTTPException(401, str(err)) from err

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
            return {"from": "919800000000", "text": "Win a free iPhone!!"}
        if kind == "forged":
            return {"from": demo.PHONE, "text": "pretend I'm the bot"}
        raise HTTPException(404, f"no demo event {kind!r}")

    @api.post("/demo/forward/{kind}")
    def forward(kind: str, authorization: str | None = Header(None)) -> dict[str, Any]:
        sid = student(authorization)
        event = {**events(kind), "message_id": f"wamid.demo-{kind}-{uuid.uuid4().hex[:10]}"}
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
        """A clean demo: a fresh database with the demo morning, and a fresh mock portal.

        What the student set up stays: a connected Google account, the phones registered for
        wake-ups, and the call consent and quiet hours. Only the demo's data starts over."""
        from . import mail

        sid = student(authorization)
        old = router.app.db
        kept_google = old.google_account(sid)
        kept_devices = old.conn.execute("SELECT token, platform, created_at FROM devices"
                                        " WHERE student_id=?", (sid,)).fetchall()
        kept_student = old.student(sid)
        resets["n"] += 1
        fresh = base_db
        if "://" not in base_db:  # a SQLite file: a new one beside it
            path = Path(base_db)
            fresh = str(path.with_name(f"{path.stem}-reset{resets['n']}{path.suffix}"))
        mail.reset_demo(sid)
        app, core, new_sid, _, lines = demo.prepare(fresh)
        if kept_google is not None:
            app.db.save_google(new_sid, kept_google["email"], kept_google["scopes"],
                               kept_google["refresh_token"], kept_google["connected_at"])
            mail.sync_cards(app.db, new_sid)  # the real mailbox's cards, not the demo's
        for row in kept_devices:
            app.db.add_device(row["token"], new_sid, row["platform"], row["created_at"])
        with app.db.tx() as c:
            c.execute("UPDATE students SET call_consent_at=?, quiet_start=?, quiet_end=?"
                      " WHERE id=?", (kept_student["call_consent_at"], kept_student["quiet_start"],
                                      kept_student["quiet_end"], new_sid))
        router.app, router.core = app, core
        router.portal = create_app(config=PortalConfig(captcha="fixed"))
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
