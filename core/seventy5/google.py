"""Google, connected once on the server: Gmail read-only, Calendar events, Classroom read.

The sign-in (decision P6), with no student token in any URL:
1. The app calls POST /api/google/start with its own token. We make a one-time code, Google's
   `state`, bound to this student, with a PKCE verifier and ten minutes to live, and answer
   with Google's consent page address.
2. The app opens that page in the phone's browser; the student signs in at Google and agrees.
3. Google sends the browser to GET /api/google/callback?code=...&state=.... We spend the state
   (once), swap the code (with the verifier and our client secret) for a refresh token, encrypt
   it and store it. The page says to go back to the app.
The phone never holds a Google token. The student may untick a permission at Google; each
feature checks the scope it needs and says what is missing.

At rest: the refresh token is encrypted with TOKEN_ENCRYPTION_KEY (Fernet). Unset in development:
a fixed key is used and the startup report says so. Disconnect revokes at Google, then deletes.
What each scope is for: Gmail read-only feeds the mail filter (mail.py); Calendar writes the one
event a student approves (add_to_calendar); Classroom brings coursework with its own due date
into the cascade (decision 29). Google's verification is needed before real students (decision
54); the demo runs in Testing mode, where a sign-in lasts 7 days.
"""

from __future__ import annotations

import base64
import hashlib
import json
import logging
import secrets
import threading
import time
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any
from urllib.parse import urlencode

import httpx
from mailfilter.errors import GmailUnavailable, NeedsReconnect, NotConnected

from . import clock
from .config import settings
from .db import Database

log = logging.getLogger(__name__)

AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
TOKEN_URL = "https://oauth2.googleapis.com/token"
REVOKE_URL = "https://oauth2.googleapis.com/revoke"
CALENDAR = "https://www.googleapis.com/calendar/v3/calendars/primary/events"
CLASSROOM = "https://classroom.googleapis.com/v1"

GMAIL_SCOPE = "https://www.googleapis.com/auth/gmail.readonly"
CALENDAR_SCOPE = "https://www.googleapis.com/auth/calendar.events"
COURSES_SCOPE = "https://www.googleapis.com/auth/classroom.courses.readonly"
COURSEWORK_SCOPE = "https://www.googleapis.com/auth/classroom.coursework.me.readonly"
SCOPES = ("openid", "email", GMAIL_SCOPE, CALENDAR_SCOPE, COURSES_SCOPE, COURSEWORK_SCOPE)
CODE_MINUTES = 10
EARLY = 60.0  # refresh an access token this long before it expires
# Development only: a fixed key, so a laptop restart can still read what it stored.
DEV_KEY = base64.urlsafe_b64encode(hashlib.sha256(b"7even5ive-dev-only").digest())


class GoogleUnavailable(RuntimeError):
    """Said to the student as it is (the sign-in page or the app shows it)."""


def _http() -> httpx.Client:
    """Every call to Google goes through one of these (tests swap it for a fake Google)."""
    return httpx.Client(timeout=15.0)


# --- encryption at rest -----------------------------------------------------------------------
def _fernet() -> Any:
    from cryptography.fernet import Fernet

    raw = settings.token_encryption_key.strip()
    if not raw:
        return Fernet(DEV_KEY)
    try:
        return Fernet(raw.encode())
    except ValueError:
        # Any long random string works: it is stretched into a Fernet key.
        return Fernet(base64.urlsafe_b64encode(hashlib.sha256(raw.encode()).digest()))


def seal(token: str) -> str:
    return str(_fernet().encrypt(token.encode()).decode())


def unseal(sealed: str) -> str:
    from cryptography.fernet import InvalidToken

    try:
        return str(_fernet().decrypt(sealed.encode()).decode())
    except InvalidToken as err:
        # The key changed: the stored grant is unreadable, so the student signs in again.
        raise NeedsReconnect("token_unreadable") from err


# --- the sign-in --------------------------------------------------------------------------------
def configured() -> bool:
    return bool(settings.google_client_id and settings.google_client_secret)


def redirect_uri(origin: str | None) -> str:
    base = settings.public_url or (origin or "").rstrip("/")
    if not base:
        raise GoogleUnavailable("This server doesn't know its own address: set PUBLIC_URL.")
    return f"{base}/api/google/callback"


