"""The gateway: every tool call, from any client, passes these checks in this order.

1. inbound auth   -- the caller is a known student (MCP token / signed-in phone)
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
from typing import Any, Callable

from . import clock, notify, tools
from .config import settings
from .db import Database

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
}
WRITES: dict[str, Callable[..., Any]] = {"add_to_calendar": tools.add_to_calendar}


class Denied(Exception):
    pass


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

    def authenticate(self, mcp_token: str | None) -> int:
        row = self.db.student_by_token(mcp_token) if mcp_token else None
        if row is None:
            self._log(None, "*", "deny", "unknown caller")
            raise Denied("unknown caller")
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
        args = args or {}
        rule = POLICY.get(tool, "deny")
        if rule == "deny":
            self._log(student_id, tool, "deny", "policy")
            raise Denied(f"{tool} is not allowed")

        if rule == "allow":
            try:
                self._provenance(student_id, tool, args)
                result = OWN[tool](self.db, student_id, **args)
            except (Denied, ValueError, TypeError) as err:
                self._log(student_id, tool, "deny", str(err))
                raise Denied(str(err)) from err
            self._log(student_id, tool, "allow", "policy")
            return {"status": "ok", "result": result}

        # rule == "ask"
        try:
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
            self._provenance(student_id, claims["a"], claims["g"])
            if not self.db.spend_nonce(claims["n"], clock.iso(clock.now())):
                raise Denied("approval already used")
        except Denied as err:
            self._log(student_id, "approve", "deny", str(err))
            raise
        self._log(student_id, claims["a"], "allow", "approved by student")
        return {"status": "ok", "result": WRITES[claims["a"]](self.db, student_id, **claims["g"])}
