from datetime import time

import pytest
from pydantic import ValidationError

from portmax.contract import (
    AttendanceRow,
    MarkRow,
    Profile,
    TimetableSlot,
    Weekday,
)


def row(**overrides: object) -> AttendanceRow:
    fields: dict[str, object] = {
        "subject_code": "CS52",
        "subject_name": "Database Systems",
        "attended": 22,
        "held": 30,
        "percent": 73.33,
    }
    fields.update(overrides)
    return AttendanceRow.model_validate(fields)


def test_a_rounded_portal_percentage_passes() -> None:
    assert row(percent=73).percent == 73


@pytest.mark.parametrize(
    "overrides",
    [
        {"attended": 31},  # more attended than held
        {"percent": 80},  # percentage disagrees with attended/held
        {"planned": 25},  # more held than planned for the semester
        {"subject_code": "cs52"},  # codes are upper-case
    ],
)
def test_impossible_attendance_is_refused(overrides: dict[str, object]) -> None:
    with pytest.raises(ValidationError):
        row(**overrides)


def test_no_classes_held_allows_any_percentage_the_portal_prints() -> None:
    assert row(attended=0, held=0, percent=0).held == 0


def test_timetable_slot_must_end_after_it_starts() -> None:
    with pytest.raises(ValidationError):
        TimetableSlot(day=Weekday.MON, start=time(10), end=time(9), subject_code="CS52")


def test_marks_cannot_exceed_the_maximum() -> None:
    with pytest.raises(ValidationError):
        MarkRow(subject_code="CS52", component="CIE-1", scored=31, maximum=30)


def test_profile_has_no_room_for_a_name() -> None:
    with pytest.raises(ValidationError):
        Profile.model_validate(
            {"usn": "1MC24CS042", "branch": "CSE", "semester": 5, "name": "Asha"}
        )
