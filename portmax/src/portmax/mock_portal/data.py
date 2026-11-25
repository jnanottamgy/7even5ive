"""The mock portal's ground truth: one made-up student, and the answers PortMax must produce."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, time

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


@dataclass
class Course:
    code: str
    name: str
    attended: int
    held: int
    planned: int
    last_updated: date
    cie: list[tuple[str, float, float]]  # (component, scored, maximum)

    @property
    def percent(self) -> float:
        return round(self.attended / self.held * 100, 2) if self.held else 0.0


@dataclass
class SemesterResult:
    semester: int
    subjects: list[tuple[str, float, str, float]]  # (code, credits, grade, grade points)
    sgpa: float
    cgpa: float


@dataclass
class Student:
    usn: str
    name: str  # shown on the portal, never extracted by PortMax
    dob: date
    parent_mobile: str  # the login's second step asks for its last four digits
    branch: str
    semester: int
    section: str
    courses: list[Course]
    # (day, period index, course code, room); periods are the portal's fixed time grid
    timetable: list[tuple[Weekday, int, str, str]]
    results: list[SemesterResult]


PERIODS: list[tuple[time, time]] = [
    (time(9, 0), time(9, 55)),
    (time(10, 0), time(10, 55)),
    (time(11, 10), time(12, 5)),
    (time(12, 5), time(13, 0)),
    (time(14, 0), time(14, 55)),
    (time(15, 0), time(15, 55)),
]


@dataclass
class MockState:
    students: dict[str, Student] = field(default_factory=dict)

    def student(self, usn: str) -> Student:
        return self.students[usn]


def demo_student() -> Student:
    updated = date(2026, 11, 24)
    return Student(
        usn="1MC24CS042",
        name="Asha Rao",
        dob=date(2005, 8, 14),
        parent_mobile="9845012345",
        branch="Computer Science and Engineering",
        semester=5,
        section="B",
        courses=[
            Course(
                "CS51",
                "Computer Networks",
                26,
                30,
                52,
                updated,
                [("CIE-1", 24, 30), ("Quiz-1", 8, 10)],
            ),
            Course(
                "CS52", "Database Management Systems", 22, 30, 52, updated, [("CIE-1", 21.5, 30)]
            ),
            Course(
                "CS53",
                "Design and Analysis of Algorithms",
                27,
                29,
                48,
                updated,
                [("CIE-1", 27, 30)],
            ),
            Course(
                "CS54",
                "Operating Systems",
                25,
                31,
                52,
                updated,
                [("CIE-1", 18, 30), ("Quiz-1", 9, 10)],
            ),
            Course(
                "MA51",
                "Probability and Statistics",
                19,
                24,
                42,
                date(2026, 11, 22),
                [("CIE-1", 22, 30)],
            ),
            Course("CSL57", "DBMS Laboratory", 11, 12, 14, updated, [("Lab record", 18, 20)]),
        ],
        timetable=[
            (Weekday.MON, 0, "CS52", "LH-204"),
            (Weekday.MON, 1, "CS54", "LH-204"),
            (Weekday.MON, 2, "MA51", "LH-108"),
            (Weekday.MON, 4, "CSL57", "LAB-3"),
            (Weekday.MON, 5, "CSL57", "LAB-3"),
            (Weekday.TUE, 0, "CS51", "LH-204"),
            (Weekday.TUE, 1, "CS53", "LH-204"),
            (Weekday.TUE, 3, "CS52", "LH-204"),
            (Weekday.WED, 0, "CS54", "LH-204"),
            (Weekday.WED, 2, "CS53", "LH-206"),
            (Weekday.WED, 4, "MA51", "LH-108"),
            (Weekday.THU, 1, "CS52", "LH-204"),
            (Weekday.THU, 2, "CS51", "LH-204"),
            (Weekday.FRI, 0, "CS53", "LH-204"),
            (Weekday.FRI, 1, "CS54", "LH-204"),
            (Weekday.FRI, 3, "MA51", "LH-108"),
            (Weekday.SAT, 0, "CS51", "LH-204"),
        ],
        results=[
            SemesterResult(
                3, [("CS31", 4, "A", 9), ("CS32", 4, "B+", 8), ("MA31", 3, "A+", 10)], 8.91, 8.62
            ),
            SemesterResult(
                4, [("CS41", 4, "A", 9), ("CS42", 4, "A", 9), ("MA41", 3, "B", 7)], 8.45, 8.58
            ),
        ],
    )


def default_state() -> MockState:
    student = demo_student()
    return MockState(students={student.usn: student})


# The answers PortMax must produce for a student: the golden output for the mock portal.


def expected_attendance(student: Student) -> list[AttendanceRow]:
    return [
        AttendanceRow(
            subject_code=c.code,
            subject_name=c.name,
            attended=c.attended,
            held=c.held,
            percent=c.percent,
            planned=c.planned,
            as_of=c.last_updated,
        )
        for c in student.courses
    ]


def expected_marks(student: Student) -> list[MarkRow]:
    return [
        MarkRow(subject_code=c.code, component=component, scored=scored, maximum=maximum)
        for c in student.courses
        for component, scored, maximum in c.cie
    ]


def expected_timetable(student: Student) -> list[TimetableSlot]:
    order = list(Weekday)
    slots = sorted(student.timetable, key=lambda s: (order.index(s[0]), s[1]))
    return [
        TimetableSlot(
            day=day, start=PERIODS[period][0], end=PERIODS[period][1], subject_code=code, room=room
        )
        for day, period, code, room in slots
    ]


def expected_results(student: Student) -> Results:
    return Results(
        subjects=[
            ResultRow(semester=r.semester, subject_code=code, credits=cr, grade=g, grade_points=gp)
            for r in student.results
            for code, cr, g, gp in r.subjects
        ],
        semesters=[
            SemesterSummary(semester=r.semester, sgpa=r.sgpa, cgpa=r.cgpa) for r in student.results
        ],
    )


def expected_profile(student: Student) -> Profile:
    return Profile(
        usn=student.usn, branch=student.branch, semester=student.semester, section=student.section
    )
