"""Time in India: every date a student sees, and every date a mail states, is India time."""

from __future__ import annotations

from datetime import UTC, date, datetime, time, timedelta, timezone

# Colleges served are in India and there is no per-student time zone to read.
IST = timezone(timedelta(hours=5, minutes=30), "IST")


def utc_now() -> datetime:
    return datetime.now(UTC)


def aware(value: datetime) -> datetime:
    """SQLite drops the zone; every time the filter writes is UTC, so put it back."""
    return value if value.tzinfo else value.replace(tzinfo=UTC)


def to_ist(value: datetime) -> datetime:
    return aware(value).astimezone(IST)


def ist_midnight(value: datetime) -> datetime:
    """The start of that day in India, as an aware time."""
    return datetime.combine(to_ist(value).date(), time(0), IST)


def from_epoch_ms(milliseconds: int) -> datetime:
    return datetime.fromtimestamp(milliseconds / 1000, UTC)


def epoch_seconds(value: datetime) -> int:
    return int(aware(value).timestamp())


def day_text(value: date) -> str:
    """'Tue 1 Dec 2026': no leading zero, the weekday first so a misread date stands out."""
    return f"{value:%a} {value.day} {value:%b %Y}"


def clock_text(value: time) -> str:
    """'5 PM', '5:30 PM', '11:59 PM'."""
    hour = value.hour % 12 or 12
    suffix = "AM" if value.hour < 12 else "PM"
    return f"{hour} {suffix}" if value.minute == 0 else f"{hour}:{value.minute:02d} {suffix}"


def moment_text(value: datetime) -> str:
    """'Tue 1 Dec 2026, 10:12 AM' in India time."""
    local = to_ist(value)
    return f"{day_text(local.date())}, {clock_text(local.time())}"
