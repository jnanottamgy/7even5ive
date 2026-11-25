"""Regressions for the independent review of 25 Nov: each test failed before its fix."""

from __future__ import annotations

from datetime import date, datetime, time

import pytest

from mailfilter.checks import check
from mailfilter.config import Settings
from mailfilter.contract import OTHER, Proposal
from mailfilter.dates import mentions
from mailfilter.errors import JudgeFailed
from mailfilter.fake import STUDENT_ADDRESS, FakeMail, FakeMailbox, build_raw
from mailfilter.judge import ScriptedJudge
from mailfilter.mail import render
from mailfilter.run import check_mailbox
from mailfilter.samples import BY_KEY, SAMPLES, fake_mails, proposal
from mailfilter.store import Store
from mailfilter.timekit import IST
from tests.conftest import MONDAY, STUDENT, Clock

TPO = "Training & Placement Office <placements@mockcollege.edu.in>"


def at(day: int, hour: int, minute: int = 0) -> datetime:
    return datetime(2026, 11 if day >= 28 else 12, day, hour, minute, tzinfo=IST)


def mail(number: int, when: datetime, subject: str, text: str, thread: str | None = None,
         sender: str = TPO) -> FakeMail:  # fmt: skip
    raw = build_raw(sender=sender, subject=subject, received_at=when,
                    message_id=f"<r{number}@mockcollege.edu.in>", plain=text)  # fmt: skip
    return FakeMail(f"{number:016x}", thread or f"thread{number}", when, raw)


def marker(subject: str, sender: str = TPO) -> str:
    return f"\nFrom: {sender}\nSubject: {subject}\n"


def run_all(store: Store, settings: Settings, clock: Clock, mails: list[FakeMail],
            answers: dict[str, Proposal | Exception]) -> None:  # fmt: skip
    store.connect(STUDENT, STUDENT_ADDRESS, MONDAY)
    check_mailbox(store, FakeMailbox(mails, now=clock), ScriptedJudge(answers), STUDENT,
                  settings, now=clock)  # fmt: skip


# 2a. A forwarded update (the placement office forwarding the company's extension) must win.
def test_a_forwarded_extension_moves_the_deadline(
    store: Store, settings: Settings, clock: Clock
) -> None:
    link = "https://forms.gle/Zenith27"
    first = mail(1, at(1, 10), "Zenith Labs drive", f"Register at {link} by 3 Dec 2026, 5 PM.")
    forwarded = (
        "Please note.\n\n---------- Forwarded message ---------\nFrom: Zenith HR "
        "<hr@zenith.example.com>\nDate: Wed, 2 Dec 2026 at 08:30\nSubject: Deadline extended"
        f"\n\nThe deadline is extended to 6 Dec 2026, 5 PM. Form: {link}"
    )
    update = mail(2, at(2, 9), "Fwd: Zenith Labs drive – deadline extended", forwarded)
    answers: dict[str, Proposal | Exception] = {
        marker("Zenith Labs drive"): proposal(
            "placement", "Zenith Labs drive", organisation="Zenith Labs",
            deadline=("2026-12-03T17:00", "by 3 Dec 2026, 5 PM"), link=link),
        marker("Fwd: Zenith Labs drive – deadline extended"): proposal(
            "placement", "Zenith Labs drive", organisation="Zenith Labs",
            deadline=("2026-12-06T17:00", "extended to 6 Dec 2026, 5 PM"), link=link),
    }  # fmt: skip
    run_all(store, settings, clock, [first, update], answers)
    [card] = store.cards(STUDENT)
    assert card.deadline == at(6, 17)


# 2b. A reminder judged late (after a stale forward) must still update the card.
def test_a_reminder_judged_late_still_wins(store: Store, settings: Settings, clock: Clock) -> None:
    store.connect(STUDENT, STUDENT_ADDRESS, MONDAY)
    answers: dict[str, Proposal | Exception] = {s.marker: s.golden for s in SAMPLES}
    reminder = BY_KEY["nimbus_reminder"]
    flaky = ScriptedJudge({**answers, reminder.marker: JudgeFailed("max_tokens")})
    mailbox = FakeMailbox(fake_mails(), now=clock)
    check_mailbox(store, mailbox, flaky, STUDENT, settings, now=clock)
    clock.advance(hours=12)
    check_mailbox(store, mailbox, ScriptedJudge(answers), STUDENT, settings, now=clock)
    nimbus = next(c for c in store.cards(STUDENT) if c.title == "Nimbus Systems Campus Drive")
    assert nimbus.deadline == at(5, 23, 59)
    assert nimbus.event_date == at(7, 10)
    assert nimbus.message_id == reminder.mail.id