def _pkce() -> tuple[str, str]:
    verifier = secrets.token_urlsafe(64)[:96]
    challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest())
    return verifier, challenge.decode().rstrip("=")


def start(db: Database, sid: int, origin: str | None) -> dict[str, Any]:
    """Google's consent page for this student, with a one-time state."""
    if not configured():
        raise GoogleUnavailable("Google sign-in isn't set up on this server yet "
                                "(GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET).")
    back = redirect_uri(origin)
    code = secrets.token_urlsafe(32)
    verifier, challenge = _pkce()
    expires = clock.iso(clock.now() + timedelta(minutes=CODE_MINUTES))
    db.add_connect_code(code, sid, verifier, back, expires)
    query = urlencode({
        "client_id": settings.google_client_id, "redirect_uri": back, "response_type": "code",
        "scope": " ".join(SCOPES), "state": code, "code_challenge": challenge,
        "code_challenge_method": "S256", "access_type": "offline",
        # Always ask, so Google always returns a refresh token, even on a second sign-in.
        "prompt": "consent", "include_granted_scopes": "true",
    })
    return {"url": f"{AUTH_URL}?{query}", "expires_at": expires}


def _email_from(id_token: str | None) -> str | None:
    """The address in the ID token Google just sent us over TLS (no signature check needed:
    it came straight from Google's token endpoint, not from the browser)."""
    if not id_token or id_token.count(".") != 2:
        return None
    payload = id_token.split(".")[1]
    try:
        claims = json.loads(base64.urlsafe_b64decode(payload + "=" * (-len(payload) % 4)))
    except ValueError:
        return None
    email = claims.get("email")
    return str(email) if isinstance(email, str) else None


def finish(db: Database, code: str | None, state: str | None,
           http: httpx.Client | None = None) -> int:
    """Google sent the browser back. Returns the student id; raises with a reason to show."""
    if not code or not state:
        raise GoogleUnavailable("Google didn't finish the sign-in. Start again in the app.")
    row = db.take_connect_code(state, clock.iso(clock.now()))
    if row is None:
        raise GoogleUnavailable("This sign-in link was already used or has expired. "
                                "Start again in the app.")
    client = http or _http()
    try:
        resp = client.post(TOKEN_URL, data={
            "client_id": settings.google_client_id, "client_secret": settings.google_client_secret,
            "code": code, "code_verifier": row["verifier"], "grant_type": "authorization_code",
            "redirect_uri": row["redirect_uri"]})
    except httpx.HTTPError as err:
        raise GoogleUnavailable("Google can't be reached right now. Try again.") from err
    if resp.status_code != 200:
        log.warning("google code exchange refused", extra={"status": resp.status_code})
        raise GoogleUnavailable("Google refused the sign-in. Start again in the app.")
    body = resp.json()
    refresh = body.get("refresh_token")
    if not isinstance(refresh, str) or not refresh:
        raise GoogleUnavailable("Google didn't grant lasting access. Start again in the app.")
    sid = int(row["student_id"])
    db.save_google(sid, _email_from(body.get("id_token")), str(body.get("scope") or ""),
                   seal(refresh), clock.iso(clock.now()))
    _tokens.drop(sid)
    log.info("google connected", extra={"student": sid})
    return sid


def account(db: Database, sid: int) -> Any | None:
    return db.google_account(sid)


def _scopes(db: Database, sid: int) -> set[str]:
    row = db.google_account(sid)
    return set(str(row["scopes"]).split()) if row is not None else set()


def has_gmail(db: Database, sid: int) -> bool:
    return GMAIL_SCOPE in _scopes(db, sid)


def has_calendar(db: Database, sid: int) -> bool:
    return CALENDAR_SCOPE in _scopes(db, sid)


def has_classroom(db: Database, sid: int) -> bool:
    return {COURSES_SCOPE, COURSEWORK_SCOPE} <= _scopes(db, sid)


def account_email(db: Database, sid: int) -> str | None:
    row = db.google_account(sid)
    return row["email"] if row is not None else None


