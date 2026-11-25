"""HTTP API: the bot's webhook, the phone's cards, and Approve.

Why FastAPI here: the same routes run under uvicorn locally and behind API Gateway on
AWS (via an ASGI adapter), so the demo and the deployment share one code path.
Not: a WebSocket for live cards -- the page polls every few seconds; WebSocket
connection-minutes cost money and the demo does not need them.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from fastapi import BackgroundTasks, FastAPI, Header, HTTPException, Request
from fastapi.responses import FileResponse

from . import tools
from .app import App, build
from .gateway import Denied
from .ingress import BadSignature, accept, verify

WEB = Path(__file__).parent / "web"


def create(app_state: App | None = None) -> FastAPI:
    state = app_state or build()
    api = FastAPI(title="75")

    def student_from(auth: str | None) -> int:
        # Prototype sign-in: the student's personal token as a Bearer header.
        try:
            return state.gateway.authenticate((auth or "").removeprefix("Bearer ").strip())
        except Denied as err:
            raise HTTPException(401, str(err)) from err

    @api.post("/bot/webhook")
    async def bot_webhook(request: Request, background: BackgroundTasks,
                          x_75_timestamp: str | None = Header(None),
                          x_75_signature: str | None = Header(None)) -> dict[str, Any]:
        body = await request.body()
        try:
            verify(body, x_75_timestamp, x_75_signature)
        except BadSignature as err:
            raise HTTPException(401, str(err)) from err
        event = json.loads(body)
        student = state.db.student_by_phone(str(event.get("from", "")))
        if student is None:
            # Unknown number: no reply, no row, no model call. Spam costs one SELECT.
            return {"ok": True}
        payload = {k: event.get(k) for k in ("text", "attachment", "file_id", "group", "decision")
                   if event.get(k)}
        event_id = accept(state.db, state.queue, student["id"], "whatsapp",
                          str(event["message_id"]), payload)
        background.add_task(state.work)
        return {"ok": True, "duplicate": event_id is None}

    @api.get("/api/cards")
    def cards(authorization: str | None = Header(None)) -> dict[str, Any]:
        sid = student_from(authorization)
        db = state.db
        return {
            "student": dict(db.student(sid)) | {"mcp_token": None},
            "due_this_week": tools.due_this_week(db, sid),
            "attendance": tools.attendance(db, sid),
            "materials": tools.materials(db, sid),
            "opportunities": tools.opportunities(db, sid),
            "filtered": sum(1 for r in db.all_cards(sid) if r["status"] == "filtered"),
            "needs_review": [dict(r) for r in db.all_cards(sid) if r["status"] == "needs_review"],
            "approvals": [{"action": r["action"], "args": json.loads(r["args"]),
                           "token": r["token"]} for r in db.pending(sid)],
            "calendar": [dict(r) for r in db.calendar(sid)],
            "audit": [dict(r) for r in db.audit_log(sid)][:12],
        }

    @api.post("/api/approve")
    def approve(body: dict[str, str], authorization: str | None = Header(None)) -> dict[str, Any]:
        sid = student_from(authorization)
        try:
            return state.gateway.approve(sid, body.get("token", ""))
        except Denied as err:
            raise HTTPException(403, str(err)) from err

    @api.get("/")
    def index() -> FileResponse:
        return FileResponse(WEB / "index.html")

    return api
