"""The dates and times a quote actually names, so a date Claude proposes can be checked.

Claude says "deadline 2026-12-03T17:00, from 'on or before Thursday, 3 December 2026, 5 PM'".
This module reads the quote itself and finds which dates and times it can mean; the check then
insists Claude's date is one of them. An off-by-one day, a wrong month or a time the quote never
states fails, and a wrong date is worse than no date, so the field is dropped.

Day-first numeric dates (03/12/2026) are read the Indian way. Relative words ("today",
"tomorrow", "EOD") and weekdays are read from the day the mail arrived.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date, time, timedelta

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
# A year after a month: four digits after any separator, or two digits only straight after
# an apostrophe, dash or slash ("Dec'26", "Dec-26"), so "3 Dec, 10 AM" is not the year 2010.
_YEAR = r"(?:,?[\s\-./]*(\d{4})\b|[\-/']\s?(\d{2})\b(?![:.]\d|\s*[ap]\.?m))"

_DAY_MONTH = re.compile(rf"\b(\d{{1,2}}){_ORD}(?:\s+of)?[\s\-./,]*{_MONTH}{_YEAR}?", re.IGNORECASE)
_MONTH_DAY = re.compile(rf"\b{_MONTH}[\s\-.]*(\d{{1,2}}){_ORD}\b(?:,?\s*(\d{{4}})\b)?", re.I)
_ISO = re.compile(r"\b(\d{4})-(\d{1,2})-(\d{1,2})\b")
_NUMERIC = re.compile(r"\b(\d{1,2})[/.\-](\d{1,2})[/.\-](\d{4}|\d{2})\b")
_DAY_SLASH_MONTH = re.compile(r"\b(\d{1,2})/(\d{1,2})\b(?![/.\-]\d)")
_WEEKDAY_RE = re.compile(_WEEKDAY, re.IGNORECASE)
_NEXT_WEEKDAY = re.compile(rf"\bnext\s+{_WEEKDAY}", re.IGNORECASE)

_CLOCK = re.compile(r"\b(\d{1,2})(?:[:.](\d{2}))?\s*(a\.?m\.?|p\.?m\.?)(?![a-z])", re.IGNORECASE)
_TWENTY_FOUR = re.compile(r"\b([01]?\d|2[0-3])[:.]([0-5]\d)\b(?!\s*(?:a\.?m|p\.?m))", re.I)
_HOURS = re.compile(r"\b([01]\d|2[0-3])([0-5]\d)\s*(?:hrs|hours|h)\b", re.IGNORECASE)

END_OF_DAY = time(23, 59)


@dataclass(frozen=True)
class Mentions:
    dates: frozenset[date]
    times: frozenset[time]


def _year(raw: str | None, month: int, day: int, received: date) -> list[int]:
    if raw:
        digits = raw.lstrip("'")
        return [2000 + int(digits) if len(digits) == 2 else int(digits)]
    # No year: this year's date, unless that is more than a month gone; then next year's.
    try:
        this_year = date(received.year, month, day)
    except ValueError:
        return [received.year + 1]
    return [received.year] if this_year >= received - timedelta(days=30) else [received.year + 1]


def _add(found: set[date], year: int, month: int, day: int) -> bool:
    try:
        found.add(date(year, month, day))
    except ValueError:
        return False
    return True


def _blank(text: str, pattern: re.Pattern[str]) -> str:
    return pattern.sub(lambda match: " " * len(match.group(0)), text)


def mentions(quote: str, received: date) -> Mentions:
    """Every date and time the quote can mean, given the day the mail arrived."""
    text = quote.lower()
    found: set[date] = set()

    for match in _ISO.finditer(text):
        _add(found, int(match.group(1)), int(match.group(2)), int(match.group(3)))
    text = _blank(text, _ISO)

    for match in _NUMERIC.finditer(text):
        first, second, raw_year = int(match.group(1)), int(match.group(2)), match.group(3)
        year = 2000 + int(raw_year) if len(raw_year) == 2 else int(raw_year)
        # Day first, the Indian way; month first only when day first cannot be a date.
        if not _add(found, year, second, first):
            _add(found, year, first, second)
    text = _blank(text, _NUMERIC)

    for match in _DAY_MONTH.finditer(text):
        day, month = int(match.group(1)), _MONTHS[match.group(2)[:3]]
        for year in _year(match.group(3) or match.group(4), month, day, received):
            _add(found, year, month, day)
    text = _blank(text, _DAY_MONTH)

    for match in _MONTH_DAY.finditer(text):
        month, day = _MONTHS[match.group(1)[:3]], int(match.group(2))
        for year in _year(match.group(3), month, day, received):
            _add(found, year, month, day)
    text = _blank(text, _MONTH_DAY)

    for match in _DAY_SLASH_MONTH.finditer(text):
        day, month = int(match.group(1)), int(match.group(2))
        for year in _year(None, month, day, received):
            _add(found, year, month, day)
    text = _blank(text, _DAY_SLASH_MONTH)

    for match in _WEEKDAY_RE.finditer(text):
        target = _WEEKDAYS[match.group(1)[:3]]
        ahead = (target - received.weekday()) % 7
        found.add(received + timedelta(days=ahead))
    for match in _NEXT_WEEKDAY.finditer(text):
        target = _WEEKDAYS[match.group(1)[:3]]
        ahead = (target - received.weekday()) % 7
        found.add(received + timedelta(days=ahead + 7))

    times: set[time] = set()
    if re.search(r"\bday after tomorrow\b", text):
        found.add(received + timedelta(days=2))
    elif re.search(r"\btomorrow\b", text):
        found.add(received + timedelta(days=1))
    if re.search(r"\b(today|tonight|eod)\b|\bend of (?:the )?day\b", text):
        found.add(received)
    if re.search(r"\beod\b|\bend of (?:the )?day\b|\bmidnight\b", text):
        times.add(END_OF_DAY)
    if re.search(r"\bnoon\b|\bmidday\b", text):
        times.add(time(12, 0))

    for match in _CLOCK.finditer(text):
        hour, minute = int(match.group(1)), int(match.group(2) or 0)
        if not 1 <= hour <= 12 or minute > 59:
            continue
        evening = match.group(3).startswith("p")
        times.add(time(hour % 12 + (12 if evening else 0), minute))
    text = _blank(text, _CLOCK)
    for match in _TWENTY_FOUR.finditer(text):
        times.add(time(int(match.group(1)), int(match.group(2))))
    for match in _HOURS.finditer(text):
        times.add(time(int(match.group(1)), int(match.group(2))))
    return Mentions(dates=frozenset(found), times=frozenset(times))