def status(db: Database, sid: int) -> dict[str, Any]:
    row = db.google_account(sid)
    scopes = set(str(row["scopes"]).split()) if row is not None else set()
    return {
        "configured": configured(),
        "connected": row is not None,
        "email": row["email"] if row is not None else None,
        "connected_at": row["connected_at"] if row is not None else None,
        "gmail": GMAIL_SCOPE in scopes,
        "calendar": CALENDAR_SCOPE in scopes,
        "classroom": {COURSES_SCOPE, COURSEWORK_SCOPE} <= scopes,
    }


def disconnect(db: Database, sid: int, http: httpx.Client | None = None) -> bool:
    """Revoke at Google (best effort), then forget the grant and everything read with it."""
    row = db.google_account(sid)
    if row is None:
        return False
    client = http or _http()
    try:
        client.post(REVOKE_URL, data={"token": unseal(row["refresh_token"])},
                    headers={"Content-Type": "application/x-www-form-urlencoded"})
    except (httpx.HTTPError, NeedsReconnect):
        log.warning("google revoke failed; deleting anyway", extra={"student": sid})
    db.delete_google(sid)
    _tokens.drop(sid)
    from . import mail

    mail.forget(db, sid)
    return True


# --- access tokens --------------------------------------------------------------------------------
@dataclass
class _Cached:
    token: str
    expires_at: float


class _Tokens:
    """Access tokens from each student's refresh token, cached until shortly before expiry."""

    def __init__(self) -> None:
        self._cache: dict[int, _Cached] = {}
        self._lock = threading.Lock()

    def drop(self, sid: int) -> None:
        with self._lock:
            self._cache.pop(sid, None)

    def get(self, db: Database, sid: int, fresh: bool = False,
            http: httpx.Client | None = None) -> str:
        with self._lock:
            cached = self._cache.get(sid)
        if cached and not fresh and cached.expires_at - EARLY > time.time():
            return cached.token
        row = db.google_account(sid)
        if row is None:
            raise NotConnected("no_google_account")
        client = http or _http()
        try:
            resp = client.post(TOKEN_URL, data={
                "client_id": settings.google_client_id,
                "client_secret": settings.google_client_secret,
                "refresh_token": unseal(row["refresh_token"]), "grant_type": "refresh_token"})
        except httpx.HTTPError:
            raise GmailUnavailable("token_network") from None
        if resp.status_code >= 500:
            raise GmailUnavailable(f"token_http_{resp.status_code}")
        if resp.status_code != 200:
            error = ""
            try:
                error = str(resp.json().get("error", ""))
            except ValueError:
                pass
            if error == "invalid_grant":  # revoked at Google, or a Testing-mode week passed
                raise NeedsReconnect("invalid_grant")
            raise GmailUnavailable(error or f"token_http_{resp.status_code}")
        body = resp.json()
        token = str(body["access_token"])
        with self._lock:
            self._cache[sid] = _Cached(token, time.time() + float(body.get("expires_in", 3600)))
        return token


_tokens = _Tokens()


def access_token(db: Database, sid: int, fresh: bool = False,
                 http: httpx.Client | None = None) -> str:
    return _tokens.get(db, sid, fresh, http)


def gmail_mailbox(db: Database, sid: int) -> Any:
    from mailfilter.gmail import GmailMailbox

    from .mail import mail_settings

    return GmailMailbox(lambda fresh: access_token(db, sid, fresh), _http(),
                        mail_settings().max_text_chars)


def _authorized(db: Database, sid: int, http: httpx.Client, method: str, url: str,
                **kwargs: Any) -> httpx.Response:
    """One Google API call with the student's access token, retried once on a stale token."""
    for fresh in (False, True):
        token = access_token(db, sid, fresh, http)
        resp = http.request(method, url, headers={"Authorization": f"Bearer {token}"}, **kwargs)
        if resp.status_code != 401:
            return resp
    return resp


