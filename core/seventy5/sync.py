"""Keeping 7even5ive's deadline cards in step with the WhatsApp bot's deadlines.

The bot tells us when a deadline is created, changed or deleted (an event per change), and
we backfill every upcoming one when the service starts, which also repairs any event lost
while we were down.
Why a version on every card: two deliveries can arrive out of order; the newer one always
wins, so a stale "due Friday" can never overwrite "moved to Monday". Two arriving at once still
make one card: the database allows one card per external id (db.insert_item_once).
Why move reminders with the deadline: a reminder set "an hour before" must still be an hour
before after the date changes, and a deleted deadline must never fire one.
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any

from . import clock
from .cascade import Outcome, _parse_due
from .db import Database
from .library import LibraryUnavailable, configured, get_library

log = logging.getLogger(__name__)
MISC = "Miscellaneous"


def _external(deadline_id: Any) -> str:
    return f"bot:deadline:{int(deadline_id)}"


def _move_reminders(db: Database, sid: int, item: Any, new_due: str | None) -> None:
    old_due = item["due_at"]
    for r in db.pending_reminders_for(sid, item["id"]):
        if new_due is None or old_due is None:
            db.cancel_reminder(sid, r["id"])
            continue
        before = datetime.fromisoformat(old_due) - datetime.fromisoformat(r["fire_at"])
        fire = datetime.fromisoformat(new_due) - before
        if fire <= clock.now():
            db.cancel_reminder(sid, r["id"])  # its moment has passed
        else:
            db.move_reminder(r["id"], clock.iso(fire))


def apply(db: Database, sid: int, event_id: int, payload: dict[str, Any]) -> Outcome:
    kind = str(payload.get("type", "")).removeprefix("deadline.")
    body = payload.get("deadline") or {}
    version = int(payload.get("version") or 0)
    external = _external(body["id"])
    item = db.item_by_external(sid, external)
    if item is not None and (item["external_version"] or 0) >= version:
        return Outcome("bot", "stale", item["id"])  # we already have something newer

    if kind == "deleted":
        if item is None:
            return Outcome("bot", "skipped")
        _move_reminders(db, sid, item, None)
        db.update_item(sid, item["id"], status="cancelled", external_version=version)
        return Outcome("bot", "cancelled", item["id"])

    subject = body.get("subject") or MISC
    if subject != MISC:
        db.add_subject(sid, subject)  # the bot's subject list is the one that counts
    due = _parse_due(body.get("due_at"))
    fields = {"kind": "deadline", "subject": subject, "title": str(body.get("title") or ""),
              "due_at": due, "status": "filed", "external_version": version}
    if item is None:
        new_id = db.insert_item_once(student_id=sid, event_id=event_id, source="whatsapp",
                                     route="bot", relevance=None,
                                     created_at=clock.iso(clock.now()), external_id=external,
                                     **fields)
        if new_id is not None:
            return Outcome("bot", "filed", new_id)
        # Another delivery of this deadline filed it a moment ago: the newer one still wins.
        item = db.item_by_external(sid, external)
        if item is None:  # and it is gone again (the student's data was deleted meanwhile)
            return Outcome("bot", "skipped")
        if (item["external_version"] or 0) >= version:
            return Outcome("bot", "stale", item["id"])
    if item["due_at"] != due:
        _move_reminders(db, sid, item, due)
    db.update_item(sid, item["id"], **fields)
    return Outcome("bot", "updated", item["id"])


def backfill(db: Database, sid: int) -> list[str]:
    """Pull every upcoming deadline and the subject list from the bot. Returns log lines."""
    if not configured():
        return []
    phone = db.student(sid)["wa_phone"]
    lib = get_library()
    try:
        subjects = [s["name"] for s in lib.library(phone)["subjects"]]
        deadlines = lib.deadlines(phone)
    except (LibraryUnavailable, LookupError) as err:
        log.warning("backfill skipped", extra={"reason": type(err).__name__})
        return [f"library   backfill skipped: {type(err).__name__}"]
    for name in subjects:
        db.add_subject(sid, name)
    event_id = db.insert_event(sid, f"bot:backfill:{clock.iso(clock.now())}", "bot",
                               {"type": "backfill"}, clock.iso(clock.now()))
    if event_id is None:  # same minute, already done
        return []
    db.mark_event(event_id, "done")
    filed = 0
    for d in deadlines:
        # Version 0: any real event, older or newer, still wins over a backfilled copy.
        out = apply(db, sid, event_id, {"type": "deadline.updated", "version": 0, "deadline": d})
        filed += out.status in ("filed", "updated")
    return [f"library   backfill {filed} deadlines, {len(subjects)} subjects from the bot"]
