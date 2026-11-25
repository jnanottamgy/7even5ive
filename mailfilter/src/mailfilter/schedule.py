"""When the checks run: 1 PM and 9 PM India time by default, as EventBridge sees it (UTC)."""

from __future__ import annotations

from collections import defaultdict
from datetime import UTC, date, datetime, time, timedelta

from mailfilter.timekit import IST, to_ist


def eventbridge_crons(check_times: tuple[time, ...]) -> list[str]:
    """One EventBridge cron expression per distinct UTC minute, e.g. 'cron(30 7,15 * * ? *)'."""
    by_minute: dict[int, set[int]] = defaultdict(set)
    for local in check_times:
        utc = datetime.combine(date(2026, 1, 1), local, IST).astimezone(UTC)
        by_minute[utc.minute].add(utc.hour)
    return [
        f"cron({minute} {','.join(str(h) for h in sorted(hours))} * * ? *)"
        for minute, hours in sorted(by_minute.items())
    ]


def next_check(now: datetime, check_times: tuple[time, ...]) -> datetime:
    local = to_ist(now)
    for days in (0, 1):
        day = local.date() + timedelta(days=days)
        for at in sorted(check_times):
            moment = datetime.combine(day, at, IST)
            if moment > local:
                return moment
    raise ValueError("no check times")


def longest_gap(check_times: tuple[time, ...]) -> timedelta:
    """The longest wait between two scheduled checks, across midnight."""
    minutes = sorted(t.hour * 60 + t.minute for t in check_times)
    gaps = [b - a for a, b in zip(minutes, minutes[1:], strict=False)]
    gaps.append(minutes[0] + 24 * 60 - minutes[-1])
    return timedelta(minutes=max(gaps))
