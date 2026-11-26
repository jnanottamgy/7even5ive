"""Google, connected once on the server: Gmail read-only, Calendar events, Classroom read.

The sign-in (decision P6), with no student token in any URL:
1. The app calls POST /api/google/start with its own token. We make a one-time code, Google's
   `state`, bound to this student, with a PKCE verifier and ten minutes to live, and answer
   with Google's consent page address.
2. The app opens that page in the phone's browser; the student signs in at Google and agrees.
3. Google sends the browser to GET /api/google/callback?code=...&state=.... That page only hands
   the code back to the app (sevenfive://google?...).
4. The app posts it to POST /api/google/finish with its own token. Only now do we spend the
   state (once, and only for the student who started it), swap the code (with the verifier and
   our client secret) for a refresh token, encrypt it and store it.
Why the app finishes it: a consent link forwarded to someone else would otherwise attach their
Google account to the student who started it. Their browser can't hand the code to an app
signed in as that student. The phone never holds a Google token either way. The student may
untick a permission at Google; each feature checks the scope it needs and says what is missing.

At rest: the refresh token is encrypted with TOKEN_ENCRYPTION_KEY (Fernet). Unset in development:
a fixed key is used and the startup report says so. Disconnect revokes at Google, then deletes.
What each scope is for: Gmail read-only feeds the mail filter (mail.py); Calendar writes the one
event a student approves (add_to_calendar); Classroom brings coursework with its own due date
into the cascade (decision 29). Google's verification is needed before real students (decision
54); the demo runs in Testing mode, where a sign-in lasts 7 days.

When Google refuses the grant for good (invalid_grant: revoked, or the Testing-mode week passed)
the account is marked: status says needs_reconnect (the app says "Reconnect Google"), Gmail,
Classroom and Calendar wait without asking Google again, and the student is told once, in the
outbox. Signing in again clears it. A grant this server cannot decrypt (its key changed) is not
marked: that is the server's fault, and fixing the key brings every account back.
Classroom has its own job (app.sync_classroom): every connected student once per mail slot,
least recently read first, over as many ticks as it takes.
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
from mailfilter.config import parse_times
from mailfilter.errors import GmailUnavailable, NeedsReconnect, NotConnected

from . import clock
from .config import settings
from .db import Database
from .scheduler import latest_slot

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
# Classroom only starts a new piece of coursework (it may need the LLM) with this much time left.
CLASSROOM_RESERVE = 15.0
# A Classroom read that failed (Google down, a refused course list) is tried again this much later
# in the same slot; one cut short by the tick's budget goes on at the next tick.
CLASSROOM_RETRY_AFTER = timedelta(minutes=10)
# Said once in the outbox when Google refuses a student's grant for good.
RECONNECT_TITLE = "Reconnect Google"
RECONNECT_BODY = ("Google stopped letting 7even5ive read your college mail and Classroom. "
                  "Open Settings and connect Google again.")
# Development only: a fixed key, so a laptop restart can still read what it stored.
DEV_KEY = base64.urlsafe_b64encode(hashlib.sha256(b"7even5ive-dev-only").digest())


class GoogleUnavailable(RuntimeError):
    """Said to the student as it is (the sign-in page or the app shows it)."""


class ClassroomRefused(GoogleUnavailable):
    """Classroom answered, and refused (a 4xx other than 429): the college's admin, or an
    account without Classroom. Asked again at the next slot, not minutes later."""


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


def pending(db: Database, state: str | None) -> bool:
    """Whether this state is a sign-in still waiting to be finished (the callback page asks)."""
    return bool(state) and db.peek_connect_code(str(state), clock.iso(clock.now())) is not None


def finish(db: Database, code: str | None, state: str | None, student_id: int,
           http: httpx.Client | None = None) -> int:
    """The app hands back Google's code, with its own token. Returns the student id; raises
    with a reason to show."""
    if not code or not state:
        raise GoogleUnavailable("Google didn't finish the sign-in. Start again in the app.")
    started = db.peek_connect_code(state, clock.iso(clock.now()))
    if started is None:
        raise GoogleUnavailable("This sign-in link was already used or has expired. "
                                "Start again in the app.")
    if int(started["student_id"]) != student_id:
        # Not spent: the student who started it can still finish it.
        raise GoogleUnavailable("This sign-in was started from another account.")
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
    email = _email_from(body.get("id_token"))
    db.save_google(sid, email, str(body.get("scope") or ""), seal(refresh), clock.iso(clock.now()))
    db.google_reconnected(sid)  # a refused grant is forgotten; Classroom is read again soon
    _tokens.drop(sid)
    from . import mail

    # (Re)connect the Gmail mailbox now: a mailbox Google had cut off (a revoked grant, a
    # Testing-mode week) is checked again, and a different address starts afresh.
    mail.store().connect(mail.mailbox_key(sid, "gmail"), email, clock.now())
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


def needs_reconnect(db: Database, sid: int) -> str | None:
    """Why Google refused this student's grant, until they connect again; None while it works."""
    row = db.google_account(sid)
    if row is None or not row["needs_reconnect_at"]:
        return None
    return str(row["reconnect_reason"] or "needs_reconnect")