# 3a. Two drives that both point at the same placement portal stay two cards.
def test_a_shared_portal_link_does_not_merge_drives(
    store: Store, settings: Settings, clock: Clock
) -> None:
    portal = "https://app.joinsuperset.example.com/students/login"
    infosys = mail(1, at(1, 10), "Infosys campus drive", f"Apply on Superset {portal} by 4 Dec.")
    tcs = mail(2, at(1, 11), "TCS Ninja hiring", f"Apply on Superset {portal} by 9 Dec 2026, 5 PM.")
    answers: dict[str, Proposal | Exception] = {
        marker("Infosys campus drive"): proposal(
            "placement", "Infosys campus drive", organisation="Infosys",
            deadline=("2026-12-04T23:59", "by 4 Dec"), link=portal),
        marker("TCS Ninja hiring"): proposal(
            "placement", "TCS Ninja hiring", organisation="TCS", role="Ninja",
            deadline=("2026-12-09T17:00", "by 9 Dec 2026, 5 PM"), link=portal),
    }  # fmt: skip
    run_all(store, settings, clock, [infosys, tcs], answers)
    cards = {c.title: c for c in store.cards(STUDENT)}
    assert set(cards) == {"Infosys campus drive", "TCS Ninja hiring"}
    assert cards["Infosys campus drive"].deadline == at(4, 23, 59)


# 3b. A reminder in the same conversation that leaves out the link updates the same card.
def test_a_reminder_without_the_link_updates_the_same_card(
    store: Store, settings: Settings, clock: Clock
) -> None:
    link = "https://forms.gle/Orion27"
    first = mail(1, at(1, 10), "Orion Tech drive", f"Register at {link} by 3 Dec 2026, 5 PM.",
                 thread="t-orion")  # fmt: skip
    again = mail(2, at(2, 10), "Re: Orion Tech drive", "Reminder: the last date is now 5 Dec.",
                 thread="t-orion")  # fmt: skip
    answers: dict[str, Proposal | Exception] = {
        marker("Orion Tech drive"): proposal(
            "placement", "Orion Tech drive", organisation="Orion Tech",
            deadline=("2026-12-03T17:00", "by 3 Dec 2026, 5 PM"), link=link),
        marker("Re: Orion Tech drive"): proposal(
            "placement", "Orion Tech drive", deadline=("2026-12-05T23:59", "now 5 Dec")),
    }  # fmt: skip
    run_all(store, settings, clock, [first, again], answers)
    [card] = store.cards(STUDENT)
    assert card.deadline == at(5, 23, 59) and card.form_link == link and card.mails == 2


# 4. A malformed link from Claude costs the link, not the notice.
@pytest.mark.parametrize("link", ["https://[insert form link here]", "https://[forms.gle/abc"])
def test_a_malformed_link_is_dropped_not_fatal(link: str) -> None:
    sample = BY_KEY["nimbus_drive"]
    message = FakeMailbox([sample.mail]).get(sample.mail.id)
    assert message is not None
    result = check(sample.golden.model_copy(update={"form_link": link}), message,
                   render(message).checkable)  # fmt: skip
    assert result.form_link is None and result.rejected == ("form_link:bad_link",)
    assert result.deadline is not None


# 7. A link must match a link in the mail exactly, not a piece of one.
def test_a_partial_link_is_refused() -> None:
    sample = BY_KEY["nimbus_drive"]
    message = FakeMailbox([sample.mail]).get(sample.mail.id)
    assert message is not None
    result = check(sample.golden.model_copy(update={"form_link": "https://forms.gle/Nimbus"}),
                   message, render(message).checkable)  # fmt: skip
    assert result.form_link is None and result.rejected == ("form_link:not_in_mail",)


TUESDAY = date(2026, 12, 1)


