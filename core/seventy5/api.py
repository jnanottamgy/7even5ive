"""HTTP API: the bot's webhook, the phone's cards, and Approve.

Why FastAPI here: the same routes run under uvicorn locally and behind API Gateway on
AWS (via an ASGI adapter), so the demo and the deployment share one code path.
Not: a WebSocket for live cards -- the page polls every few seconds; WebSocket
connection-minutes cost money and the demo does not need them.
"""

from __future__ import annotations

import json
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, AsyncIterator

from fastapi import BackgroundTasks, FastAPI, Header, HTTPException, Request
from fastapi.responses import FileResponse, Response

from . import ask, calls, clock, files, notify, tools
from .app import App, build
from .config import settings
from .gateway import Denied, read_token
from .ingress import BadSignature, accept, verify
from .scheduler import Scheduler

WEB = Path(__file__).parent / "web"


def create(app_state: App | None = None, run_jobs: bool = False) -> FastAPI:
    """The core's HTTP face. run_jobs=True also runs the background loop (reminders, calls,
    mail) for as long as the server is up -- the online service and the laptop demo do."""
    state = app_state or build()

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        scheduler = Scheduler(state.db, state.jobs()) if run_jobs else None
        if scheduler is not None:
            scheduler.start()
        try:
            yield
        finally:
            if scheduler is not None:
                await scheduler.stop()

    api = FastAPI(title="75", lifespan=lifespan)

    def student_from(auth: str | None) -> int:
        # Prototype sign-in: the student's personal token as a Bearer header.
        try:
            return state.gateway.authenticate((auth or "").removeprefix("Bearer ").strip())
        except Denied as err:
            raise HTTPException(401, str(err)) from err

    def live(token: str) -> bool:
        # A pending row outlives its token (15 minutes); the phone only shows what it can still
        # approve. Used ones are already gone: spending the nonce deletes the row.
        try:
            read_token(token)
        except Denied:
            return False
        return True

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
        payload = {k: event.get(k) for k in ("text", "attachment", "file_id", "group", "decision",
                                             "file") if event.get(k)}
        if payload.get("file"):
            # A file comes with its name or not at all; a bad one is dropped, the message kept.
            try:
                files.check(str(payload["file"]))
                if not payload.get("attachment"):
                    raise files.BadFile("file without a name")
            except files.BadFile:
                payload.pop("file")
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
                           "token": r["token"]} for r in db.pending(sid) if live(r["token"])],
            "calendar": [dict(r) for r in db.calendar(sid)],
            "reminders": notify.list_reminders(db, sid),
            "audit": [dict(r) for r in db.audit_log(sid)][:40],
            # The student's subject list: what the phone offers when they file something.
            "subjects": db.subjects(sid),
            "timetable": tools.timetable(db, sid),
            "marks": tools.marks(db, sid),
            "results": tools.results(db, sid),
        }

    @api.get("/api/files/{item_id}")
    def file(item_id: int, authorization: str | None = Header(None)) -> Response:
        # Only the student's own items; another student's id is simply not found.
        sid = student_from(authorization)
        found = files.file_of(state.db, sid, item_id)
        if found is None:
            raise HTTPException(404, "no file kept for this item")
        name, mime, raw = found
        safe = "".join(ch if ch.isalnum() or ch in "._- " else "_" for ch in name)
        return Response(raw, media_type=mime,
                        headers={"Content-Disposition": f'inline; filename="{safe}"'})

    @api.post("/api/ask")
    def ask_semester(body: dict[str, Any], authorization: str | None = Header(None)) -> dict[str, Any]:
        """A question in plain words, answered from the student's own data through the
        gateway: the same tools and rules as an MCP client."""
        sid = student_from(authorization)
        question = str(body.get("question", "")).strip()
        if not question:
            raise HTTPException(400, "ask a question")
        if len(question) > 500:
            raise HTTPException(400, "keep the question under 500 characters")
        return ask.answer(state.gateway, sid, question)

    @api.post("/api/share")
    def share(body: dict[str, Any], authorization: str | None = Header(None)) -> dict[str, Any]:
        """Something the student shared into the app from another app (a WhatsApp message,
        a PDF). If they said what it is, it is filed as they said, after the same checks as
        a bot decision; if not, the cascade decides as for any message."""
        import uuid

        sid = student_from(authorization)
        text = str(body.get("text") or "").strip()[:4000]
        name = str(body.get("file_name") or "").strip()[:120] or None
        payload: dict[str, Any] = {"text": text} if text else {}
        if body.get("file_b64"):
            if not name:
                raise HTTPException(400, "a shared file needs its name")
            try:
                payload["file"] = files.check(str(body["file_b64"]))
            except files.BadFile as err:
                raise HTTPException(400, str(err)) from err
        if name:
            payload["attachment"] = name
        if not payload:
            raise HTTPException(400, "nothing to file")
        if body.get("kind"):
            payload["by"] = "student"
            payload["decision"] = {k: body.get(k) for k in ("kind", "subject", "title", "due_at")
                                   if body.get(k)}
        event_id = accept(state.db, state.queue, sid, "share", uuid.uuid4().hex, payload)
        state.work()
        row = state.db.item_for_event(sid, event_id) if event_id is not None else None
        if row is None:
            return {"status": "skipped", "item": None}
        card = {k: row[k] for k in ("id", "kind", "subject", "title", "due_at", "status", "route")}
        return {"status": row["status"], "item": card}

    @api.post("/api/approve")
    def approve(body: dict[str, str], authorization: str | None = Header(None)) -> dict[str, Any]:
        sid = student_from(authorization)
        try:
            return state.gateway.approve(sid, body.get("token", ""))
        except Denied as err:
            raise HTTPException(403, str(err)) from err

    @api.post("/api/tools/{tool}")
    def call_tool(tool: str, body: dict[str, Any] | None = None,
                  authorization: str | None = Header(None)) -> dict[str, Any]:
        # The app's door to the same gateway an MCP client uses. No approval token here:
        # an "ask" tool returns approval_needed, and the tap goes through /api/approve.
        sid = student_from(authorization)
        args = (body or {}).get("args")
        args = {} if args is None else args
        if not isinstance(args, dict):
            raise HTTPException(400, "args must be an object")
        try:
            return state.gateway.call(sid, tool, args)
        except Denied as err:
            raise HTTPException(403, str(err)) from err

    # --- the outbox and the phones it wakes -------------------------------------------
    @api.get("/api/notifications")
    def notifications(after: int = 0, limit: int = 50,
                      authorization: str | None = Header(None)) -> dict[str, Any]:
        """What 7even5ive sent the student since `after`. A phone opening for the first time
        asks with after=-1 to learn latest_id without being handed old messages."""
        sid = student_from(authorization)
        latest = state.db.latest_notification_id(sid)
        if after < 0:
            return {"notifications": [], "latest_id": latest}
        rows = state.db.notifications(sid, after, max(1, min(limit, 100)))
        return {"notifications": [{"id": r["id"], "kind": r["kind"], "title": r["title"],
                                   "body": r["body"], "item_id": r["item_id"],
                                   "created_at": r["created_at"]} for r in rows],
                "latest_id": latest}

    @api.post("/api/devices")
    def add_device(body: dict[str, Any], authorization: str | None = Header(None)) -> dict[str, Any]:
        sid = student_from(authorization)
        token = str(body.get("token") or "").strip()
        if not token or len(token) > 4096:
            raise HTTPException(400, "token required")
        platform = str(body.get("platform") or "android")[:20]
        state.db.add_device(token, sid, platform, clock.iso(clock.now()))
        return {"ok": True}

    @api.post("/api/devices/remove")
    def remove_device(body: dict[str, Any],
                      authorization: str | None = Header(None)) -> dict[str, Any]:
        sid = student_from(authorization)
        return {"removed": state.db.remove_device(str(body.get("token") or ""), sid)}

    # --- the urgent call ------------------------------------------------------------------
    @api.get("/api/settings")
    def get_settings(authorization: str | None = Header(None)) -> dict[str, Any]:
        sid = student_from(authorization)
        return {"calls": calls.call_settings(state.db, sid),
                # True when Firebase is configured: the phone is woken at once, not on its pull.
                "push": {"wakeups": getattr(state.sender, "wake", None) is not None}}

    @api.post("/api/settings/calls")
    def set_call_settings(body: dict[str, Any],
                          authorization: str | None = Header(None)) -> dict[str, Any]:
        sid = student_from(authorization)
        enabled = body.get("enabled")
        if enabled is not None and not isinstance(enabled, bool):
            raise HTTPException(400, "enabled must be true or false")
        try:
            out = calls.update_settings(state.db, sid, enabled=enabled,
                                        quiet_start=body.get("quiet_start"),
                                        quiet_end=body.get("quiet_end"))
        except ValueError as err:
            raise HTTPException(400, str(err)) from err
        state.db.audit(sid, "call_settings", "allow", "student", clock.iso(clock.now()))
        return out

    @api.get("/api/calls")
    def call_history(authorization: str | None = Header(None)) -> dict[str, Any]:
        sid = student_from(authorization)
        return {"calls": calls.history(state.db, sid)}

    @api.post("/api/calls/test")
    def test_call(authorization: str | None = Header(None)) -> dict[str, Any]:
        sid = student_from(authorization)
        try:
            return calls.test_call(state.db, state.caller, state.sender, sid)
        except ValueError as err:
            raise HTTPException(409, str(err)) from err

    @api.post("/api/calls/webhook")
    async def call_webhook(request: Request) -> dict[str, Any]:
        # ElevenLabs' post-call webhook. Signed; anything unsigned or stale is refused.
        body = await request.body()
        try:
            calls.verify_webhook(body, request.headers.get("elevenlabs-signature"),
                                 settings.elevenlabs_webhook_secret)
            event = json.loads(body)
        except (calls.BadWebhook, ValueError) as err:
            raise HTTPException(401, str(err)) from err
        if not isinstance(event, dict):
            raise HTTPException(400, "event must be an object")
        return calls.handle_webhook(state.db, state.sender, event)

    @api.get("/api/health")
    def health() -> dict[str, Any]:
        # No token: the phone app scans its Wi-Fi for this to find the laptop by itself.
        # Says only what this is; nothing about any student.
        return {"service": "7even5ive", "version": 1}

    @api.get("/")
    def index() -> FileResponse:
        return FileResponse(WEB / "index.html")

    return api
