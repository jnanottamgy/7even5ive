from __future__ import annotations

from datetime import UTC, date, datetime, time
from fractions import Fraction

import pytest

from portmax.bunk import IST, attendance_plan, can_skip, must_attend, plan_subject, upcoming
from portmax.contract import AttendanceRow, TimetableSlot, Weekday

MIN = Fraction(3, 4)
MONDAY_7AM = datetime(2026, 11, 30, 7, 0, tzinfo=IST)  # the morning briefing's hour


def row(attended: int, held: int, planned: int | None = None, code: str = "CS52") -> AttendanceRow:
    return AttendanceRow(
        subject_code=code,
        subject_name="Database Management Systems",
        attended=attended,
        held=held,
        percent=round(attended / held * 100, 2),
        planned=planned,
    )


SLOTS = [
    TimetableSlot(day=Weekday.MON, start=time(9), end=time(10), subject_code="CS52"),
    TimetableSlot(day=Weekday.THU, start=time(10), end=time(11), subject_code="CS52"),
]


@pytest.mark.parametrize(
    ("attended", "held", "skip", "attend"),
    [
        (33, 45, 0, 3),  # brain.md's example: 73% -> attend the next 3 to reach 75%
        (26, 30, 4, 0),  # 86.7%: 26/34 is 76.5%, 26/35 would be 74.3%
        (30, 40, 0, 0),  # exactly 75%: neither short nor able to skip
        (0, 0, 0, 0),
    ],
)
def test_the_arithmetic_is_exact(attended: int, held: int, skip: int, attend: int) -> None:
    assert can_skip(attended, held, MIN) == skip
    assert must_attend(attended, held, MIN) == attend


def test_a_short_subject_says_how_many_in_a_row_and_from_when() -> None:
    plan = plan_subject(row(33, 45), SLOTS, MONDAY_7AM)
    assert plan.status == "short" and plan.must_attend == 3
    assert plan.next_classes == [date(2026, 11, 30), date(2026, 12, 3), date(2026, 12, 7)]
    assert plan.message == (
        "CS52 73.33%: attend the next 3 classes in a row, starting Mon 30 Nov, to get back to 75%."
    )


def test_a_class_that_has_started_is_not_coming_up() -> None:
    nine_thirty = datetime(2026, 11, 30, 9, 30, tzinfo=IST)
    assert upcoming("CS52", SLOTS, nine_thirty, 2) == [date(2026, 12, 3), date(2026, 12, 7)]


def test_the_day_is_read_in_india_whatever_the_server_clock() -> None:
    four_utc = datetime(2026, 11, 30, 4, 0, tzinfo=UTC)  # 09:30 in India: Monday's class began
    assert upcoming("CS52", SLOTS, four_utc, 1) == [date(2026, 12, 3)]


def test_a_safe_subject_counts_the_rest_of_the_semester_too() -> None:
    plan = plan_subject(row(26, 30, planned=52), SLOTS, MONDAY_7AM)
    assert (plan.status, plan.can_skip_now) == ("safe", 4)
    assert plan.semester is not None
    assert (plan.semester.remaining, plan.semester.can_skip_rest_of_semester) == (22, 9)
    assert plan.message == (
        "CS52 86.67%: you can miss 4 classes and stay at 75%. "
        "Over the rest of the semester you can miss 9 of 22."
    )


@pytest.mark.parametrize(
    ("attended", "held", "said"),
    [
        (30, 40, "CS52 75%: right at the line; missing the next class takes you below 75%."),
        (19, 24, "CS52 79.17%: you can miss 1 class and stay at 75%."),
    ],
)
def test_a_subject_near_the_line_is_at_risk(attended: int, held: int, said: str) -> None:
    plan = plan_subject(row(attended, held), SLOTS, MONDAY_7AM)
    assert plan.status == "at_risk" and plan.message == said


def test_nobody_is_told_to_miss_classes_that_will_not_happen() -> None:
    plan = plan_subject(row(29, 30, planned=32), SLOTS, MONDAY_7AM)
    assert plan.can_skip_now == 2  # 29 of 38 would still be 76%, but only 2 classes are left
    assert plan.message.endswith("Over the rest of the semester you can miss 2 of 2.")


def test_a_finished_semester_lists_no_classes() -> None:
    plan = plan_subject(row(27, 30, planned=30), SLOTS, MONDAY_7AM)
    assert (plan.status, plan.can_skip_now, plan.next_classes) == ("safe", 0, [])
    assert plan.message == (
        "CS52 90%: every planned class is done, and you finished at or above 75%."
    )


def test_out_of_reach_is_said_plainly() -> None:
    plan = plan_subject(row(10, 30, planned=40), SLOTS, MONDAY_7AM)
    assert plan.status == "unrecoverable"
    assert plan.message == (
        "CS52 33.33%: even attending every remaining class ends the semester at 50%, below 75%. "
        "Ask your department about condonation now."
    )


def test_no_timetable_means_no_invented_dates() -> None:
    plan = plan_subject(row(33, 45), [], MONDAY_7AM)  # MSRIT's portal has no timetable
    assert plan.next_classes == []
    assert plan.message == "CS52 73.33%: attend the next 3 classes in a row to get back to 75%."
    assert upcoming("CS99", SLOTS, MONDAY_7AM, 3) == []


def test_the_college_minimum_is_used_throughout() -> None:
    [at_85] = attendance_plan([row(26, 30)], SLOTS, MONDAY_7AM, minimum_percent=85)
    assert (at_85.minimum_percent, at_85.status) == (85, "at_risk")
    assert at_85.message == (
        "CS52 86.67%: right at the line; missing the next class takes you below 85%."
    )
    [exactly] = attendance_plan([row(17, 20)], SLOTS, MONDAY_7AM, minimum_percent=85)
    assert exactly.must_attend == 0  # exactly 85% is never short


def test_the_worst_subject_comes_first() -> None:
    plans = attendance_plan(
        [
            row(26, 30, code="CS51"),
            row(33, 45, code="CS52"),
            row(30, 40, code="CS53"),
            row(10, 30, planned=40, code="CS54"),
        ],
        SLOTS,
        MONDAY_7AM,
    )
    assert [p.subject_code for p in plans] == ["CS54", "CS52", "CS53", "CS51"]
    assert [p.status for p in plans] == ["unrecoverable", "short", "at_risk", "safe"]
