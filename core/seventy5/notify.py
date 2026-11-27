"""Reminders: 7even5ive notes them when the student opts in, and fires them itself.

Why 7even5ive and not the bot: one owner, so a student never gets the same reminder twice.
Why claim-then-send: the background loop runs every 30 seconds; if two runs overlap, the
UPDATE that flips 'pending' to 'sent' succeeds for only one of them.
Why an outbox: every message for the student is a row the phone pulls. A push (Firebase) only
wakes the phone up and carries nothing, so no title or deadline ever travels through Google's
push service, and a phone that missed the push still gets the message on its next pull.
Not: a reminder for a deadline the student just forwarded -- reminders exist only when the
student asks for one. Not: a reminder for something done, deleted or already past: skipped.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any, Callable, Protocol

from . import clock
from .db import Database

log = logging.getLogger(__name__)


class Sender(Protocol):
    def send(self, student_id: int, title: str, body: str, *, kind: str = "reminder",
             item_id: int | None = None, reminder_id: int | None = None) -> None: ...


@dataclass
class LogSender:
    """Stand-in: keeps what it would have pushed, so tests and the demo can show it."""

    sent: list[dict[str, Any]] = field(default_factory=list)

    def send(self, student_id: int, title: str, body: str, *, kind: str = "reminder",
             item_id: int | None = None, reminder_id: int | None = None) -> None:
        self.sent.append({"student_id": student_id, "title": title, "body": body,
                          "kind": kind, "item_id": item_id, "reminder_id": reminder_id})
        log.info("notification sent", extra={"student": student_id, "kind": kind})


class OutboxSender:
    """Writes the message to the student's outbox, then wakes their phones (best effort)."""

    def __init__(self, db: Database, wake: Callable[[int], None] | None = None) -> None:
        self.db = db
        self.wake = wake

    def send(self, student_id: int, title: str, body: str, *, kind: str = "reminder",
             item_id: int | None = None, reminder_id: int | None = None) -> None:
        self.db.add_notification(student_id, kind, title, body, item_id,
                                 clock.iso(clock.now()), reminder_id)
        log.info("notification queued", extra={"student": student_id, "kind": kind})
        if self.wake is not None:
            try:
                self.wake(student_id)
            except Exception:  # noqa: BLE001 - the row is saved; the next pull delivers it
                log.warning("wake-up failed", extra={"student": student_id})


def due_text(due_at: str | None) -> str:
    if not due_at:
        return "No date"
    at = datetime.fromisoformat(due_at).astimezone(clock.IST)
    hour = at.strftime("%I:%M %p").lstrip("0")
    return f"Due {at:%a} {at.day} {at:%b}, {hour}"


def set_reminder(db: Database, student_id: int, item_id: int,
                 before_minutes: int = 24 * 60, channel: str = "push") -> dict[str, Any]:
    item = db.item(student_id, item_id)
    if item is None or not item["due_at"] or item["status"] != "filed":
        raise ValueError("no filed, dated item with that id")
    if channel not in ("push", "call"):
        raise ValueError("channel must be push or call")
    if channel == "call":
        from . import calls  # the call rules live with the caller

        calls.check_can_schedule(db, student_id, item_id)
    # Why a floor of 5 minutes: a reminder that fires as it is set is noise.
    fire = datetime.fromisoformat(item["due_at"]) - timedelta(minutes=max(5, int(before_minutes)))
    if fire <= clock.now():
        raise ValueError("that reminder time has already passed")
    rid = db.add_reminder(student_id, item_id, clock.iso(fire), channel)
    if channel == "call":
        # One call per item: a new "call me" replaces an earlier one, as a push.
        db.conn.execute("UPDATE reminders SET channel='push' WHERE item_id=? AND id<>?"
                        " AND channel='call' AND status='pending'", (item_id, rid))
    return {"reminder_id": rid, "fires_at": clock.iso(fire), "title": item["title"],
            "channel": channel}


def list_reminders(db: Database, student_id: int) -> list[dict[str, Any]]:
    return [{"reminder_id": r["id"], "fires_at": r["fire_at"], "title": r["title"],
             "subject": r["subject"], "due_at": r["due_at"], "item_id": r["item_id"],
             "channel": r["channel"]} for r in db.reminders(student_id)]


def cancel_reminder(db: Database, student_id: int, reminder_id: int) -> dict[str, Any]:
    return {"cancelled": db.cancel_reminder(student_id, reminder_id)}


def still_open(item: Any, now: datetime) -> bool:
    """Worth a reminder: filed (not done, filtered or waiting for review) and not yet past."""
    if item is None or item["status"] != "filed" or not item["due_at"]:
        return False
    return datetime.fromisoformat(item["due_at"]) > now


def fire_due(db: Database, sender: Sender, caller: Any = None) -> int:
    """The background loop's job, every 30 seconds. Returns how many fired (pushed or called).

    A call reminder goes to `caller` (calls.place_for_reminder); without one -- or when the
    call rules refuse -- it falls back to a push, so the student is never left with nothing.
    """
    now_dt = clock.now()
    now = clock.iso(now_dt)
    fired = 0
    for r in db.due_reminders(now):
        item = db.item(r["student_id"], r["item_id"])
        if not still_open(item, now_dt):
            db.skip_reminder(r["id"], now)
            continue
        if not db.claim_reminder(r["id"], now):
            continue  # another run took it
        fired += 1
        if r["channel"] == "call" and caller is not None:
            from . import calls

            # Places the call, or -- quiet hours, a cap, consent withdrawn, a failed request --
            # sends the push instead. Either way the student hears about it exactly once.
            calls.place_for_reminder(db, caller, sender, r, item)
            continue
        # The reminder's id goes with it: the phone's own alarm for it may have shown it already.
        sender.send(r["student_id"], f"{r['subject']}: {r['title']}", due_text(r["due_at"]),
                    kind="reminder", item_id=r["item_id"], reminder_id=r["id"])
    return fired
