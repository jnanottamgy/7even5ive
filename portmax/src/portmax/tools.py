"""The tools, answered from what the student's last refresh saved. No portal call here."""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime, timedelta
from functools import cache

from pydantic import TypeAdapter

from portmax.bunk import DEFAULT_MINIMUM_PERCENT, AttendancePlanAnswer, attendance_plan
from portmax.contract import ANSWER_MODELS, Answer, AttendanceRow, TimetableSlot, ToolName
from portmax.errors import NotConnected
from portmax.store import Store

# Attendance changes daily, so an answer more than a day old is flagged; the briefing says so.
STALE_AFTER = timedelta(hours=24)


def answer(
    store: Store,
    student_id: str,
    tool: ToolName,
    now: datetime,
    *,
    stale_after: timedelta = STALE_AFTER,
) -> Answer:
    snapshot = store.snapshot(student_id, tool)
    if snapshot is None:
        raise NotConnected(f"no {tool} saved yet: connect the portal in the app")
    return ANSWER_MODELS[tool].model_validate(
        {
            "college": snapshot.college,
            "connector_version": snapshot.connector_version,
            "fetched_at": snapshot.fetched_at,
            "stale": now - snapshot.fetched_at > stale_after,
            "data": snapshot.data,
        }
    )


@cache  # connectors ship with the code, so one read per process is enough
def college_minimum(college: str) -> float:
    """The college's attendance minimum from its manifest; 75% if it has no connector here."""
    from portmax.connector import load_connector

    try:
        return load_connector(college).manifest.attendance_minimum_percent
    except (FileNotFoundError, ModuleNotFoundError, ValueError):
        return DEFAULT_MINIMUM_PERCENT


def attendance_plan_answer(
    store: Store,
    student_id: str,
    now: datetime,
    *,
    minimum_for: Callable[[str], float] = college_minimum,
    stale_after: timedelta = STALE_AFTER,
) -> AttendancePlanAnswer:
    """Bunk math from the saved attendance and, where the portal has one, the saved timetable."""
    attendance = store.snapshot(student_id, "get_attendance")
    if attendance is None:
        raise NotConnected("no attendance saved yet: connect the portal in the app")
    timetable = store.snapshot(student_id, "get_timetable")  # MSRIT's portal has none
    rows = TypeAdapter(list[AttendanceRow]).validate_python(attendance.data)
    slots = TypeAdapter(list[TimetableSlot]).validate_python(timetable.data) if timetable else []
    return AttendancePlanAnswer(
        college=attendance.college,
        connector_version=attendance.connector_version,
        fetched_at=attendance.fetched_at,
        stale=now - attendance.fetched_at > stale_after,
        data=attendance_plan(rows, slots, now, minimum_for(attendance.college)),
    )
