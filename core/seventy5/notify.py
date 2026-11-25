"""Reminders: 7even5ive notes them when the student opts in, and fires them itself.

Why 7even5ive and not the bot: one owner, so a student never gets the same reminder twice.
Why claim-then-send: the notify Lambda runs every minute; if two runs overlap, the UPDATE
that flips 'pending' to 'sent' succeeds for only one of them.
Not: a reminder for a deadline the student just forwarded -- reminders exist only when
the student asks for one.
Not yet: the Android push sender (FCM). Until then LogSender records what would be sent.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any, Protocol

from . import clock
from .db import Database

log = logging.getLogger(__name__)


class Sender(Protocol):
    def send(self, student_id: int, title: str, body: str) -> None: ...


@dataclass
class LogSender:
    """Stand-in: keeps what it would have pushed, so tests and the demo can show it."""

    sent: list[dict[str, Any]] = field(default_factory=list)

    def send(self, student_id: int, title: str, body: str) -> None:
        self.sent.append({"student_id": student_id, "title": title, "body": body})
        log.info("reminder sent", extra={"student": student_id})


def set_reminder(db: Database, student_id: int, item_id: int,
                 before_minutes: int = 24 * 60) -> dict[str, Any]:
    item = db.item(student_id, item_id)
    if item is None or not item["due_at"] or item["status"] != "filed":
        raise ValueError("no filed, dated item with that id")
    # Why a floor of 5 minutes: a reminder that fires as it is set is noise.
    fire = datetime.fromisoformat(item["due_at"]) - timedelta(minutes=max(5, before_minutes))
    if fire <= clock.now():
        raise ValueError("that reminder time has already passed")
    rid = db.add_reminder(student_id, item_id, clock.iso(fire))
    return {"reminder_id": rid, "fires_at": clock.iso(fire), "title": item["title"]}


def list_reminders(db: Database, student_id: int) -> list[dict[str, Any]]:
    return [{"reminder_id": r["id"], "fires_at": r["fire_at"], "title": r["title"],
             "subject": r["subject"], "due_at": r["due_at"]} for r in db.reminders(student_id)]


def cancel_reminder(db: Database, student_id: int, reminder_id: int) -> dict[str, Any]:
    return {"cancelled": db.cancel_reminder(student_id, reminder_id)}


def fire_due(db: Database, sender: Sender) -> int:
    """The notify Lambda's job (EventBridge, every minute). Returns how many fired."""
    now = clock.iso(clock.now())
    fired = 0
    for r in db.due_reminders(now):
        if not db.claim_reminder(r["id"], now):
            continue  # another run took it
        due = datetime.fromisoformat(r["due_at"]).strftime("%a %d %b, %I:%M %p")
        sender.send(r["student_id"], f"{r['subject']}: {r['title']}", f"Due {due}")
        fired += 1
    return fired
