"""The agent's tools: plain functions over the database, shared by MCP, the web app and voice.

Why one set of functions: Claude, ChatGPT, the phone and the ElevenLabs agent all ask the
same questions, so they get the same answers. The gateway decides who may call what.
Not: tools that plan a study schedule -- 75 organises and presents; it does not plan.
"""

from __future__ import annotations

import hashlib
from datetime import timedelta
from typing import Any

from portmax.errors import NotConnected
from portmax.store import Store
from portmax.tools import attendance_plan_answer

from . import clock
from .config import settings
from .db import Database

_portal: Store | None = None


def portal_store() -> Store:
    # Why PortMax: it owns the portal and the bunk math (exact fractions, the college's own
    # minimum from its manifest). 75 only reads its saved answers -- one implementation.
    global _portal
    if _portal is None:
        _portal = Store(settings.portmax_database_url)
    return _portal


def _card(row: Any) -> dict[str, Any]:
    return {"id": row["id"], "kind": row["kind"], "subject": row["subject"],
            "title": row["title"], "due_at": row["due_at"], "status": row["status"],
            "source": row["source"], "route": row["route"]}


def due_this_week(db: Database, student_id: int) -> list[dict[str, Any]]:
    """Deadlines, exams and events from now until 7 days ahead, soonest first."""
    now = clock.now()
    rows = db.items(student_id, kinds=("deadline", "exam", "event"),
                    due_from=clock.iso(now), due_to=clock.iso(now + timedelta(days=7)))
    return [_card(r) for r in rows]


def materials(db: Database, student_id: int, subject: str | None = None) -> list[dict[str, Any]]:
    return [_card(r) for r in db.items(student_id, kinds=("material",), subject=subject)]


def opportunities(db: Database, student_id: int) -> list[dict[str, Any]]:
    """Events and notices from email that passed the spam filter, most relevant first."""
    rows = db.items(student_id, kinds=("event", "notice"))
    rows = [r for r in rows if r["source"] == "gmail"]
    rows.sort(key=lambda r: -(r["relevance"] or 0))
    return [_card(r) | {"relevance": r["relevance"]} for r in rows]


def attendance(db: Database, student_id: int) -> dict[str, Any]:
    """PortMax's get_attendance_plan for this student: worst subject first, with
    can_skip_now / must_attend and a plain sentence no model wrote."""
    student = db.student(student_id)
    try:
        plan = attendance_plan_answer(portal_store(), student["portal_id"], clock.now())
    except NotConnected:
        return {"connected": False, "subjects": []}
    return {"connected": True, "stale": plan.stale, "fetched_at": plan.fetched_at.isoformat(),
            "subjects": [s.model_dump(mode="json") for s in plan.data]}


def mark_done(db: Database, student_id: int, item_id: int) -> dict[str, Any]:
    """The student finished it: it leaves "due this week", and its reminders and calls are
    skipped. For you, with undo (reopen)."""
    if not db.set_item_status(student_id, int(item_id), "filed", "done"):
        raise ValueError("no open item with that id")
    return {"item_id": int(item_id), "status": "done"}


def reopen(db: Database, student_id: int, item_id: int) -> dict[str, Any]:
    """Undo for mark_done. Reminders that came due while it was done stay skipped."""
    if not db.set_item_status(student_id, int(item_id), "done", "filed"):
        raise ValueError("no done item with that id")
    return {"item_id": int(item_id), "status": "filed"}


def calendar_key(student_id: int, item_id: int) -> str:
    # Fixed per item, so a retry rewrites the same calendar event, never a second one.
    return "75" + hashlib.sha256(f"{student_id}:{item_id}".encode()).hexdigest()[:24]


def add_to_calendar(db: Database, student_id: int, item_id: int) -> dict[str, Any]:
    """Writes outside 75 -- the gateway only lets this run with a one-time approval."""
    item = db.item(student_id, item_id)
    if item is None or not item["due_at"]:
        raise ValueError("no dated item with that id")
    key = calendar_key(student_id, item_id)
    db.upsert_calendar(key, student_id, f"{item['subject']}: {item['title']}", item["due_at"])
    return {"calendar_event": key, "title": item["title"], "starts_at": item["due_at"]}
