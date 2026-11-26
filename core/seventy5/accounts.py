"""Accounts: the profile behind a Supabase sign-in, its personal token, WhatsApp, deletion.

A student signs up in the app (auth.py: Supabase checks the email with a code), then sets up a
profile here: a unique username, their name, college, branch, year, interests and subjects.
Until then their token is good for /api/me only (403 profile_required everywhere else).

Why usernames live here and not in Supabase: they must be unique, and the unique index in this
database decides, so two students choosing the same name at once cannot both get it.
Why WhatsApp is linked by a code sent to the bot: the bot's signed webhook proves the number
belongs to whoever sent the code. A number typed into a form would let anyone claim a
classmate's number and receive their forwards (and their urgent calls).
Why personal tokens are stored hashed and shown once: a token is a password for MCP clients.
A real account's personal token works for MCP only, never for the app's own API.
The demo account is shared by everyone who taps "Try the demo": it cannot be changed, linked
to WhatsApp or Google, given a token, or deleted.
"""

from __future__ import annotations

import logging
import re
import secrets
from datetime import timedelta
from typing import Any

from . import clock
from .config import settings
from .db import INTEGRITY, Database, token_hash

log = logging.getLogger(__name__)

USERNAME = re.compile(r"[a-z0-9._]{3,30}")
RESERVED = frozenset({
    "7even5ive", "seventy5", "sevenfive", "75", "admin", "administrator", "root", "support",
    "help", "demo", "official", "team", "staff", "system", "null", "undefined", "api", "www",
    "me", "settings", "login", "signup", "account", "accounts", "moderator", "security",
    "privacy", "terms", "anthropic", "claude", "supabase",
})
# "LINK 75-ABC234" (any case; "link:", "link -" too). One character class between the word and
# the code, so a long run of spaces can't make the match slow; and only short texts are tried.
LINK_CODE = re.compile(r"^\s*(?:link\b[\s:\-]*)?(75-[A-Z0-9]{6})\s*$", re.IGNORECASE)
LINK_MAX_CHARS = 40
_CODE_LETTERS = "ABCDEFGHJKMNPQRSTUVWXYZ23456789"  # no 0/O, 1/I/L: read aloud or retyped
LINK_MINUTES = 15
TOKEN_PREFIX = "75p_"
MAX_SUBJECTS = 20


class AccountError(ValueError):
    """The request can't be done as asked. detail is said to the student as it is."""

    def __init__(self, detail: str, status: int = 400, code: str = "invalid") -> None:
        super().__init__(detail)
        self.detail = detail
        self.status = status
        self.code = code


def _demo(db: Database, sid: int) -> bool:
    from . import demo

    return demo.is_demo(db, sid)


def refuse_demo(db: Database, sid: int, what: str) -> None:
    if _demo(db, sid):
        raise AccountError(f"The demo account can't {what}. Create your own account for that.",
                           403, "demo_account")


# --- usernames and profiles ----------------------------------------------------------------
def username_problem(name: str) -> str | None:
    """Why this username can't be used, or None. Checked on lowercase."""
    if not USERNAME.fullmatch(name):
        return "Use 3 to 30 letters, numbers, dots or underscores."
    if name.startswith(".") or name.endswith(".") or ".." in name:
        return "A username can't start or end with a dot, or have two dots in a row."
    if not re.search(r"[a-z0-9]", name):
        return "A username needs at least one letter or number."
    if name in RESERVED:
        return "That username is reserved."
    return None


def username_check(db: Database, raw: str, mine: int | None = None) -> dict[str, Any]:
    name = (raw or "").strip().lower()
    problem = username_problem(name)
    if problem is None:
        row = db.student_by_username(name)
        if row is not None and int(row["id"]) != mine:
            problem = "That username is taken."
    return {"username": name, "available": problem is None, "message": problem}


def _text(body: dict[str, Any], key: str, limit: int, required: bool = False) -> str | None:
    value = body.get(key)
    if value is None or (isinstance(value, str) and not value.strip()):
        if required:
            raise AccountError(f"{key.capitalize()} is required.")
        return None
    if not isinstance(value, str):
        raise AccountError(f"{key.capitalize()} must be text.")
    flat = " ".join(value.split())
    if any(ord(ch) < 32 for ch in flat):
        raise AccountError(f"{key.capitalize()} has characters that can't be used.")
    if len(flat) > limit:
        raise AccountError(f"{key.capitalize()} can be at most {limit} characters.")
    return flat


def _year(body: dict[str, Any]) -> int | None:
    value = body.get("year")
    if value is None or value == "":
        return None
    if isinstance(value, bool) or not isinstance(value, (int, str)):
        raise AccountError("Year must be a number from 1 to 6.")
    try:
        year = int(value)
    except ValueError:
        raise AccountError("Year must be a number from 1 to 6.") from None
    if not 1 <= year <= 6:
        raise AccountError("Year must be a number from 1 to 6.")
    return year


