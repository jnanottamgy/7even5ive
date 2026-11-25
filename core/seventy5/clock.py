"""One clock for the whole app, in IST.

Why: tests freeze it, and "due this week" must mean the student's week, not UTC's.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

IST = timezone(timedelta(hours=5, minutes=30))
_frozen: datetime | None = None


def now() -> datetime:
    return _frozen or datetime.now(IST)


def freeze(at: datetime | None) -> None:
    global _frozen
    _frozen = at


def iso(at: datetime) -> str:
    return at.astimezone(IST).isoformat(timespec="minutes")
