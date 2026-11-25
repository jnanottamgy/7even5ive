"""Mock College of Engineering: page HTML to PortMax's five tools.

Pure functions: no network, no files, no clock. Each takes the pages of the steps its tool needs
(see fetch_plan.json) and returns contract models; anything unexpected raises, and the caller
reports PortalChanged instead of guessing.
"""

from __future__ import annotations

import re
from datetime import datetime, time

from portmax.contract import (
    AttendanceRow,
    MarkRow,
    Profile,
    ResultRow,
    Results,
    SemesterSummary,
    TimetableSlot,
    Weekday,
)
from portmax.htmlkit import Missing, integer, number, one, only, parse, table_kv, table_rows, text
from portmax.pages import PagesByStep

_TITLE = re.compile(r"^([A-Z0-9]+) · (.+?)(?:: CIE marks)?$")
_DATE = re.compile(r"(\d{2}-\d{2}-\d{4})")
_PERIOD = re.compile(r"(\d{2}:\d{2}) - (\d{2}:\d{2})")
_GPA = re.compile(r"SGPA:\s*([\d.]+)\s+CGPA:\s*([\d.]+)")


def _course_title(title: str) -> tuple[str, str]:
    match = _TITLE.match(title)
    if match is None:
        raise Missing(f"unexpected course title {title!r}")
    return match.group(1), match.group(2)


def parse_profile(pages: PagesByStep) -> Profile:
    tree = parse(only(pages["dashboard"]).html)
    rows = table_kv(tree, "table.pm-profile")
    # Name, date of birth and parent mobile sit in the same table; they are never read.
    return Profile(
        usn=rows["USN"],
        branch=rows["Branch"],
        semester=integer(rows["Semester"]),
        section=rows.get("Section") or None,
    )


def parse_attendance(pages: PagesByStep) -> list[AttendanceRow]:
    rows: list[AttendanceRow] = []
    for page in pages["course"]:
        tree = parse(page.html)
        code, name = _course_title(text(tree, "h3.pm-course-title"))
        values = table_kv(tree, "table.pm-attendance")
        updated = _DATE.search(text(tree, "p.pm-last-update"))
        rows.append(
            AttendanceRow(
                subject_code=code,
                subject_name=name,
                attended=integer(values["Classes attended"]),
                held=integer(values["Classes held"]),
                percent=number(values["Attendance"]),
                planned=integer(values["Classes planned"]),
                as_of=datetime.strptime(updated.group(1), "%d-%m-%Y").date() if updated else None,
            )
        )
    return rows


def parse_marks(pages: PagesByStep) -> list[MarkRow]:
    marks: list[MarkRow] = []
    for page in pages["cie"]:
        tree = parse(page.html)
        code, _ = _course_title(text(tree, "h3.pm-course-title"))
        header, *body = table_rows(tree, "table.pm-cie-marks")
        if header != ["Component", "Max", "Scored"]:
            raise Missing(f"unexpected CIE columns {header}")
        for component, maximum, scored in body:
            marks.append(
                MarkRow(
                    subject_code=code,
                    component=component,
                    scored=number(scored),
                    maximum=number(maximum),
                )
            )
    return marks


def parse_timetable(pages: PagesByStep) -> list[TimetableSlot]:
    table = one(parse(only(pages["timetable"]).html), "table.pm-timetable")
    header, *days = table.css("tr")
    periods: list[tuple[time, time]] = []
    for label in [cell.text() for cell in header.css("th")][1:]:
        match = _PERIOD.search(label)
        if match is None:
            raise Missing(f"unexpected period heading {label!r}")
        periods.append((time.fromisoformat(match.group(1)), time.fromisoformat(match.group(2))))
    slots: list[TimetableSlot] = []
    for row in days:
        day = Weekday(one(row, "th").text(strip=True))
        for (start, end), cell in zip(periods, row.css("td"), strict=True):
            code = cell.text(deep=False, strip=True)
            if not code or code == "—":
                continue
            room = cell.css_first("small")
            slots.append(
                TimetableSlot(
                    day=day,
                    start=start,
                    end=end,
                    subject_code=code,
                    room=room.text(strip=True) if room is not None else None,
                )
            )
    return slots


def parse_results(pages: PagesByStep) -> Results:
    tree = parse(only(pages["results"]).html)
    subjects: list[ResultRow] = []
    semesters: list[SemesterSummary] = []
    for section in tree.css("section.pm-sem"):
        semester = integer(section.attributes.get("data-sem") or "")
        _, *body = table_rows(section, "table.pm-results")
        for code, credits, grade, points in body:
            subjects.append(
                ResultRow(
                    semester=semester,
                    subject_code=code,
                    credits=number(credits),
                    grade=grade,
                    grade_points=number(points),
                )
            )
        gpa = _GPA.search(text(section, "p.pm-gpa"))
        if gpa is None:
            raise Missing(f"semester {semester} has no SGPA/CGPA line")
        semesters.append(
            SemesterSummary(semester=semester, sgpa=float(gpa.group(1)), cgpa=float(gpa.group(2)))
        )
    if not semesters:
        raise Missing("no semesters on the results page")
    return Results(subjects=subjects, semesters=semesters)