# 5 and 6. Ranges, and times written with "hrs".
@pytest.mark.parametrize(
    ("quote", "dates", "times"),
    [
        ("SEE from 14-23 December 2026", ["2026-12-14", "2026-12-23"], []),
        ("7th-9th Dec", ["2026-12-07", "2026-12-09"], []),
        ("Dec 3-5", ["2026-12-03", "2026-12-05"], []),
        ("14th to 23rd December", ["2026-12-14", "2026-12-23"], []),
        ("on 5 Dec, 10-11 AM", ["2026-12-05"], ["10:00", "11:00"]),
        ("2-4 PM", [], ["14:00", "16:00"]),
        ("11-1 PM", [], ["11:00", "13:00"]),
        ("on 14 Dec 2026, 9.30-12.30", ["2026-12-14"], ["09:30", "12:30"]),
        ("2.00-5.00 PM", [], ["14:00", "17:00"]),
        ("Report by 3 Dec 1700 hrs", ["2026-12-03"], ["17:00"]),
        ("Dec 3 1700 hrs", ["2026-12-03"], ["17:00"]),
        ("by 0930 hrs on 3 Dec", ["2026-12-03"], ["09:30"]),
        ("3 Dec, 17:00hrs", ["2026-12-03"], ["17:00"]),
        ("3 Dec, 09:30hrs", ["2026-12-03"], ["09:30"]),
    ],
)
def test_ranges_and_hours(quote: str, dates: list[str], times: list[str]) -> None:
    found = mentions(quote, TUESDAY)
    assert sorted(d.isoformat() for d in found.dates) == dates
    assert sorted(t.strftime("%H:%M") for t in found.times) == times


# 9a. A weekday next to an explicit date does not add "the coming weekday".
def test_a_weekday_beside_a_date_adds_nothing() -> None:
    found = mentions("Registration closes Friday, 11 December 2026", TUESDAY)
    assert found.dates == frozenset({date(2026, 12, 11)})


# 9b. A date without a year is the nearest one, so late December read in January is last year.
def test_a_recent_date_across_new_year_is_last_year() -> None:
    assert mentions("began on 28 Dec", date(2027, 1, 2)).dates == frozenset({date(2026, 12, 28)})
    assert mentions("closes 5 Jan", date(2026, 12, 28)).dates == frozenset({date(2027, 1, 5)})
    assert mentions("due 15 Feb", date(2026, 12, 1)).dates == frozenset({date(2027, 2, 15)})


# 10. Disconnecting in the middle of a check leaves nothing behind.
def test_disconnecting_mid_check_leaves_nothing(
    store: Store, settings: Settings, clock: Clock
) -> None:
    store.connect(STUDENT, STUDENT_ADDRESS, MONDAY)
    answers: dict[str, Proposal | Exception] = {s.marker: s.golden for s in SAMPLES}

    class Disconnects(ScriptedJudge):
        def judge(self, rendered: str) -> Proposal:
            if BY_KEY["revaluation"].marker in rendered:
                store.forget(STUDENT)
            return super().judge(rendered)

    check_mailbox(store, FakeMailbox(fake_mails(), now=clock), Disconnects(answers), STUDENT,
                  settings, now=clock)  # fmt: skip
    with store.engine.connect() as db:
        dumped = "\n".join(db.connection.iterdump())  # type: ignore[attr-defined]
    assert STUDENT not in dumped


def test_other_is_still_other() -> None:
    assert OTHER.kind == "other" and time(0) == time(0)


# 8. A mail the student rescues from spam keeps its old date: Gmail's history brings it in.
def test_a_mail_rescued_from_spam_is_read(store: Store, settings: Settings, clock: Clock) -> None:
    from dataclasses import replace

    store.connect(STUDENT, STUDENT_ADDRESS, MONDAY)
    drive = BY_KEY["nimbus_drive"]
    mails = [replace(m, labels=frozenset({"SPAM"})) if m.id == drive.mail.id else m
             for m in fake_mails()]  # fmt: skip
    mailbox = FakeMailbox(mails, now=clock)
    judge = ScriptedJudge({s.marker: s.golden for s in SAMPLES})
    for moment in (at(30, 13), at(30, 21), at(1, 13)):
        clock.set(moment)
        check_mailbox(store, mailbox, judge, STUDENT, settings, now=clock)
    assert drive.marker not in judge.calls  # in spam: never judged, never recorded
    clock.set(at(1, 18))
    mailbox.move_to_inbox(drive.mail.id)  # Monday's mail, rescued on Tuesday evening
    clock.set(at(1, 21))
    check_mailbox(store, mailbox, judge, STUDENT, settings, now=clock)
    assert judge.calls.count(drive.marker) == 1
    nimbus = next(c for c in store.cards(STUDENT) if c.title == "Nimbus Systems Campus Drive")
    assert nimbus.role == "Graduate Engineer Trainee"  # only the rescued mail names the role


def test_expired_history_falls_back_to_the_window(
    store: Store, settings: Settings, clock: Clock
) -> None:
    store.connect(STUDENT, STUDENT_ADDRESS, MONDAY)
    mailbox = FakeMailbox(fake_mails(), now=clock)
    clock.set(at(30, 13))
    check_mailbox(store, mailbox, ScriptedJudge({}), STUDENT, settings, now=clock)
    mailbox.history_floor = 10**9  # Google dropped the history
    clock.set(at(30, 21))
    result = check_mailbox(store, mailbox, ScriptedJudge({}), STUDENT, settings, now=clock)
    assert result.error is None and result.listed > 0


