"""The dates and times a quote actually names, so a date Claude proposes can be checked.

Claude says "deadline 2026-12-03T17:00, from 'on or before Thursday, 3 December 2026, 5 PM'".
This module reads the quote itself and finds which dates and times it can mean; the check then
insists Claude's date is one of them. An off-by-one day, a wrong month or a time the quote never
states fails, and a wrong date is worse than no date, so the field is dropped.

Day-first numeric dates (03/12/2026) are read the Indian way. A date without a year is the
nearest one: the next such date, or a recent one (within 60 days) when that is nearer, so
"28 Dec" read on 2 January is last December. Relative words ("today", "tomorrow", "EOD") and
weekdays are read from the day the mail arrived; a weekday next to an explicit date adds
nothing. Ranges ("14-23 December", "Dec 3-5", "10-11 AM", "9.30-12.30") name both ends.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date, time, timedelta
from email.utils import parsedate_to_datetime

from mailfilter.timekit import IST

_MONTHS = {
    "jan": 1, "feb": 2, "mar": 3, "apr": 4, "may": 5, "jun": 6,
    "jul": 7, "aug": 8, "sep": 9, "oct": 10, "nov": 11, "dec": 12,
}  # fmt: skip
# A month name never runs into more letters: "marks" and "decimal" are not months.
_MONTH = (
    r"(jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|june?|july?|aug(?:ust)?"
    r"|sep(?:t(?:ember)?)?|oct(?:ober)?|nov(?:ember)?|dec(?:ember)?)(?![a-z])\.?"
)
_WEEKDAYS = {
    "mon": 0, "tue": 1, "wed": 2, "thu": 3, "fri": 4, "sat": 5, "sun": 6,
}  # fmt: skip
_WEEKDAY = (
    r"\b(mon(?:day)?|tue(?:s(?:day)?)?|wed(?:nesday)?|thu(?:r(?:s(?:day)?)?)?|fri(?:day)?"
    r"|sat(?:urday)?|sun(?:day)?)\b\.?"
)
_ORD = r"(?:st|nd|rd|th)?"
_TO = r"(?:-|to|till|until|through)"
# A four-digit year is 19xx or 20xx and never a time: "3 Dec 1700 hrs" is five in the evening.
_YEAR4 = r"((?:19|20)\d{2})\b(?!\s*(?:hrs?|hours)\b)"
# After a month: a four-digit year after any separator, or two digits only straight after an
# apostrophe, dash or slash ("Dec'26", "Dec-26"), so "3 Dec, 10 AM" is not the year 2010.
_YEAR = rf"(?:,?[\s\-./]*{_YEAR4}|[\-/']\s?(\d{{2}})\b(?![:.]\d|\s*[ap]\.?m))"

_ISO = re.compile(r"\b((?:19|20)\d{2})-(\d{1,2})-(\d{1,2})\b")
# Both separators the same, and not the start of a time: "9.30-12.30" is not a date.
_NUMERIC = re.compile(r"\b(\d{1,2})([/.\-])(\d{1,2})\2((?:19|20)\d{2}|\d{2})\b(?![.:]\d)")
_DAY_RANGE = re.compile(rf"\b(\d{{1,2}}){_ORD}\s*{_TO}\s*(\d{{1,2}}){_ORD}(?:\s+of)?[\s\-./,]*"
                        rf"{_MONTH}{_YEAR}?")  # fmt: skip
_MONTH_RANGE = re.compile(rf"\b{_MONTH}[\s\-.]*(\d{{1,2}}){_ORD}\s*{_TO}\s*(\d{{1,2}}){_ORD}\b"
                          rf"(?:,?\s*{_YEAR4})?")  # fmt: skip
_DAY_MONTH = re.compile(rf"\b(\d{{1,2}}){_ORD}(?:\s+of)?[\s\-./,]*{_MONTH}{_YEAR}?")
_MONTH_DAY = re.compile(rf"\b{_MONTH}[\s\-.]*(\d{{1,2}}){_ORD}\b(?:,?\s*{_YEAR4})?")
_DAY_SLASH_MONTH = re.compile(r"\b(\d{1,2})/(\d{1,2})\b(?![/.\-]\d)")
_WEEKDAY_RE = re.compile(_WEEKDAY)
_NEXT_WEEKDAY = re.compile(rf"\bnext\s+{_WEEKDAY}")

_MERIDIEM = r"(a\.?m\.?|p\.?m\.?)(?![a-z])"
_TIME_RANGE = re.compile(rf"\b(\d{{1,2}})(?:[:.](\d{{2}}))?\s*{_TO}\s*(\d{{1,2}})(?:[:.](\d{{2}}))?"
                         rf"\s*{_MERIDIEM}")  # fmt: skip
_CLOCK = re.compile(rf"\b(\d{{1,2}})(?:[:.](\d{{2}}))?\s*{_MERIDIEM}")
_TWENTY_FOUR = re.compile(r"\b([01]?\d|2[0-3])[:.]([0-5]\d)(?!\d)(?!\s*(?:a\.?m|p\.?m))")
_HOURS = re.compile(r"\b([01]\d|2[0-3])([0-5]\d)\s*(?:hrs?|hours|h)\b")
_DASHES = dict.fromkeys(map(ord, "‐‑‒–—―−"), "-")

END_OF_DAY = time(23, 59)
RECENT = timedelta(days=60)


@dataclass(frozen=True)
class Mentions:
    dates: frozenset[date]
    times: frozenset[time]


def _make(year: int, month: int, day: int) -> date | None:
    try:
        return date(year, month, day)
    except ValueError:
        return None


def _resolve(raw_year: str | None, month: int, day: int, received: date) -> date | None:
    """The date meant: the stated year, else the nearest such date (see the module docstring)."""
    if raw_year:
        digits = raw_year.lstrip("'")
        return _make(2000 + int(digits) if len(digits) == 2 else int(digits), month, day)
    found = [
        _make(year, month, day) for year in (received.year - 1, received.year, received.year + 1)
    ]
    candidates = [d for d in found if d is not None]
    past = max((d for d in candidates if d < received), default=None)
    future = min((d for d in candidates if d >= received), default=None)
    if (
        past is not None
        and received - past <= RECENT
        and (future is None or received - past < future - received)
    ):
        return past
    return future if future is not None else past


def _blank(text: str, pattern: re.Pattern[str]) -> str:
    return pattern.sub(lambda match: " " * len(match.group(0)), text)


def _clock(hour: int, minute: int, meridiem: str) -> time | None:
    if not 1 <= hour <= 12 or minute > 59:
        return None
    return time(hour % 12 + (12 if meridiem.startswith("p") else 0), minute)


def mentions(quote: str, received: date) -> Mentions:
    """Every date and time the quote can mean, given the day the mail arrived."""
    text = quote.translate(_DASHES).lower()
    found: set[date] = set()

    def add(value: date | None) -> None:
        if value is not None:
            found.add(value)

    for match in _ISO.finditer(text):
        add(_make(int(match.group(1)), int(match.group(2)), int(match.group(3))))
    text = _blank(text, _ISO)

    for match in _NUMERIC.finditer(text):
        first, second, raw_year = int(match.group(1)), int(match.group(3)), match.group(4)
        full_year = 2000 + int(raw_year) if len(raw_year) == 2 else int(raw_year)
        # Day first, the Indian way; month first only when day first cannot be a date.
        add(_make(full_year, second, first) or _make(full_year, first, second))
    text = _blank(text, _NUMERIC)

    for match in _DAY_RANGE.finditer(text):
        month, stated = _MONTHS[match.group(3)[:3]], match.group(4) or match.group(5)
        for day in (int(match.group(1)), int(match.group(2))):
            add(_resolve(stated, month, day, received))
    text = _blank(text, _DAY_RANGE)

    for match in _MONTH_RANGE.finditer(text):
        month = _MONTHS[match.group(1)[:3]]
        for day in (int(match.group(2)), int(match.group(3))):
            add(_resolve(match.group(4), month, day, received))
    text = _blank(text, _MONTH_RANGE)

    for match in _DAY_MONTH.finditer(text):
        month = _MONTHS[match.group(2)[:3]]
        add(_resolve(match.group(3) or match.group(4), month, int(match.group(1)), received))
    text = _blank(text, _DAY_MONTH)

    for match in _MONTH_DAY.finditer(text):
        add(_resolve(match.group(3), _MONTHS[match.group(1)[:3]], int(match.group(2)), received))
    text = _blank(text, _MONTH_DAY)

    for match in _DAY_SLASH_MONTH.finditer(text):
        add(_resolve(None, int(match.group(2)), int(match.group(1)), received))
    text = _blank(text, _DAY_SLASH_MONTH)

    if re.search(r"\bday after tomorrow\b", text):
        found.add(received + timedelta(days=2))
    elif re.search(r"\btomorrow\b", text):
        found.add(received + timedelta(days=1))
    if re.search(r"\b(today|tonight|eod)\b|\bend of (?:the )?day\b", text):
        found.add(received)

    if not found:
        # A weekday counts only when nothing more exact is named beside it.
        for match in _NEXT_WEEKDAY.finditer(text):
            ahead = (_WEEKDAYS[match.group(1)[:3]] - received.weekday()) % 7
            found.add(received + timedelta(days=ahead + 7))
        for match in _WEEKDAY_RE.finditer(text):
            ahead = (_WEEKDAYS[match.group(1)[:3]] - received.weekday()) % 7
            found.add(received + timedelta(days=ahead))

    times: set[time] = set()
    if re.search(r"\beod\b|\bend of (?:the )?day\b|\bmidnight\b", text):
        times.add(END_OF_DAY)
    if re.search(r"\bnoon\b|\bmidday\b", text):
        times.add(time(12, 0))
    for match in _TIME_RANGE.finditer(text):
        meridiem = match.group(5)
        end = _clock(int(match.group(3)), int(match.group(4) or 0), meridiem)
        start = _clock(int(match.group(1)), int(match.group(2) or 0), meridiem)
        if end is None or start is None:
            continue
        if start > end:  # "11-1 PM": the start is in the morning
            start = _clock(int(match.group(1)), int(match.group(2) or 0), "am") or start
        times.update({start, end})
    text = _blank(text, _TIME_RANGE)
    for match in _CLOCK.finditer(text):
        clock = _clock(int(match.group(1)), int(match.group(2) or 0), match.group(3))
        if clock is not None:
            times.add(clock)
    text = _blank(text, _CLOCK)
    for match in _TWENTY_FOUR.finditer(text):
        times.add(time(int(match.group(1)), int(match.group(2))))
    for match in _HOURS.finditer(text):
        times.add(time(int(match.group(1)), int(match.group(2))))
    return Mentions(dates=frozenset(found), times=frozenset(times))


def moment_named(text: str, received: date) -> tuple[date, time | None] | None:
    """The one date (and time) a header line such as a forward's "Date:" names, if exactly one."""
    try:
        parsed = parsedate_to_datetime(text.strip())
    except (TypeError, ValueError, IndexError):
        parsed = None
    if parsed is not None:
        if parsed.tzinfo is not None:
            parsed = parsed.astimezone(IST)
        return parsed.date(), parsed.time().replace(second=0, microsecond=0)
    said = mentions(text, received)
    if len(said.dates) != 1:
        return None
    clock = next(iter(said.times)) if len(said.times) == 1 else None
    return next(iter(said.dates)), clock