# --- Calendar: the one write, after the student's tap -------------------------------------------
def calendar_upsert(db: Database, sid: int, key: str, title: str, starts_at: str,
                    http: httpx.Client | None = None) -> dict[str, Any]:
    """Writes the event with our fixed id; a retry (409: the id exists) rewrites the same event."""
    client = http or _http()
    start_at = datetime.fromisoformat(starts_at)
    event = {
        "id": key, "summary": title,
        "description": "Added by 7even5ive after you tapped Approve.",
        "start": {"dateTime": start_at.isoformat(), "timeZone": settings.timezone},
        "end": {"dateTime": (start_at + timedelta(minutes=30)).isoformat(),
                "timeZone": settings.timezone},
        "reminders": {"useDefault": True},
    }
    resp = _authorized(db, sid, client, "POST", CALENDAR, json=event)
    if resp.status_code == 409:
        resp = _authorized(db, sid, client, "PUT", f"{CALENDAR}/{key}", json=event)
    if resp.status_code not in (200, 201):
        log.warning("calendar write refused", extra={"status": resp.status_code})
        raise GoogleUnavailable("Google Calendar refused the event.")
    return {"google_event": key, "link": resp.json().get("htmlLink")}


# --- Classroom: coursework with its own due date -------------------------------------------------
def _due(work: dict[str, Any]) -> datetime | None:
    """Classroom's due date and time, both UTC. Google leaves out fields that are zero, so
    dueTime {} is midnight UTC; with no dueTime at all, the day's end is used."""
    day = work.get("dueDate") or {}
    if not {"year", "month", "day"} <= set(day):
        return None
    if "dueTime" in work:
        at = work.get("dueTime") or {}
        hour, minute = int(at.get("hours", 0)), int(at.get("minutes", 0))
    else:
        hour, minute = 23, 59
    return datetime(int(day["year"]), int(day["month"]), int(day["day"]), hour, minute,
                    tzinfo=timezone.utc)


def coursework(db: Database, sid: int, http: httpx.Client | None = None) -> list[dict[str, Any]]:
    """Published coursework with a due date still ahead, from the student's active courses."""
    client = http or _http()
    now = clock.now()
    courses = _authorized(db, sid, client, "GET", f"{CLASSROOM}/courses",
                          params={"studentId": "me", "courseStates": "ACTIVE", "pageSize": 50})
    if courses.status_code != 200:
        raise GoogleUnavailable(f"Classroom refused the course list ({courses.status_code}).")
    found = []
    for course in courses.json().get("courses", []):
        works = _authorized(db, sid, client, "GET",
                            f"{CLASSROOM}/courses/{course['id']}/courseWork",
                            params={"courseWorkStates": "PUBLISHED", "orderBy": "dueDate desc",
                                    "pageSize": 30})
        if works.status_code != 200:
            log.info("classroom course skipped", extra={"status": works.status_code})
            continue
        for work in works.json().get("courseWork", []):
            due = _due(work)
            if due is None or due <= now:
                continue
            found.append({"id": str(work["id"]), "course": str(course.get("name") or ""),
                          "title": str(work.get("title") or "Untitled"), "due_at": clock.iso(due),
                          "link": work.get("alternateLink")})
    return found


def classroom_sync(app: Any, sid: int, http: httpx.Client | None = None) -> int:
    """Coursework into cards. A new piece goes through the cascade (Jev or the LLM names the
    subject); Classroom's own due date always wins. A moved due date moves the card and its
    reminders. Returns how many pieces were new."""
    db = app.db
    if not (settings.classroom_enabled and has_classroom(db, sid)):
        return 0
    from .ingress import accept

    new = 0
    for work in coursework(db, sid, http):
        external = f"classroom:{work['id']}"
        item = db.item_by_external(sid, external)
        if item is not None:
            if item["due_at"] != work["due_at"]:
                db.move_item_due(sid, item["id"], work["due_at"], clock.iso(clock.now()))
            continue
        due_text = datetime.fromisoformat(work["due_at"]).strftime("%A %d %B %Y %I:%M %p")
        payload = {"text": f"{work['course']}: {work['title']} (due {due_text})",
                   "classroom": {"title": work["title"], "due_at": work["due_at"]}}
        event_id = accept(db, app.queue, sid, "classroom", external, payload)
        if event_id is None:
            continue
        outcomes = app.work()
        filed = next((o for o in outcomes if o.item_id is not None), None)
        if filed is not None and filed.status == "filed":
            db.update_item(sid, filed.item_id, external_id=external)
            db.move_item_due(sid, filed.item_id, work["due_at"], clock.iso(clock.now()))
            new += 1
    return new
