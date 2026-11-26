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
from fastapi.responses import FileResponse, HTMLResponse, Response

from . import briefing, calls, clock, google, mail, notify, tools, voice
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
        if str(event.get("type", "")).startswith("deadline."):
            # A deadline the bot saved, changed or deleted: keyed by the bot's event id, so a
            # retried delivery is dropped.
            payload = {k: event[k] for k in ("type", "version", "deadline") if k in event}
            event_id = accept(state.db, state.queue, student["id"], "bot",
                              str(event["event_id"]), payload)
            background.add_task(state.work)
            return {"ok": True, "duplicate": event_id is None}
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
                           "token": r["token"]} for r in db.pending(sid) if live(r["token"])],
            "calendar": [dict(r) for r in db.calendar(sid)],
            "reminders": notify.list_reminders(db, sid),
            "classes_today": tools.timetable_today(db, sid)["classes"],
            "mail": mail.status(db, sid),
            "audit": [dict(r) for r in db.audit_log(sid)][:12],
        }

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
                "push": {"wakeups": getattr(state.sender, "wake", None) is not None},
                "google": google.status(state.db, sid),
                "voice": {"assistant": voice.configured(),
                          "briefing_audio": briefing.voice_configured()}}

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

    # --- the morning briefing (in the app only, never a notification) -----------------------
    @api.get("/api/briefing")
    def get_briefing(authorization: str | None = Header(None)) -> dict[str, Any]:
        return briefing.build(state.db, student_from(authorization))

    @api.get("/api/briefing/audio")
    def briefing_audio(authorization: str | None = Header(None)) -> Response:
        sid = student_from(authorization)
        try:
            sound = briefing.audio(state.db, sid)
        except briefing.VoiceUnavailable as err:
            # The app says why and reads the text with the phone's own voice instead.
            raise HTTPException(503, str(err)) from err
        return Response(sound, media_type="audio/mpeg",
                        headers={"Cache-Control": "private, max-age=600"})

    # --- Google: one sign-in on the server (Gmail read-only, Calendar, Classroom) --------------
    @api.post("/api/google/start")
    def google_start(request: Request, authorization: str | None = Header(None)) -> dict[str, Any]:
        """Google's consent page for this student. The app opens it in the browser; nothing
        about the student is in the address (the state is a one-time code)."""
        from .cloud import origin_of

        sid = student_from(authorization)
        try:
            return google.start(state.db, sid, origin_of(request.scope))
        except google.GoogleUnavailable as err:
            raise HTTPException(503, str(err)) from err

    @api.get("/api/google/callback")
    def google_callback(request: Request) -> HTMLResponse:
        # No token here: Google sends the browser back; the one-time state names the student.
        query = request.query_params
        try:
            if query.get("error"):
                raise google.GoogleUnavailable("You didn't allow access at Google. Nothing was "
                                               "connected.")
            sid = google.finish(state.db, query.get("code"), query.get("state"))
        except google.GoogleUnavailable as err:
            return HTMLResponse(_page("Not connected", str(err)), status_code=400)
        mail.sync_cards(state.db, sid)  # invented demo mail leaves the Inbox at once
        state.db.audit(sid, "google_connect", "allow", "student", clock.iso(clock.now()))
        return HTMLResponse(_page("Connected", "Google is connected to 7even5ive. Go back to "
                                  "the app: your college mail is checked at 1 PM and 9 PM, or "
                                  "tap Check now."))

    @api.post("/api/google/disconnect")
    def google_disconnect(authorization: str | None = Header(None)) -> dict[str, Any]:
        sid = student_from(authorization)
        removed = google.disconnect(state.db, sid)
        state.db.audit(sid, "google_disconnect", "allow", "student", clock.iso(clock.now()))
        return {"disconnected": removed, "google": google.status(state.db, sid)}

    # --- college mail ---------------------------------------------------------------------------
    @api.get("/api/mail")
    def mail_status(authorization: str | None = Header(None)) -> dict[str, Any]:
        return mail.status(state.db, student_from(authorization))

    @api.post("/api/mail/check")
    def mail_check(authorization: str | None = Header(None)) -> dict[str, Any]:
        """The Inbox's "Check now": refused within 5 minutes of the last check."""
        sid = student_from(authorization)
        try:
            out = mail.check(state.db, sid, "check_now", budget_seconds=20)
        except mail.MailUnavailable as err:
            raise HTTPException(err.status, str(err)) from err
        state.db.audit(sid, "check_mail_now", "allow", "student", clock.iso(clock.now()))
        return out | {"mail": mail.status(state.db, sid)}

    # --- the voice assistant ----------------------------------------------------------------
    @api.get("/api/voice/session")
    def voice_session(authorization: str | None = Header(None)) -> dict[str, Any]:
        """A signed address for one conversation with the assistant. Its tools run on the phone,
        through /api/tools like any tap, so the gateway decides what each may do."""
        sid = student_from(authorization)
        try:
            out = voice.session(state.db, sid)
        except voice.VoiceUnavailable as err:
            raise HTTPException(503, str(err)) from err
        if out.get("available"):
            state.db.audit(sid, "voice_session", "allow", "student", clock.iso(clock.now()))
        return out

    @api.get("/api/health")
    def health() -> dict[str, Any]:
        # No token: the phone app scans its Wi-Fi for this to find the laptop by itself.
        # Says only what this is; nothing about any student.
        return {"service": "7even5ive", "version": 1}

    @api.get("/")
    def index() -> FileResponse:
        return FileResponse(WEB / "index.html")

    return api


def _page(title: str, message: str) -> str:
    """The small page the browser shows after Google's sign-in. Text only, escaped."""
    from html import escape

    return ("<!doctype html><html lang='en'><head><meta charset='utf-8'><meta name='viewport' "
            "content='width=device-width, initial-scale=1'><title>7even5ive</title><style>"
            "body{font:17px/1.5 system-ui,sans-serif;background:#F4F1EA;color:#0B0C10;"
            "display:grid;place-items:center;min-height:90vh;margin:0;padding:16px}"
            "main{max-width:420px}h1{color:#FF8A1F;font-size:28px;margin:0 0 8px}</style></head>"
            f"<body><main><h1>{escape(title)}</h1><p>{escape(message)}</p></main></body></html>")