def status(db: Database, sid: int) -> dict[str, Any]:
    """What Settings shows. connected: an account is linked (the app shows it, and Disconnect);
    needs_reconnect: Google refused its grant, so the app says "Reconnect Google"."""
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
        "needs_reconnect": row is not None and bool(row["needs_reconnect_at"]),
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
        if row["needs_reconnect_at"]:
            # Google refused this grant already: it is not asked again until the student
            # connects again (every Gmail, Classroom and Calendar call comes through here).
            raise NeedsReconnect(str(row["reconnect_reason"] or "needs_reconnect"))
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
                _grant_lost(db, sid, str(row["refresh_token"]), error)
                raise NeedsReconnect("invalid_grant")
            raise GmailUnavailable(error or f"token_http_{resp.status_code}")
        body = resp.json()
        token = str(body["access_token"])
        with self._lock:
            self._cache[sid] = _Cached(token, time.time() + float(body.get("expires_in", 3600)))
        return token


_tokens = _Tokens()


def _grant_lost(db: Database, sid: int, sealed: str, reason: str) -> bool:
    """Google refused the student's grant (`sealed`, as stored) for good: the account is marked
    and the student told, once, in the outbox, with a wake-up for their phone. Nothing happens
    when a reconnect already replaced that grant. Returns whether this call marked it."""
    _tokens.drop(sid)
    if not db.google_grant_lost(sid, sealed, reason, clock.iso(clock.now()), RECONNECT_TITLE,
                                RECONNECT_BODY):
        return False
    log.info("google grant refused", extra={"student": sid, "reason": reason})
    try:
        from . import fcm

        account = fcm.load_account()
        if account is not None:
            fcm.FcmWaker(db, account, background=False).wake(sid)
    except Exception as err:  # noqa: BLE001 - the message is saved; the phone's next pull has it
        log.warning("wake-up failed", extra={"student": sid, "error": type(err).__name__})
    return True


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
    if (refused := needs_reconnect(db, sid)) is not None:
        raise NeedsReconnect(refused)  # Google is not asked until the student reconnects
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
        busy = courses.status_code == 429 or courses.status_code >= 500
        raise (GoogleUnavailable if busy else ClassroomRefused)(
            f"Classroom refused the course list ({courses.status_code}).")
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


def classroom_sync(app: Any, sid: int, http: httpx.Client | None = None,
                   deadline: float | None = None) -> int:
    """Coursework into cards. A new piece goes through the cascade (Jev or the LLM names the
    subject); Classroom's own due date always wins. A moved due date moves the card and its
    reminders. A piece whose card was left for review, or that never got one (skipped, or its
    run was cut off), goes through the cascade again: its card is filed in place of the one
    for review, never beside it. A piece is only started with CLASSROOM_RESERVE seconds left
    before the deadline (the rest waits for the next turn). Returns how many were filed."""
    return _classroom(app, sid, http, deadline)[0]


