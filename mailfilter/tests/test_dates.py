from __future__ import annotations

from datetime import date, time

import pytest

from mailfilter.dates import mentions

TUESDAY = date(2026, 12, 1)


@pytest.mark.parametrize(
    ("quote", "dates", "times"),
    [
        ("on or before Thursday, 3 December 2026, 5:00 PM", ["2026-12-03"], ["17:00"]),
        ("extended to Sat 5 Dec, 11:59 PM", ["2026-12-05"], ["23:59"]),
        ("till 5th Dec 2026", ["2026-12-05"], []),
        ("Last date: 04-12-2026, 11:00 AM", ["2026-12-04"], ["11:00"]),
        ("apply by 15/12/2026", ["2026-12-15"], []),
        ("Deadline 03/12/26 17:00 hrs", ["2026-12-03"], ["17:00"]),
        ("1700 hrs on 3 Dec", ["2026-12-03"], ["17:00"]),
        ("December 3rd, 2026 at 5 p.m.", ["2026-12-03"], ["17:00"]),
        ("3 Dec, 10 AM", ["2026-12-03"], ["10:00"]),  # 10 is a time here, not the year 2010
        ("2026-12-09", ["2026-12-09"], []),
        ("by tomorrow 9 AM", ["2026-12-02"], ["09:00"]),
        ("day after tomorrow, noon", ["2026-12-03"], ["12:00"]),
        ("by EOD today", ["2026-12-01"], ["23:59"]),
        ("by midnight on 4 December", ["2026-12-04"], ["23:59"]),
        ("on 5 Jan", ["2027-01-05"], []),  # no year: the next 5 January
        ("closed on 28 Nov", ["2026-11-28"], []),  # recent past stays this year
        ("this Friday", ["2026-12-04"], []),
        ("next Friday", ["2026-12-04", "2026-12-11"], []),  # ambiguous: both readings
        ("15 marks out of 20", [], []),  # "marks" is not March
        ("10.30 a.m. sharp", [], ["10:30"]),
        ("by 12 AM", [], ["00:00"]),
        ("13/25/2026", [], []),  # no such date either way
        ("12/25/2026", ["2026-12-25"], []),  # day first impossible: month first
    ],
)
def test_what_a_quote_can_mean(quote: str, dates: list[str], times: list[str]) -> None:
    found = mentions(quote, TUESDAY)
    assert sorted(d.isoformat() for d in found.dates) == dates
    assert sorted(t.strftime("%H:%M") for t in found.times) == times


def test_a_year_end_date_without_a_year_rolls_over() -> None:
    found = mentions("by 5 Jan", date(2026, 12, 28))
    assert found.dates == frozenset({date(2027, 1, 5)})
    assert mentions("by 5 PM", date(2026, 12, 28)).times == frozenset({time(17, 0)})