def _subjects(body: dict[str, Any]) -> list[str] | None:
    value = body.get("subjects")
    if value is None:
        return None
    if not isinstance(value, list) or not all(isinstance(v, str) for v in value):
        raise AccountError("Subjects must be a list of names.")
    seen: set[str] = set()
    out: list[str] = []
    for raw in value:
        name = " ".join(raw.split())
        if not name or name.lower() in seen:
            continue
        if len(name) > 60 or any(ord(ch) < 32 for ch in name):
            raise AccountError("Each subject can be at most 60 characters.")
        seen.add(name.lower())
        out.append(name)
    if len(out) > MAX_SUBJECTS:
        raise AccountError(f"At most {MAX_SUBJECTS} subjects.")
    return out


def view(db: Database, sid: int) -> dict[str, Any]:
    """The profile as the app shows it. Never the whole phone number, never a token."""
    row = db.student(sid)
    phone = str(row["wa_phone"] or "")
    return {
        "username": row["username"],
        "name": row["name"],
        "email": row["email"],
        "college": row["college"],
        "branch": row["branch"],
        "year": row["year"],
        "interests": row["interests"],
        "subjects": db.subjects(sid),
        "whatsapp": f"+{phone[:2]} ••••• •{phone[-4:]}" if len(phone) >= 6 else None,
        "personal_token": {"exists": bool(row["token_hash"]) and not _demo(db, sid),
                           "created_at": row["token_created_at"]},
        "demo": _demo(db, sid),
    }


def me(db: Database, sid: int | None, email: str | None = None) -> dict[str, Any]:
    if sid is None:
        return {"onboarded": False, "email": email, "profile": None, "demo": False}
    profile = view(db, sid)
    return {"onboarded": True, "email": profile["email"] or email, "profile": profile,
            "demo": profile["demo"]}


def save_profile(db: Database, user_id: str, email: str | None, body: dict[str, Any]) -> int:
    """Creates this Supabase user's student, or updates it. Returns the student id."""
    existing = db.student_by_auth(user_id)
    sid = int(existing["id"]) if existing is not None else None
    raw_name = body.get("username")
    if sid is None or raw_name is not None:
        check = username_check(db, str(raw_name or ""), mine=sid)
        if not check["available"]:
            status = 409 if check["message"] == "That username is taken." else 400
            raise AccountError(str(check["message"]), status,
                               "username_taken" if status == 409 else "invalid_username")
    fields: dict[str, Any] = {}
    if raw_name is not None or sid is None:
        fields["username"] = str(raw_name).strip().lower()
    name = _text(body, "name", 60, required=sid is None)
    if name is not None:
        fields["name"] = name
    for key, limit in (("college", 80), ("branch", 40), ("interests", 200)):
        if key in body:
            fields[key] = _text(body, key, limit)
    if "year" in body:
        fields["year"] = _year(body)
    subjects = _subjects(body)
    if email:
        fields["email"] = email
    taken = AccountError("That username is taken.", 409, "username_taken")
    try:
        if sid is None:
            sid = db.create_student(auth_user_id=user_id, portal_id="u" + secrets.token_hex(8),
                                    created_at=clock.iso(clock.now()), **fields)
            log.info("profile created", extra={"student": sid})
        else:
            db.update_student(sid, **fields)
    except INTEGRITY:
        # A unique index decided. Either someone took the username a moment ago, or this same
        # account was created by a second request (a double tap): then this one updates it.
        row = db.student_by_auth(user_id)
        if sid is not None or row is None:
            raise taken from None
        sid = int(row["id"])
        try:
            db.update_student(sid, **fields)
        except INTEGRITY:
            raise taken from None
    if subjects is not None:
        db.set_subjects(sid, subjects)
    return sid


# --- personal token (MCP) ---------------------------------------------------------------------
def new_token(db: Database, sid: int) -> dict[str, Any]:
    refuse_demo(db, sid, "make a personal token")
    token = TOKEN_PREFIX + secrets.token_urlsafe(32)
    now = clock.iso(clock.now())
    db.update_student(sid, token_hash=token_hash(token), token_created_at=now)
    db.audit(sid, "personal_token", "allow", "created", now)
    return {"token": token, "created_at": now}


def drop_token(db: Database, sid: int) -> None:
    refuse_demo(db, sid, "change its token")
    db.update_student(sid, token_hash=None, token_created_at=None)
    db.audit(sid, "personal_token", "allow", "revoked", clock.iso(clock.now()))