def _follow(db: Database, sid: int, card: Any, work: dict[str, Any]) -> None:
    if card["due_at"] != work["due_at"]:
        db.move_item_due(sid, card["id"], work["due_at"], clock.iso(clock.now()))


def _classroom(app: Any, sid: int, http: httpx.Client | None,
               deadline: float | None) -> tuple[int, bool]:
    """classroom_sync: (pieces filed, whether every piece was seen to: False when cut short)."""
    db = app.db
    if not (settings.classroom_enabled and has_classroom(db, sid)) or needs_reconnect(db, sid):
        return 0, True
    from .ingress import accept, accept_again

    new = 0
    for work in coursework(db, sid, http):
        external = f"classroom:{work['id']}"
        card = db.item_by_external(sid, external)
        if card is not None and card["status"] != "needs_review":
            _follow(db, sid, card, work)
            continue
        if deadline is not None and deadline - time.monotonic() < CLASSROOM_RESERVE:
            return new, False
        due_text = datetime.fromisoformat(work["due_at"]).strftime("%A %d %B %Y %I:%M %p")
        payload = {"text": f"{work['course']}: {work['title']} (due {due_text})",
                   "classroom": {"title": work["title"], "due_at": work["due_at"],
                                 "external_id": external}}
        event_id = accept(db, app.queue, sid, "classroom", external, payload)
        if event_id is None:
            # Seen at an earlier sync, with no filed card to show for it: run it again.
            event_id = accept_again(db, app.queue, sid, "classroom", external, payload)
            if event_id is None:
                continue
        app.work()
        # The cascade gives the card this piece's id; a card filed before it did is linked now.
        card = db.item_by_external(sid, external) or db.link_event_card(sid, event_id, external)
        if card is not None and card["status"] == "filed":
            _follow(db, sid, card, work)
            new += 1
    return new, True


def classroom_due(db: Database, now: datetime | None = None) -> list[int]:
    """Students whose Classroom has not been read completely since the latest mail slot (1 PM,
    9 PM), least recently tried first. One that failed waits CLASSROOM_RETRY_AFTER; a grant
    Google refused waits for the student to reconnect."""
    if not settings.classroom_enabled:
        return []
    now = now or clock.now()
    slot = latest_slot(now, parse_times(settings.mail_check_times))
    rows = db.classroom_due(clock.iso(slot), clock.iso(now - CLASSROOM_RETRY_AFTER))
    return [int(r["student_id"]) for r in rows
            if {COURSES_SCOPE, COURSEWORK_SCOPE} <= set(str(r["scopes"]).split())]


def classroom_turn(app: Any, sid: int, http: httpx.Client | None = None,
                   deadline: float | None = None) -> bool:
    """One student's Classroom for the background job, claimed first so two instances never
    read it in the same minute, then recorded: complete (done until the next slot), cut short
    (goes on at the next turn, behind the others), failed (Google busy or unreachable: tried
    again CLASSROOM_RETRY_AFTER later) or refused (asked again at the next slot). Never raises.
    Returns whether it is done for this slot."""
    db = app.db
    started = clock.iso(clock.now())
    if not db.claim_classroom(sid, started):
        return False
    try:
        _, complete = _classroom(app, sid, http, deadline)
    except Exception as err:  # noqa: BLE001 - logged by type only; one student never stops another
        refused = isinstance(err, ClassroomRefused)
        code = "classroom_refused" if refused else str(getattr(err, "code", "")
                                                       or type(err).__name__)[:40]
        log.warning("classroom sync failed", extra={"student": sid, "error": code})
        db.classroom_tried(sid, started, refused, code)
        return refused
    db.classroom_tried(sid, started, complete, None)
    return complete