# 1. A listing too large to read in full stops the check; it never cuts off the oldest mail.
def test_a_listing_too_large_stops_without_moving_the_start(
    store: Store, settings: Settings, clock: Clock
) -> None:
    from mailfilter.errors import GmailUnavailable

    store.connect(STUDENT, STUDENT_ADDRESS, MONDAY)
    mailbox = FakeMailbox(fake_mails(), now=clock,
                          list_error=GmailUnavailable("listing_too_large"))  # fmt: skip
    result = check_mailbox(store, mailbox, ScriptedJudge({}), STUDENT, settings, now=clock)
    connection = store.connection(STUDENT)
    assert result.error == "gmail_unavailable"
    assert connection is not None and connection.checked_through == MONDAY


# 11. A check that overran its lease stops, never undoes the check that took over, and a
# running check refuses a second one.
def test_a_check_that_overran_its_lease_stops_cleanly(
    store: Store, settings: Settings, clock: Clock
) -> None:
    from mailfilter.errors import CheckInProgress
    from mailfilter.run import check_now

    store.connect(STUDENT, STUDENT_ADDRESS, MONDAY)
    answers: dict[str, Proposal | Exception] = {s.marker: s.golden for s in SAMPLES}
    mailbox = FakeMailbox(fake_mails(), now=clock)
    taken_over: list[object] = []

    class Stalls(ScriptedJudge):
        def judge(self, rendered: str) -> Proposal:
            if BY_KEY["see_timetable"].marker in rendered and not taken_over:
                with pytest.raises(CheckInProgress):  # the lease is renewed: no second check
                    check_now(store, mailbox, ScriptedJudge(answers), STUDENT, settings,
                              now=clock, force=True)  # fmt: skip
                clock.advance(minutes=11)  # this call hangs past the lease...
                taken_over.append(  # ...and the next scheduled check takes over
                    check_mailbox(store, mailbox, ScriptedJudge(answers), STUDENT, settings,
                                  now=clock))  # fmt: skip
            return super().judge(rendered)

    first = check_mailbox(store, mailbox, Stalls(answers), STUDENT, settings, now=clock)
    assert first.error == "lease_lost"
    connection = store.connection(STUDENT)
    assert connection is not None and connection.checked_through == clock()  # not moved back
    nimbus = next(c for c in store.cards(STUDENT) if c.title == "Nimbus Systems Campus Drive")
    assert nimbus.mails == 3 and len(store.cards(STUDENT)) == 17  # nothing merged twice
    assert store.acquire(STUDENT, clock(), settings.lease)  # the stale check left no lock


def test_the_whole_check_through_gmails_rest_api(
    store: Store, settings: Settings, clock: Clock
) -> None:
    """Listing, history and raw mail over Gmail's own JSON, through the real client."""
    from dataclasses import replace

    from mailfilter.gmail import GmailMailbox
    from tests.conftest import GmailFake

    store.connect(STUDENT, STUDENT_ADDRESS, MONDAY)
    drive = BY_KEY["nimbus_drive"]
    fake = GmailFake([replace(m, labels=frozenset({"SPAM"})) if m.id == drive.mail.id else m
                      for m in fake_mails()], page_size=7)  # fmt: skip
    box = GmailMailbox(lambda fresh: "token", fake.client(), settings.max_text_chars,
                       sleep=lambda s: None, jitter=lambda: 0.0)  # fmt: skip
    judge = ScriptedJudge({s.marker: s.golden for s in SAMPLES})
    first = check_mailbox(store, box, judge, STUDENT, settings, now=clock)
    assert first.error is None and len(store.cards(STUDENT)) == 17
    assert drive.marker not in judge.calls
    connection = store.connection(STUDENT)
    assert connection is not None and connection.history_id == str(fake.history_counter)
    fake.mails = [replace(m, labels=frozenset({"INBOX"})) if m.id == drive.mail.id else m
                  for m in fake.mails]  # fmt: skip
    fake.record("labelsRemoved", drive.mail, ["SPAM"])
    clock.advance(hours=12)
    second = check_mailbox(store, box, judge, STUDENT, settings, now=clock)
    assert second.error is None and judge.calls.count(drive.marker) == 1
    paths = [request.url.path.rsplit("/", 1)[-1] for request in fake.requests]
    assert "history" in paths and "profile" in paths
