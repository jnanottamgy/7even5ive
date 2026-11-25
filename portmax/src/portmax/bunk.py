"""Bunk math: what each subject's attendance means for the student, as plain sentences.

Pure arithmetic on the portal's own numbers, at the college's minimum (75% by default), done in
exact fractions so a student at exactly 75% is never told they are short. No model writes the
sentences, so nothing can be invented.

Two views per subject. Right now: how many classes can be missed, or must be attended in a row,
measured on classes held so far. Over the semester, when the portal shows classes planned: how
many of the remaining classes can be missed, and whether the minimum is still reachable at all.
Upcoming class dates come from the weekly timetable; holidays are not known, so they are a guide.
"""

from __future__ import annotations

import math
from datetime import date, datetime, timedelta, timezone
from fractions import Fraction
from typing import Literal

from pydantic import Field

from portmax.contract import Answer, AttendanceRow, Model, TimetableSlot, Weekday

DEFAULT_MINIMUM_PERCENT = 75.0
MAX_LISTED_CLASSES = 10
# Colleges PortMax serves are in India; there is no per-student time zone to read.
IST = timezone(timedelta(hours=5, minutes=30))

Status = Literal["safe", "at_risk", "short", "unrecoverable"]


class SemesterOutlook(Model):
    planned: int
    remaining: int
    can_skip_rest_of_semester: int = Field(
        description="Of the remaining classes; negative means the minimum is out of reach"
    )
    best_final_percent: float = Field(description="If every remaining class is attended")


class SubjectPlan(Model):
    subject_code: str
    subject_name: str
    attended: int
    held: int
    percent: float
    minimum_percent: float
    status: Status
    can_skip_now: int = Field(description="Classes that can be missed now, staying at the minimum")
    must_attend: int = Field(description="Classes in a row needed to get back to the minimum")
    next_classes: list[date] = Field(description="From the weekly timetable; holidays not known")
    semester: SemesterOutlook | None = None
    message: str


class AttendancePlanAnswer(Answer):
    tool: Literal["get_attendance_plan"] = "get_attendance_plan"
    data: list[SubjectPlan]


def can_skip(attended: int, held: int, minimum: Fraction) -> int:
    """floor(attended / minimum - held): misses allowed now while staying at the minimum."""
    return max(0, math.floor(Fraction(attended) / minimum - held))


def must_attend(attended: int, held: int, minimum: Fraction) -> int:
    """ceil((minimum * held - attended) / (1 - minimum)): attendances in a row to reach it."""
    return max(0, math.ceil((minimum * held - attended) / (1 - minimum)))


def upcoming(code: str, timetable: list[TimetableSlot], now: datetime, count: int) -> list[date]:
    """The dates of the subject's next `count` classes; a class already started today is past."""
    days = list(Weekday)
    slots = sorted((days.index(s.day), s.start) for s in timetable if s.subject_code == code)
    found: list[date] = []
    if not slots or count < 1:
        return found
    local = now.astimezone(IST)
    day = local.date()
    while len(found) < count:
        for weekday, start in slots:
            if weekday == day.weekday() and (day > local.date() or start > local.time()):
                found.append(day)
        day += timedelta(days=1)
    return found[:count]


def _outlook(row: AttendanceRow, minimum: Fraction) -> SemesterOutlook | None:
    if row.planned is None or row.planned == 0 or row.planned < row.held:
        return None
    remaining = row.planned - row.held
    spare = math.floor(row.attended + remaining - minimum * row.planned)
    return SemesterOutlook(
        planned=row.planned,
        remaining=remaining,
        can_skip_rest_of_semester=min(spare, remaining),
        best_final_percent=round(float(Fraction(row.attended + remaining, row.planned) * 100), 2),
    )


def _day(value: date) -> str:
    return value.strftime("%a %d %b").replace(" 0", " ")


def _classes(n: int) -> str:
    return f"{n} class" if n == 1 else f"{n} classes"


def plan_subject(
    row: AttendanceRow,
    timetable: list[TimetableSlot],
    now: datetime,
    minimum: Fraction = Fraction(3, 4),
) -> SubjectPlan:
    outlook = _outlook(row, minimum)
    skip = can_skip(row.attended, row.held, minimum)
    if outlook is not None:
        skip = min(skip, outlook.remaining)  # nobody can miss classes that will not happen
    attend = must_attend(row.attended, row.held, minimum)
    wanted = min(max(attend, 1), MAX_LISTED_CLASSES)
    if outlook is not None:
        wanted = min(wanted, outlook.remaining)  # a finished semester has no next class
    next_classes = upcoming(row.subject_code, timetable, now, wanted)
    line = f"{row.subject_code} {row.percent:g}%"
    floor_text = f"{float(minimum * 100):g}%"
    if outlook is not None and outlook.remaining == 0 and attend == 0:
        status: Status = "safe"
        message = f"{line}: every planned class is done, and you finished at or above {floor_text}."
    elif outlook is not None and outlook.can_skip_rest_of_semester < 0:
        status = "unrecoverable"
        message = (
            f"{line}: even attending every remaining class ends the semester at "
            f"{outlook.best_final_percent:g}%, below {floor_text}. Ask your department about "
            "condonation now."
        )
    elif attend > 0:
        status = "short"
        when = f", starting {_day(next_classes[0])}," if next_classes else ""
        message = f"{line}: attend the next {_classes(attend)} in a row{when} to get back to "
        message += f"{floor_text}."
    elif skip == 0:
        status = "at_risk"
        message = f"{line}: right at the line; missing the next class takes you below {floor_text}."
    elif skip == 1:
        status = "at_risk"
        message = f"{line}: you can miss 1 class and stay at {floor_text}."
    else:
        status = "safe"
        message = f"{line}: you can miss {_classes(skip)} and stay at {floor_text}."
    if outlook is not None and status in ("safe", "at_risk") and outlook.remaining:
        spare = max(outlook.can_skip_rest_of_semester, 0)
        message += f" Over the rest of the semester you can miss {spare} of {outlook.remaining}."
    return SubjectPlan(
        subject_code=row.subject_code,
        subject_name=row.subject_name,
        attended=row.attended,
        held=row.held,
        percent=row.percent,
        minimum_percent=float(minimum * 100),
        status=status,
        can_skip_now=skip,
        must_attend=attend,
        next_classes=next_classes,
        semester=outlook,
        message=message,
    )


_ORDER: dict[Status, int] = {"unrecoverable": 0, "short": 1, "at_risk": 2, "safe": 3}


def attendance_plan(
    attendance: list[AttendanceRow],
    timetable: list[TimetableSlot],
    now: datetime,
    minimum_percent: float = DEFAULT_MINIMUM_PERCENT,
) -> list[SubjectPlan]:
    """Every subject's plan, worst first, so a briefing reads the urgent ones first."""
    minimum = Fraction(minimum_percent).limit_denominator(1000) / 100
    plans = [plan_subject(row, timetable, now, minimum) for row in attendance]
    return sorted(plans, key=lambda p: (_ORDER[p.status], p.percent))
