"""The agent's tools: plain functions over the database, shared by MCP, the web app and voice.

Why one set of functions: Claude, ChatGPT, the phone and the ElevenLabs agent all ask the
same questions, so they get the same answers. The gateway decides who may call what.
Not: tools that plan a study schedule -- 75 organises and presents; it does not plan.
"""

from __future__ import annotations

import hashlib
from datetime import timedelta
from typing import Any

import httpx

from portmax.errors import NotConnected
from portmax.store import Store
from portmax.tools import answer, attendance_plan_answer

from . import clock
from .config import settings
from .db import Database

_portal: Store | None = None


def portal_store() -> Store:
    # Why PortMax: it owns the portal and the bunk math (exact fractions, the college's own
    # minimum from its manifest). 75 only reads its saved answers -- one implementation.
    global _portal
    if _portal is None:
        from portmax.store import metadata

        from .db import open_store

        _portal = open_store(Store, settings.portmax_database_url, metadata)
    return _portal


MAIL_FIELDS = ("category", "organisation", "role", "link", "mail_link", "summary", "event_at")


def subjects(db: Database, student_id: int) -> list[str]:
    """The subjects a message can be filed under: the student's own list (set up with their
    profile, or the bot's), then the subjects of their college portal's attendance once it has
    been read, so a new student needs to type none of them."""
    names = db.subjects(student_id)
    student = db.student(student_id)
    if student is None or not student["portal_id"]:
        return names
    try:
        rows = answer(portal_store(), student["portal_id"], "get_attendance", clock.now()).data
    except NotConnected:
        return names
    except Exception as err:  # noqa: BLE001 - the portal's answer is a bonus, never a blocker
        import logging

        logging.getLogger(__name__).warning("portal subjects unreadable",
                                            extra={"error": type(err).__name__})
        return names
    known = {n.lower() for n in names}
    for row in rows:
        name = " ".join(str(row.subject_name or "").split())
        if name and name.lower() not in known:
            names.append(name)
            known.add(name.lower())
    return names


def _card(row: Any) -> dict[str, Any]:
    card = {"id": row["id"], "kind": row["kind"], "subject": row["subject"],
            "title": row["title"], "due_at": row["due_at"], "status": row["status"],
            "source": row["source"], "route": row["route"]}
    if row["route"] == "mail":  # a college-mail card carries who, what, the form and the mail
        card |= {k: row[k] for k in MAIL_FIELDS}
    return card


def due_this_week(db: Database, student_id: int) -> list[dict[str, Any]]:
    """Deadlines, exams and events from now until 7 days ahead, soonest first."""
    now = clock.now()
    rows = db.items(student_id, kinds=("deadline", "exam", "event"),
                    due_from=clock.iso(now), due_to=clock.iso(now + timedelta(days=7)))
    return [_card(r) for r in rows]


def materials(db: Database, student_id: int, subject: str | None = None) -> list[dict[str, Any]]:
    return [_card(r) for r in db.items(student_id, kinds=("material",), subject=subject)]


def opportunities(db: Database, student_id: int) -> list[dict[str, Any]]:
    """College mail worth a look: placements, internships, exam notices and events that passed
    the filters, still open, most relevant first, then soonest first."""
    cutoff = clock.iso(clock.now() - timedelta(days=1))
    rows = [r for r in db.items(student_id, kinds=("deadline", "exam", "event", "notice"))
            if r["source"] == "gmail"
            and not (r["due_at"] and max(r["due_at"], r["event_at"] or "") < cutoff)]
    rows.sort(key=lambda r: (-(r["relevance"] or 0), r["due_at"] or "9999"))
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


WEEKDAYS = ("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun")


def timetable_today(db: Database, student_id: int, now: Any = None) -> dict[str, Any]:
    """Today's classes from PortMax's saved timetable, in order, with subject names where the
    portal gave them (labs often only have a code)."""
    now = now or clock.now()
    day = WEEKDAYS[now.astimezone(clock.IST).weekday()]
    student = db.student(student_id)
    try:
        table = answer(portal_store(), student["portal_id"], "get_timetable", now)
    except NotConnected:
        return {"connected": False, "day": day, "classes": []}
    names: dict[str, str] = {}
    try:
        for row in answer(portal_store(), student["portal_id"], "get_attendance", now).data:
            names[row.subject_code] = row.subject_name
    except NotConnected:
        pass
    slots = sorted((s for s in table.data if s.day == day), key=lambda s: s.start)
    return {"connected": True, "stale": table.stale, "day": day, "classes": [
        {"start": s.start.strftime("%H:%M"), "end": s.end.strftime("%H:%M"),
         "subject_code": s.subject_code, "subject": names.get(s.subject_code, s.subject_code),
         "room": s.room} for s in slots]}


def check_mail_now(db: Database, student_id: int) -> dict[str, Any]:
    """Check college mail now (5-minute cooldown): new cards land in the Inbox."""
    from . import mail

    return mail.check_mail_now(db, student_id)


def briefing(db: Database, student_id: int) -> dict[str, Any]:
    """Today's briefing: the sections and the text the app (or its voice) reads out."""
    from . import briefing as morning

    return morning.build(db, student_id)


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
    title = f"{item['subject']}: {item['title']}"
    db.upsert_calendar(key, student_id, title, item["due_at"])
    out: dict[str, Any] = {"calendar_event": key, "title": item["title"],
                           "starts_at": item["due_at"]}
    from . import google

    if google.has_calendar(db, student_id):
        # The student's real calendar, with the same fixed id: a retry rewrites, never doubles.
        from mailfilter.errors import MailFilterError

        try:
            out["google"] = {"ok": True, **google.calendar_upsert(
                db, student_id, key, title, item["due_at"])}
        except (google.GoogleUnavailable, MailFilterError, httpx.HTTPError) as err:
            out["google"] = {"ok": False, "reason": str(err) or type(err).__name__}
    return out


# --- the bot's library (read through, never copied: see library.py) ---------------------------
_library: Any = None


def library_client() -> Any:
    global _library
    if _library is None:
        from .library import get_library

        _library = get_library()
    return _library


def _read(call: Any) -> Any:
    from .library import LibraryUnavailable

    try:
        return call()
    except LibraryUnavailable as err:
        # Said, not raised: the Files screen shows it, and nothing else depends on it.
        return {"available": False, "reason": str(err)}
    except LookupError as err:
        raise ValueError("no such subject or file") from err


def list_library(db: Database, student_id: int) -> dict[str, Any]:
    """Subjects of the active term, each with its three shelves and how many files are on them."""
    phone = db.student(student_id)["wa_phone"]
    return dict(_read(lambda: library_client().library(phone)))


def list_library_files(db: Database, student_id: int, subject_id: int | None = None,
                       shelf: str | None = None, unsorted: bool = False,
                       offset: int = 0) -> dict[str, Any]:
    """One shelf of one subject (or files still waiting for a subject), newest first."""
    phone = db.student(student_id)["wa_phone"]
    return dict(_read(lambda: library_client().files(
        phone, subject_id=subject_id, shelf=shelf, unsorted=unsorted, offset=int(offset))))


def open_file(db: Database, student_id: int, file_id: int) -> dict[str, Any]:
    """A link that opens one file for a few minutes, or a note's text."""
    phone = db.student(student_id)["wa_phone"]
    return dict(_read(lambda: library_client().open(phone, int(file_id))))
