"""What the student and their AI apps get: the open cards, and the lines for the 7 AM briefing.

Every sentence here comes from a fixed template filled with checked fields: no model writes
anything a student reads, so nothing can be invented on the way out either.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from urllib.parse import quote

from mailfilter.config import Settings
from mailfilter.contract import Card, KeptKind, OpportunitiesAnswer
from mailfilter.errors import NotConnected
from mailfilter.schedule import longest_gap, next_check
from mailfilter.store import CardRow, Store
from mailfilter.timekit import clock_text, moment_text, to_ist

# A card with no date stays listed this long after its last mail.
UNDATED_FOR = timedelta(days=30)
NEW_FOR = timedelta(hours=24)
SOON = timedelta(hours=48)
_KIND = {"placement": "Placement", "internship": "Internship", "exam_notice": "Exam notice"}


def gmail_link(email: str | None, rfc822_id: str | None, message_id: str) -> str:
    """Opens the mail in Gmail in the right account. Best effort: Gmail's web addresses are
    not an API, so the card also carries the form link itself."""
    base = (
        f"https://mail.google.com/mail/?authuser={quote(email, safe='@')}"
        if email
        else "https://mail.google.com/mail/u/0/"
    )
    if rfc822_id:
        return f"{base}#search/rfc822msgid%3A{quote(rfc822_id.strip().strip('<>'), safe='')}"
    return f"{base}#all/{quote(message_id, safe='')}"


def _when(value: datetime, has_time: bool = True) -> str:
    local = to_ist(value)
    text = f"{local:%a} {local.day} {local:%b}"
    return f"{text}, {clock_text(local.time())}" if has_time else text


def summary(row: CardRow) -> str:
    parts = [f"{_KIND[row.kind]}: {row.title}"]
    if row.organisation and row.organisation.casefold() not in row.title.casefold():
        parts[0] += f" ({row.organisation})"
    if row.deadline is not None:
        parts.append(f"Last date {_when(row.deadline)}")
    else:
        parts.append("No last date in the mail")
    if row.event_date is not None:
        parts.append(f"Date {_when(row.event_date, row.event_has_time)}")
    return ". ".join(parts) + "."


def to_card(row: CardRow, email: str | None) -> Card:
    return Card(
        id=row.id,
        kind=row.kind,
        title=row.title,
        organisation=row.organisation,
        role=row.role,
        deadline=to_ist(row.deadline) if row.deadline else None,
        event_date=to_ist(row.event_date) if row.event_date else None,
        event_has_time=row.event_has_time,
        form_link=row.form_link,
        details=row.details,
        first_seen=to_ist(row.first_received_at),
        last_seen=to_ist(row.last_received_at),
        mails=row.mails,
        gmail_link=gmail_link(email, row.rfc822_id, row.message_id),
        summary=summary(row),
    )


def _upcoming(row: CardRow, now: datetime) -> datetime | None:
    """The next date that still matters: the deadline, else the event."""
    if row.deadline is not None and row.deadline >= now:
        return row.deadline
    if row.event_date is not None:
        event_day = to_ist(row.event_date).date()
        if event_day >= to_ist(now).date():
            return row.event_date
    return None


def is_open(row: CardRow, now: datetime) -> bool:
    if row.deadline is None and row.event_date is None:
        return row.last_received_at >= now - UNDATED_FOR
    return _upcoming(row, now) is not None


def _order(row: CardRow, now: datetime) -> tuple[int, float, float]:
    upcoming = _upcoming(row, now)
    if upcoming is not None:
        return (0, upcoming.timestamp(), -row.last_received_at.timestamp())
    return (1, -row.last_received_at.timestamp(), 0.0)


def opportunities_answer(
    store: Store,
    student_id: str,
    now: datetime,
    settings: Settings,
    *,
    kind: KeptKind | None = None,
    within_days: int | None = None,
    include_past: bool = False,
) -> OpportunitiesAnswer:
    connection = store.connection(student_id)
    if connection is None:
        raise NotConnected("college mail is not connected: connect it in the app")
    rows = [row for row in store.cards(student_id) if kind is None or row.kind == kind]
    if not include_past:
        rows = [row for row in rows if is_open(row, now)]
    if within_days is not None:
        horizon = now + timedelta(days=within_days)
        rows = [
            row
            for row in rows
            if (upcoming := _upcoming(row, now)) is not None and upcoming <= horizon
        ]
    rows.sort(key=lambda row: _order(row, now))
    last_ok = connection.last_ok_at
    stale = last_ok is None or now - last_ok > longest_gap(settings.check_times) + timedelta(
        hours=1
    )
    return OpportunitiesAnswer(
        connection=connection.status,
        checked_at=to_ist(last_ok) if last_ok else None,
        next_check_at=next_check(now, settings.check_times),
        stale=stale,
        data=[to_card(row, connection.email) for row in rows],
    )


def due_soon(store: Store, student_id: str, now: datetime, within: timedelta) -> list[CardRow]:
    """Open cards whose last date falls within `within`: what the urgent call is for."""
    return sorted(
        (
            row
            for row in store.cards(student_id)
            if row.deadline is not None and now <= row.deadline <= now + within
        ),
        key=lambda row: row.deadline or now,
    )


def briefing_lines(store: Store, student_id: str, now: datetime, settings: Settings) -> list[str]:
    """College-mail lines for the 7 AM briefing: new since yesterday, closing soon, and any
    problem with the connection. Fixed templates, at most five of each."""
    connection = store.connection(student_id)
    if connection is None:
        return []
    lines: list[str] = []
    if connection.status == "needs_reconnect":
        lines.append(
            "Your college mail needs reconnecting: sign in again in the app to keep getting "
            "placement and exam mail."
        )
    elif connection.status == "college_blocked":
        lines.append(
            "Your college's Google settings stop 7even5ive reading your mail. The app shows how "
            "to forward placement and exam mail instead."
        )
    open_rows = sorted(
        (row for row in store.cards(student_id) if is_open(row, now)),
        key=lambda row: _order(row, now),
    )
    new = [row for row in open_rows if row.created_at >= now - NEW_FOR]
    soon = [
        row
        for row in open_rows
        if row not in new and row.deadline is not None and now <= row.deadline <= now + SOON
    ]
    lines += [f"New from college mail: {summary(row)}" for row in new[:5]]
    if len(new) > 5:
        lines.append(f"And {len(new) - 5} more new from college mail in the app.")
    lines += [f"Closing soon: {summary(row)}" for row in soon[:5]]
    last_ok = connection.last_ok_at
    if connection.status == "connected" and (
        last_ok is None or now - last_ok > longest_gap(settings.check_times) + timedelta(hours=1)
    ):
        when = moment_text(last_ok) if last_ok else "not yet"
        lines.append(f"College mail was last checked: {when}.")
    return lines
