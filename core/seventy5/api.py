"""HTTP API: the bot's webhook, the phone's cards, and Approve.

Why FastAPI here: the same routes run under uvicorn locally and behind API Gateway on
AWS (via an ASGI adapter), so the demo and the deployment share one code path.
Not: a WebSocket for live cards -- the page polls every few seconds; WebSocket
connection-minutes cost money and the demo does not need them.
"""

from __future__ import annotations

import json
import time
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, AsyncIterator

from fastapi import BackgroundTasks, FastAPI, Header, HTTPException, Request
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, Response

from . import accounts, auth, briefing, calls, clock, google, mail, notify, tools, voice
from .app import App, build
from .config import settings
from .gateway import Denied, read_token
from .ingress import BadSignature, accept, verify
from .scheduler import Scheduler


class ApiError(Exception):
    """An answer the app acts on: detail is said to the student, code tells the app what to do
    (session_expired, profile_required, username_taken, demo_account, ...)."""

    def __init__(self, status: int, detail: str, code: str) -> None:
        super().__init__(detail)
        self.status, self.detail, self.code = status, detail, code


# Anyone may call these two; each address gets this many per 5 minutes.
_username_checks = auth.Limiter(60, 300)
_login_by_ip = auth.Limiter(10, 300)
_login_by_name = auth.Limiter(10, 900)

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

    @api.exception_handler(ApiError)
    async def api_error(_: Request, err: ApiError) -> JSONResponse:
        return JSONResponse({"detail": err.detail, "code": err.code}, status_code=err.status)

    def bearer(header: str | None) -> str:
        return (header or "").removeprefix("Bearer ").strip()

    def student_from(authorization: str | None) -> int:
        # A Supabase access token (the app), or the demo's token (Try the demo).
        try:
            return state.gateway.authenticate(bearer(authorization))
        except Denied as err:
            raise ApiError(err.status, str(err), err.code) from err

    def account_from(authorization: str | None) -> tuple[Any, int | None]:
        """For /api/me: (Supabase identity or None, student id or None). A signed-in student
        with no profile yet gets (identity, None); the demo gets (None, its id)."""
        try:
            identity, row = state.gateway.identify(bearer(authorization))
        except Denied as err:
            raise ApiError(err.status, str(err), err.code) from err
        if identity is None and row is not None and row["auth_user_id"]:
            raise ApiError(401, "This token is for MCP clients. Sign in to the app instead.",
                           "unauthorized")
        return identity, (int(row["id"]) if row is not None else None)

    def refusal(err: accounts.AccountError) -> ApiError:
        return ApiError(err.status, err.detail, err.code)

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
        sender = str(event.get("from", ""))
        if accounts.LINK_CODE.match(str(event.get("text") or "")):
            # "LINK 75-XXXXXX": this number becomes the student's who made the code. The
            # signature above proves the bot saw it come from this number. Never filed.
            linked = accounts.link_from_bot(state.db, str(event.get("text")), sender)
            return {"ok": True, "linked": linked is not None,
                    "reply": "Linked to 7even5ive. Forward your class messages here."
                    if linked is not None else
                    "That code didn't work: it may have expired. Make a new one in the app."}
        student = state.db.student_by_phone(sender)
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
            # Tokens, the sign-in's id and the phone number stay on the server.
            "student": {k: v for k, v in dict(db.student(sid)).items()
                        if k not in ("token_hash", "auth_user_id", "token_created_at")}
            | {"mcp_token": None, "wa_phone": None},
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
            accounts.refuse_demo(state.db, sid, "connect Google (it is shared by everyone "
                                                "trying the app)")
        except accounts.AccountError as err:
            raise refusal(err) from err
        try:
            return google.start(state.db, sid, origin_of(request.scope))
        except google.GoogleUnavailable as err:
            raise HTTPException(503, str(err)) from err

    @api.get("/api/google/callback")
    def google_callback(request: Request) -> HTMLResponse:
        """Google sends the browser back here. Nothing is exchanged yet: the page hands the code
        to the app, which finishes the sign-in with the student's own token."""
        query = request.query_params
        if query.get("error"):
            return HTMLResponse(_page("Not connected", "You didn't allow access at Google. "
                                      "Nothing was connected."), status_code=400)
        code, given = query.get("code"), query.get("state")
        if not code or not google.pending(state.db, given):
            return HTMLResponse(_page("Not connected", "This sign-in link was already used or "
                                      "has expired. Start again in the app."), status_code=400)
        return HTMLResponse(_handoff(code, str(given)))

    @api.post("/api/google/finish")
    def google_finish(body: dict[str, Any], authorization: str | None = Header(None)) -> dict[str, Any]:
        """The app, signed in as the student who started the sign-in, hands back Google's code."""
        sid = student_from(authorization)
        try:
            accounts.refuse_demo(state.db, sid, "connect Google")
        except accounts.AccountError as err:
            raise refusal(err) from err
        try:
            google.finish(state.db, str(body.get("code") or ""), str(body.get("state") or ""), sid)
        except google.GoogleUnavailable as err:
            raise HTTPException(409, str(err)) from err
        mail.sync_cards(state.db, sid)  # invented demo mail leaves the Inbox at once
        state.db.audit(sid, "google_connect", "allow", "student", clock.iso(clock.now()))
        return {"connected": True, "google": google.status(state.db, sid)}

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
            out = mail.check(state.db, sid, "check_now",
                             deadline=time.monotonic() + mail.CHECK_NOW_SECONDS)
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

    # --- accounts (accounts.py; the sign-in itself is Supabase's, auth.py) --------------------
    @api.get("/api/auth/config")
    def auth_config() -> dict[str, Any]:
        """What the app needs to sign in with Supabase. Nothing secret: the publishable key is
        made to ship in apps; Supabase's row level security keeps it out of every table."""
        on = auth.configured()
        return {"enabled": on,
                "supabase_url": settings.supabase_url if on else None,
                "publishable_key": settings.supabase_publishable_key if on else None,
                # Signing in with a username needs this service to look up the email.
                "username_login": on,
                "delete_account": auth.can_delete_users(),
                "password_min_length": 8,
                "demo": True}

    @api.get("/api/auth/username")
    def username_available(request: Request, u: str = "") -> dict[str, Any]:
        if not _username_checks.allow(request.client.host if request.client else "?"):
            raise ApiError(429, "Too many checks. Wait a minute.", "rate_limited")
        return accounts.username_check(state.db, u)

    @api.post("/api/auth/login")
    def login_by_username(body: dict[str, Any], request: Request) -> Response:
        """Sign in with a username instead of an email: this service finds the email and asks
        Supabase, answering with Supabase's own session. Same answer for an unknown username
        and a wrong password, so this can't be used to find out who has an account."""
        if not auth.configured():
            raise ApiError(503, "Sign-in isn't set up on this server.", "auth_unavailable")
        login = str(body.get("login") or "").strip().lower()
        password = str(body.get("password") or "")
        ip = request.client.host if request.client else "?"
        if not _login_by_ip.allow(ip) or not _login_by_name.allow(login):
            raise ApiError(429, "Too many tries. Wait a few minutes and try again.",
                           "rate_limited")
        wrong = ApiError(400, "Wrong username or password.", "invalid_credentials")
        row = state.db.student_by_username(login) if login and "@" not in login else None
        if row is None or not row["email"] or not password:
            raise wrong
        try:
            reply = auth.password_login(str(row["email"]), password, ip)
        except auth.AuthError as err:
            raise ApiError(err.status, str(err), err.code) from err
        if reply.status_code == 200:
            return Response(reply.content, media_type="application/json")
        try:
            code = str(reply.json().get("error_code") or "")
        except ValueError:
            code = ""
        if code == "email_not_confirmed":
            raise ApiError(400, "Confirm your email first: log in with your email address to "
                                "get a new code.", "email_not_confirmed")
        if reply.status_code == 429:
            raise ApiError(429, "Too many tries. Wait a few minutes and try again.",
                           "rate_limited")
        if reply.status_code >= 500:
            raise ApiError(503, "The sign-in service isn't answering. Try again.",
                           "auth_unavailable")
        raise wrong

    @api.get("/api/me")
    def get_me(authorization: str | None = Header(None)) -> dict[str, Any]:
        identity, sid = account_from(authorization)
        return accounts.me(state.db, sid, identity.email if identity else None)

    @api.post("/api/me")
    def save_me(body: dict[str, Any], authorization: str | None = Header(None)) -> dict[str, Any]:
        """The profile: made on first save (after sign-up), changed after."""
        identity, sid = account_from(authorization)
        if identity is None:
            raise ApiError(403, "The demo account can't be changed. Create your own account.",
                           "demo_account")
        try:
            sid = accounts.save_profile(state.db, identity.user_id, identity.email, body)
        except accounts.AccountError as err:
            raise refusal(err) from err
        return accounts.me(state.db, sid, identity.email)

    @api.post("/api/me/delete")
    def delete_me(body: dict[str, Any], authorization: str | None = Header(None)) -> dict[str, Any]:
        """Deletes the account: every row, the mail read, the portal answers, Google revoked,
        then the login itself. The app asks twice before calling this."""
        identity, sid = account_from(authorization)
        if identity is None:
            raise ApiError(403, "The demo account can't be deleted.", "demo_account")
        if body.get("confirm") != "DELETE":
            raise ApiError(400, "Confirm with DELETE.", "invalid")
        if not auth.can_delete_users():
            raise ApiError(503, "Deleting accounts isn't set up on this server yet. Nothing was"
                                " deleted.", "auth_unavailable")
        if sid is not None:
            try:
                accounts.delete_everything(state.db, sid)
            except accounts.AccountError as err:
                raise refusal(err) from err
        try:
            auth.delete_user(identity.user_id)
        except auth.AuthError as err:
            raise ApiError(err.status, "Your data is deleted, but your login couldn't be removed"
                                       " right now. Try again.", err.code) from err
        return {"deleted": True}

    @api.post("/api/me/token")
    def make_token(request: Request, authorization: str | None = Header(None)) -> dict[str, Any]:
        """A personal token for an MCP client (Claude, ChatGPT), shown once. A new one replaces
        the old. It reaches the same gateway tools as the app, and nothing else."""
        from .cloud import origin_of

        identity, sid = account_from(authorization)
        if sid is None:
            raise ApiError(403, "Finish setting up your account first.", "profile_required")
        try:
            out = accounts.new_token(state.db, sid)
        except accounts.AccountError as err:
            raise refusal(err) from err
        base = settings.public_url or origin_of(request.scope) or ""
        return out | {"mcp_url": f"{base}/mcp"}

    @api.post("/api/me/token/delete")
    def delete_token(authorization: str | None = Header(None)) -> dict[str, Any]:
        _, sid = account_from(authorization)
        if sid is None:
            raise ApiError(403, "Finish setting up your account first.", "profile_required")
        try:
            accounts.drop_token(state.db, sid)
        except accounts.AccountError as err:
            raise refusal(err) from err
        return {"deleted": True}

    @api.post("/api/me/whatsapp")
    def link_whatsapp(authorization: str | None = Header(None)) -> dict[str, Any]:
        _, sid = account_from(authorization)
        if sid is None:
            raise ApiError(403, "Finish setting up your account first.", "profile_required")
        try:
            return accounts.start_whatsapp(state.db, sid)
        except accounts.AccountError as err:
            raise refusal(err) from err

    @api.post("/api/me/whatsapp/delete")
    def unlink_whatsapp(authorization: str | None = Header(None)) -> dict[str, Any]:
        _, sid = account_from(authorization)
        if sid is None:
            raise ApiError(403, "Finish setting up your account first.", "profile_required")
        try:
            accounts.unlink_whatsapp(state.db, sid)
        except accounts.AccountError as err:
            raise refusal(err) from err
        return accounts.me(state.db, sid)

    @api.get("/api/health")
    def health() -> dict[str, Any]:
        # No token: the phone app scans its Wi-Fi for this to find the laptop by itself.
        # Says only what this is; nothing about any student.
        return {"service": "7even5ive", "version": 1}

    @api.get("/")
    def index() -> FileResponse:
        return FileResponse(WEB / "index.html")

    return api