# --- AI apps connected through the MCP connector (connector.py) ---------------------------------
def connections(db: Database, sid: int) -> list[dict[str, Any]]:
    """What Settings lists: each app's own name, when it was connected and last used. Never a
    token (only their hashes exist)."""
    return [{"id": int(r["id"]), "name": r["client_name"] or "An AI app",
             "connected_at": r["created_at"], "last_used_at": r["last_used_at"]}
            for r in db.grants(sid)]


def disconnect(db: Database, sid: int, grant_id: int) -> bool:
    gone = db.drop_grant(sid, grant_id)
    if gone:
        db.audit(sid, "mcp_disconnect", "allow", "student", clock.iso(clock.now()))
    return gone


# --- WhatsApp -------------------------------------------------------------------------------------
def link_code_in(text: str | None) -> str | None:
    """The code in a "LINK 75-XXXXXX" message, upper case, or None."""
    if not text or len(text) > LINK_MAX_CHARS:
        return None
    match = LINK_CODE.match(text)
    return match.group(1).upper() if match else None


def whatsapp_ready() -> bool:
    """Linking needs the bot's real secret: with the public development one, anyone could sign
    a "LINK" message from any number and take that number over."""
    from .config import DEV_BOT_SECRET

    return settings.bot_secret != DEV_BOT_SECRET


def start_whatsapp(db: Database, sid: int) -> dict[str, Any]:
    refuse_demo(db, sid, "link WhatsApp")
    if not whatsapp_ready():
        raise AccountError("Linking WhatsApp isn't set up on this server yet.", 503,
                           "whatsapp_unavailable")
    code = "75-" + "".join(secrets.choice(_CODE_LETTERS) for _ in range(6))
    expires = clock.now() + timedelta(minutes=LINK_MINUTES)
    db.add_link_code(code, sid, clock.iso(expires))
    number = settings.bot_whatsapp_number
    from urllib.parse import quote

    return {"code": code, "expires_at": clock.iso(expires),
            "message": f"LINK {code}",
            "bot_number": f"+{number}" if number else None,
            "link": f"https://wa.me/{number}?text={quote(f'LINK {code}')}" if number else None}


def link_from_bot(db: Database, text: str, phone: str) -> int | None:
    """The bot forwarded "LINK 75-XXXXXX" from this number (its webhook is signed). Returns the
    student now linked, or None when the code is unknown, used or expired."""
    code = link_code_in(text)
    if code is None or not whatsapp_ready() or not re.fullmatch(r"\d{8,15}", phone or ""):
        return None
    sid = db.link_whatsapp(code, phone, clock.iso(clock.now()))
    if sid is not None:
        db.audit(sid, "whatsapp_link", "allow", "code from the bot", clock.iso(clock.now()))
        # The deadlines the bot already holds for this number arrive now, not only new ones.
        from . import sync

        try:
            sync.backfill(db, sid)
        except Exception as err:  # noqa: BLE001 - linking is done; the next event fills in
            log.warning("backfill after link failed", extra={"error": type(err).__name__})
    return sid


def unlink_whatsapp(db: Database, sid: int) -> None:
    refuse_demo(db, sid, "change its WhatsApp")
    db.update_student(sid, wa_phone=None)
    db.audit(sid, "whatsapp_unlink", "allow", "student", clock.iso(clock.now()))


# --- deleting an account ----------------------------------------------------------------------
def forget_portal(portal_id: str | None) -> None:
    """PortMax's saved answers and login state for this student."""
    if not portal_id:
        return
    from sqlalchemy import delete

    from portmax.store import logins, snapshots

    from .tools import portal_store

    with portal_store().engine.begin() as c:
        for table in (snapshots, logins):
            c.execute(delete(table).where(table.c.student_id == portal_id))


def forget_cache(sid: int) -> None:
    from pathlib import Path

    folder = Path(settings.cache_dir) / "briefing"
    for path in folder.glob(f"{sid}-*.mp3") if folder.exists() else ():
        try:
            path.unlink()
        except OSError:
            pass


def delete_everything(db: Database, sid: int) -> None:
    """Every trace of the student in this service: Google revoked, college mail forgotten,
    portal answers, cached audio, then every row. The login itself is auth.delete_user."""
    from . import google, mail

    refuse_demo(db, sid, "be deleted")
    row = db.student(sid)
    try:
        google.disconnect(db, sid)
    except Exception as err:  # noqa: BLE001 - revoking is best effort; the rows go regardless
        log.warning("google disconnect on delete failed", extra={"error": type(err).__name__})
    for which in ("gmail", "demo", "none"):
        mail.store().forget(mail.mailbox_key(sid, which))
    forget_portal(row["portal_id"] if row is not None else None)
    forget_cache(sid)
    db.delete_student(sid)
    log.info("account deleted", extra={"student": sid})
