"""The gateway: every tool call, from any client, passes these checks in this order.

1. inbound auth   -- the caller is a known student: a Supabase access token (the app, checked
                     in auth.py), an AI app's token (the MCP connector, connector.py, or a
                     personal token), or the demo's token
2. interceptor    -- a write's arguments must point at rows 75 filed itself (provenance),
                     and an 'ask' action needs a valid one-time approval token
3. policy         -- deny by default; each tool is allow, ask or deny (Cedar-shaped)
4. audit          -- every decision logged, ids and names only

Locally this is Python; on AWS the same roles are AgentCore Gateway (inbound auth),
an interceptor Lambda, Cedar policies and the Identity vault, so the rules sit outside
the model and a prompt injection cannot talk its way past them.
Not: asking the model to "be careful" -- a rule the model enforces is a suggestion.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import secrets
import time
from datetime import timedelta
from typing import Any, Callable

from . import clock, notify, tools
from .config import settings
from .db import ACCESS_PREFIX, Database, token_hash

# Cedar-shaped policy: principal = the signed-in student, action = tool, resource = own rows.
# Anything missing from this table is denied.
POLICY: dict[str, str] = {
    "due_this_week": "allow",
    "materials": "allow",
    "attendance": "allow",
    "opportunities": "allow",
    # Reminders only touch the student's own rows inside 7even5ive, so they need no tap.
    "set_reminder": "allow",
    "list_reminders": "allow",
    "cancel_reminder": "allow",
    # Marking one of the student's own cards done, and undoing it, stays inside 7even5ive.
    "mark_done": "allow",
    "reopen": "allow",
    # The library stays in the bot's database; these only read it, scoped to this student.
    "list_library": "allow",
    "list_library_files": "allow",
    "open_file": "allow",
    # Today's picture, from what 7even5ive already holds.
    "briefing": "allow",
    "timetable_today": "allow",
    # Reads the student's own mailbox into their own cards (5-minute cooldown).
    "check_mail_now": "allow",
    "add_to_calendar": "ask",
    "send_email": "deny",  # Gmail is read-only for 75
    "submit_on_portal": "deny",
}

# Tools that stay inside 7even5ive: reads, and writes to the student's own reminders.
OWN: dict[str, Callable[..., Any]] = {
    "due_this_week": tools.due_this_week,
    "materials": tools.materials,
    "attendance": tools.attendance,
    "opportunities": tools.opportunities,
    "set_reminder": notify.set_reminder,
    "list_reminders": notify.list_reminders,
    "cancel_reminder": notify.cancel_reminder,
    "mark_done": tools.mark_done,
    "reopen": tools.reopen,
    "list_library": tools.list_library,
    "list_library_files": tools.list_library_files,
    "open_file": tools.open_file,
    "briefing": tools.briefing,
    "timetable_today": lambda db, sid: tools.timetable_today(db, sid),
    "check_mail_now": tools.check_mail_now,
}
WRITES: dict[str, Callable[..., Any]] = {"add_to_calendar": tools.add_to_calendar}

# Every tool's arguments, by name and kind; a tool not listed takes none. Checked before a tool
# runs and before an approval is made or spent, so a client (or a model) can't crash a tool, or
# spend a student's approval, with a wrong type, an unknown name or a number no row could have.
ARGS: dict[str, dict[str, type]] = {
    "materials": {"subject": str},
    "set_reminder": {"item_id": int, "before_minutes": int, "channel": str},
    "cancel_reminder": {"reminder_id": int},
    "mark_done": {"item_id": int},
    "reopen": {"item_id": int},
    "add_to_calendar": {"item_id": int},
    "list_library_files": {"subject_id": int, "shelf": str, "unsorted": bool, "offset": int},
    "open_file": {"file_id": int},
}
REQUIRED: dict[str, tuple[str, ...]] = {
    "set_reminder": ("item_id",), "cancel_reminder": ("reminder_id",), "mark_done": ("item_id",),
    "reopen": ("item_id",), "add_to_calendar": ("item_id",), "open_file": ("file_id",)}
RANGES: dict[str, tuple[int, int]] = {"before_minutes": (0, 366 * 24 * 60), "offset": (0, 10**6)}
TEXT_MAX = 200


def check_args(tool: str, args: dict[str, Any]) -> dict[str, Any]:
    """The arguments as the tool takes them, or Denied saying which one is wrong."""
    spec = ARGS.get(tool, {})
    out: dict[str, Any] = {}
    for name, value in args.items():
        kind = spec.get(name)
        if kind is None:
            raise Denied(f"{tool} takes no argument {str(name)[:40]!r}")
        if kind is bool and not isinstance(value, bool):
            raise Denied(f"{name} must be true or false")
        if kind is int:
            if isinstance(value, float) and value.is_integer():
                value = int(value)
            low, high = RANGES.get(name, (0, 2**53))
            if isinstance(value, bool) or not isinstance(value, int) or not low <= value <= high:
                raise Denied(f"{name} must be a whole number from {low} to {high}")
        if kind is str and (not isinstance(value, str) or len(value) > TEXT_MAX):
            raise Denied(f"{name} must be text, at most {TEXT_MAX} characters")
        out[str(name)] = value
    missing = [name for name in REQUIRED.get(tool, ()) if name not in out]
    if missing:
        raise Denied(f"{tool} needs {missing[0]}")
    return out


def approvals_ready() -> bool:
    """The approval secret is the team's own, or this isn't a real deployment."""
    from .config import DEV_APPROVAL_SECRET, deployed

    return settings.approval_secret != DEV_APPROVAL_SECRET or not deployed()


class Denied(Exception):
    """Refused. status/code tell the app what to do: 401 session_expired (refresh the session,
    else sign in again), 403 profile_required (finish the profile), 503 (try again later)."""

    def __init__(self, message: str, status: int = 401, code: str = "unauthorized") -> None:
        super().__init__(message)
        self.status = status
        self.code = code


def _b64(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).decode().rstrip("=")


def _mac(body: str) -> str:
    return _b64(hmac.new(settings.approval_secret.encode(), body.encode(), hashlib.sha256).digest())


def mint_token(student_id: int, action: str, args: dict[str, Any], ttl: int | None = None) -> str:
    """A token bound to one student, one action and these exact arguments."""
    body = json.dumps({"s": student_id, "a": action, "g": args, "n": secrets.token_hex(8),
                       "e": int(time.time()) + (ttl or settings.approval_ttl_seconds)},
                      sort_keys=True, separators=(",", ":"))
    return f"{_b64(body.encode())}.{_mac(body)}"


def read_token(token: str) -> dict[str, Any]:
    try:
        body_b64, mac = token.split(".")
        body = base64.urlsafe_b64decode(body_b64 + "=" * (-len(body_b64) % 4)).decode()
    except (ValueError, UnicodeDecodeError) as err:
        raise Denied("malformed approval") from err
    if not hmac.compare_digest(_mac(body), mac):
        raise Denied("approval signature invalid")
    claims: dict[str, Any] = json.loads(body)
    if claims["e"] < time.time():
        raise Denied("approval expired")
    return claims


class Gateway:
    def __init__(self, db: Database) -> None:
        self.db = db

    def _log(self, student_id: int | None, tool: str, decision: str, reason: str) -> None:
        self.db.audit(student_id, tool, decision, reason, clock.iso(clock.now()))

    def identify(self, token: str | None, allow_deleted: bool = False) -> tuple[Any, Any]:
        """(Supabase identity or None, student row or None) for a token, without the scope
        rules: /api/me uses it, for a signed-in student who has no profile yet. The session of
        an account deleted a moment ago is refused (401 account_deleted), except for a retry of
        the deletion itself (allow_deleted)."""
        from . import auth

        token = (token or "").strip()
        if not token:
            raise Denied("unknown caller")
        if auth.looks_like_jwt(token):
            try:
                identity = auth.verify(token)
            except auth.AuthError as err:
                if err.status == 401:
                    self._log(None, "*", "deny", "invalid session")
                raise Denied(str(err), err.status, err.code) from err
            row = self.db.student_by_auth(identity.user_id)
            if row is None and not allow_deleted and self.db.is_deleted(identity.user_id):
                raise Denied("This account was deleted.", 401, "account_deleted")
            return identity, row
        row = self.db.student_by_token(token)
        if row is None and token.startswith(ACCESS_PREFIX):
            # An AI app connected through the MCP connector: like a personal token, MCP only.
            now = clock.now()
            row = self.db.student_by_grant(token_hash(token), int(time.time()), clock.iso(now),
                                           clock.iso(now - timedelta(hours=1)))
        if row is None:
            self._log(None, "*", "deny", "unknown caller")
            raise Denied("unknown caller")
        return None, row

    def authenticate(self, token: str | None, scope: str = "app") -> int:
        """The student behind a token. scope "app": the app's API and PortMax; "mcp": an MCP
        client. A real account's personal token is for MCP only."""
        identity, row = self.identify(token)
        if row is None:
            raise Denied("Finish setting up your account first.", 403, "profile_required")
        if identity is None and scope != "mcp" and row["auth_user_id"]:
            self._log(int(row["id"]), "*", "deny", "personal token outside MCP")
            raise Denied("This token is for MCP clients. Sign in to the app instead.")
        return int(row["id"])

    def _provenance(self, student_id: int, tool: str, args: dict[str, Any]) -> None:
        # A write may only use values 75 filed from a real event -- never text the model
        # (or a poisoned email) typed into the call.
        if tool in ("add_to_calendar", "set_reminder"):
            item = self.db.item(student_id, int(args.get("item_id", -1)))
            if item is None or item["event_id"] is None or item["status"] != "filed":
                raise Denied("item_id is not a filed item of this student")

    def call(self, student_id: int, tool: str, args: dict[str, Any] | None = None,
             approval: str | None = None) -> dict[str, Any]:
        args = {} if args is None else args
        rule = POLICY.get(tool, "deny")
        if rule == "deny":
            self._log(student_id, tool, "deny", "policy")
            raise Denied(f"{tool} is not allowed")
        try:
            args = check_args(tool, args if isinstance(args, dict) else {"": args})
        except Denied as err:
            self._log(student_id, tool, "deny", str(err))
            raise

        if rule == "allow":
            try:
                self._provenance(student_id, tool, args)
                result = OWN[tool](self.db, student_id, **args)
            except (Denied, ValueError) as err:
                self._log(student_id, tool, "deny", str(err))
                raise Denied(str(err)) from err
            except TypeError as err:  # never Python's own words to a client
                self._log(student_id, tool, "deny", "arguments")
                raise Denied(f"those arguments don't fit {tool}") from err
            self._log(student_id, tool, "allow", "policy")
            return {"status": "ok", "result": result}

        # rule == "ask"
        try:
            if not approvals_ready():
                raise Denied("Approvals aren't set up on this server yet.", 503,
                             "approvals_unavailable")
            self._provenance(student_id, tool, args)
        except Denied as err:
            self._log(student_id, tool, "deny", str(err))
            raise
        if approval is None:
            token = mint_token(student_id, tool, args)
            nonce = read_token(token)["n"]
            self.db.add_pending(nonce, student_id, tool, args, token, clock.iso(clock.now()))
            self._log(student_id, tool, "ask", "approval requested")
            return {"status": "approval_needed",
                    "message": "Sent to the student's phone. It runs after they tap Approve."}
        return self.approve(student_id, approval, expect=(tool, args))

    def approve(self, student_id: int, token: str,
                expect: tuple[str, dict[str, Any]] | None = None) -> dict[str, Any]:
        """Runs an approved write exactly once."""
        try:
            claims = read_token(token)
            if claims["s"] != student_id:
                raise Denied("approval belongs to another student")
            if expect and (claims["a"], claims["g"]) != expect:
                raise Denied("approval is for a different action")
            if POLICY.get(claims["a"]) != "ask":
                raise Denied("action no longer allowed")
            if not approvals_ready():
                raise Denied("Approvals aren't set up on this server yet.", 503,
                             "approvals_unavailable")
            claims["g"] = check_args(claims["a"], claims["g"])  # before it is spent
            self._provenance(student_id, claims["a"], claims["g"])
            if not self.db.spend_nonce(claims["n"], clock.iso(clock.now())):
                raise Denied("approval already used")
        except Denied as err:
            self._log(student_id, "approve", "deny", str(err))
            raise
        self._log(student_id, claims["a"], "allow", "approved by student")
        return {"status": "ok", "result": WRITES[claims["a"]](self.db, student_id, **claims["g"])}