_STYLE = ("body{font:17px/1.5 system-ui,sans-serif;background:#F4F1EA;color:#0B0C10;"
          "display:grid;place-items:center;min-height:90vh;margin:0;padding:16px}"
          "main{max-width:420px}h1{color:#FF8A1F;font-size:28px;margin:0 0 8px}"
          "a.go{display:inline-block;margin-top:12px;padding:12px 20px;border-radius:999px;"
          "background:#FF8A1F;color:#fff;text-decoration:none;font-weight:600}")


def _page(title: str, message: str, extra: str = "") -> str:
    """The small page the browser shows around Google's sign-in. Text only, escaped."""
    from html import escape

    return ("<!doctype html><html lang='en'><head><meta charset='utf-8'><meta name='viewport' "
            f"content='width=device-width, initial-scale=1'><title>7even5ive</title><style>{_STYLE}"
            f"</style></head><body><main><h1>{escape(title)}</h1><p>{escape(message)}</p>{extra}"
            "</main></body></html>")


def _handoff(code: str, given: str) -> str:
    """Back to the app with Google's code: Chrome's intent link (a tap), tried at once too."""
    from html import escape
    from urllib.parse import urlencode

    query = urlencode({"code": code, "state": given})
    intent = f"intent://google?{query}#Intent;scheme=sevenfive;package=com.sevenfive.app;end"
    plain = f"sevenfive://google?{query}"
    extra = (f"<a class='go' id='go' href='{escape(intent, quote=True)}'>Back to 7even5ive</a>"
             f"<p><small>Not opening? <a href='{escape(plain, quote=True)}'>Try this link</a>."
             "</small></p><script>setTimeout(function(){location.href="
             "document.getElementById('go').href;},300);</script>")
    return _page("Almost done", "Go back to 7even5ive to finish connecting Google.", extra)
