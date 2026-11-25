from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timedelta
from typing import Any

import pytest

from mailfilter.config import Settings
from mailfilter.contract import Kind
from mailfilter.errors import (
    CheckInProgress,
    CollegeBlocked,
    GmailUnavailable,
    JudgeFailed,
    JudgeUnavailable,
    MailUnreadable,
    NeedsReconnect,
    NotConnected,
    TooSoon,
)
from mailfilter.fake import STUDENT_ADDRESS, FakeMailbox
from mailfilter.gmail import Mailbox
from mailfilter.judge import ScriptedJudge
from mailfilter.run import RunResult, check_all, check_mailbox, check_now
from mailfilter.samples import BY_KEY, SAMPLES, fake_mails, golden_judge
from mailfilter.sorter import Sorting
from mailfilter.store import CardRow, Store
from mailfilter.timekit import IST
from tests.conftest import MONDAY, STUDENT, Clock

KEPT = [s for s in SAMPLES if s.expect.kind != "other"]
JUDGED = [s for s in SAMPLES if not s.mail.labels & {"SENT", "DRAFT"}]


def at(day: int, hour: int, minute: int = 0) -> datetime:
    return datetime(2026, 11 if day >= 28 else 12, day, hour, minute, tzinfo=IST)


def connected(store: Store, when: datetime = MONDAY) -> None:
    store.connect(STUDENT, STUDENT_ADDRESS, when)


def by_title(store: Store, title: str) -> CardRow:
    return next(card for card in store.cards(STUDENT) if card.title == title)


def inbox(clock: Clock) -> FakeMailbox:
    return FakeMailbox(fake_mails(), now=clock)


def run(
    store: Store, mailbox: Mailbox, judge: ScriptedJudge, settings: Settings, clock: Clock,
    **kwargs: Any,
) -> RunResult:  # fmt: skip
    return check_mailbox(store, mailbox, judge, STUDENT, settings, now=clock, **kwargs)


def test_a_week_of_mail_becomes_the_right_cards(
    store: Store, settings: Settings, clock: Clock
) -> None:
    connected(store)
    judge = golden_judge()
    result = run(store, inbox(clock), judge, settings, clock)
    assert (result.listed, result.carded, result.updated) == (30, 17, 2)
    assert (result.dropped, result.skipped, result.failed, result.retried) == (9, 2, 0, 0)
    assert result.judged == len(JUDGED) and result.error is None
    assert len(store.cards(STUDENT)) == 17

    nimbus = by_title(store, "Nimbus Systems Campus Drive")
    # The reminder moved the deadline and the test; the later forward repeated old news and
    # changed nothing; the first mail's role survived the reminder that did not name one.
    assert nimbus.deadline == at(5, 23, 59)
    assert nimbus.event_date == at(7, 10) and nimbus.event_has_time
    assert nimbus.role == "Graduate Engineer Trainee"
    assert nimbus.form_link == "https://forms.gle/NimbusDrive2027"
    assert nimbus.mails == 3
    assert nimbus.message_id == BY_KEY["nimbus_reminder"].mail.id
    assert nimbus.first_received_at == BY_KEY["nimbus_drive"].mail.received_at

    for sample in KEPT:
        if sample.key in ("nimbus_drive", "nimbus_reminder", "forward_of_drive"):
            continue
        title = sample.golden.title
        assert title is not None
        card = by_title(store, title)
        expect = sample.expect
        assert card.kind == expect.kind, sample.key
        got = card.deadline.astimezone(IST).strftime("%Y-%m-%dT%H:%M") if card.deadline else None
        assert got == expect.deadline, sample.key
        assert card.form_link == expect.link, sample.key
        assert card.mails == 1, sample.key


def test_a_second_check_judges_nothing_again(
    store: Store, settings: Settings, clock: Clock
) -> None:
    connected(store)
    judge = golden_judge()
    mailbox = inbox(clock)
    run(store, mailbox, judge, settings, clock)
    calls = len(judge.calls)
    clock.advance(hours=12)
    again = run(store, mailbox, judge, settings, clock)
    assert again.judged == 0 and len(judge.calls) == calls
    assert again.listed > 0  # listed again within the overlap, skipped by id


def test_twice_a_day_every_mail_is_judged_exactly_once(
    store: Store, settings: Settings, clock: Clock
) -> None:
    connected(store)
    judge = golden_judge()
    mailbox = inbox(clock)
    checks = [at(day, hour) for day in (30, 1, 2, 3) for hour in (13, 21)] + [at(4, 13)]
    for moment in checks:
        clock.set(moment)
        run(store, mailbox, judge, settings, clock)
    assert sorted(judge.calls) == sorted(s.marker for s in JUDGED)
    assert len(store.cards(STUDENT)) == 17


def test_the_first_check_reads_only_that_day(
    store: Store, settings: Settings, clock: Clock
) -> None:
    connected(store, at(1, 15))  # connected Tuesday afternoon
    clock.set(at(1, 15, 1))
    judge = golden_judge()
    result = run(store, inbox(clock), judge, settings, clock)
    tuesday = [s for s in JUDGED if s.mail.received_at.date() == at(1, 0).date()
               and s.mail.received_at <= at(1, 15, 1)]  # fmt: skip
    assert sorted(judge.calls) == sorted(s.marker for s in tuesday)
    assert result.listed == len(tuesday)


def test_mail_gmail_lists_late_is_caught_by_the_overlap(
    store: Store, settings: Settings, clock: Clock
) -> None:
    connected(store)
    mailbox = inbox(clock)
    late = BY_KEY["see_timetable"].mail.id  # arrived Monday 13:05
    mailbox.hidden.add(late)
    judge = golden_judge()
    clock.set(at(30, 13, 10))
    run(store, mailbox, judge, settings, clock)
    assert BY_KEY["see_timetable"].marker not in judge.calls
    mailbox.hidden.clear()
    clock.set(at(30, 21))
    run(store, mailbox, judge, settings, clock)
    assert judge.calls.count(BY_KEY["see_timetable"].marker) == 1


def test_claude_going_down_mid_check_loses_nothing(
    store: Store, settings: Settings, clock: Clock
) -> None:
    connected(store)
    mailbox = inbox(clock)
    answers = {s.marker: s.golden for s in SAMPLES}
    down = BY_KEY["revaluation"]
    broken = ScriptedJudge({**answers, down.marker: JudgeUnavailable("RateLimitError")})
    first = run(store, mailbox, broken, settings, clock)
    assert first.error == "judge_unavailable" and first.status == "connected"
    before = store.connection(STUDENT)
    assert before is not None
    assert before.checked_through < down.mail.received_at  # the next check starts before it
    healthy = golden_judge()
    clock.advance(hours=1)
    second = run(store, mailbox, healthy, settings, clock)
    assert second.error is None
    assert len(store.cards(STUDENT)) == 17
    judged_twice = set(broken.calls) & set(healthy.calls) - {down.marker}
    assert judged_twice == set()


def test_a_mail_claude_cannot_judge_is_retried_then_given_up(
    store: Store, settings: Settings, clock: Clock
) -> None:
    connected(store)
    mailbox = inbox(clock)
    stuck = BY_KEY["kaveri_internship"]
    answers = {s.marker: s.golden for s in SAMPLES}
    judge = ScriptedJudge({**answers, stuck.marker: JudgeFailed("refusal")})
    for attempt in (1, 2, 3):
        result = run(store, mailbox, judge, settings, clock)
        state = store.seen_states(STUDENT, [stuck.mail.id])[stuck.mail.id]
        assert state.attempts == attempt
        connection = store.connection(STUDENT)
        assert connection is not None
        # The retry is queued by id, so the window moves on without it.
        assert connection.checked_through == clock()
        if attempt < 3:
            assert state.outcome == "retry" and result.retried == 1
            assert store.retry_ids(STUDENT) == [stuck.mail.id]
        else:
            assert state.outcome == "failed" and result.failed == 1
            assert store.retry_ids(STUDENT) == []
        clock.advance(days=3)  # far past the window: the retry is found by id, not by date
    assert judge.calls.count(stuck.marker) == 3
    assert judge.calls.count(BY_KEY["nimbus_drive"].marker) == 1


def test_one_unreadable_or_crashing_mail_costs_that_mail_only(
    store: Store, settings: Settings, clock: Clock
) -> None:
    connected(store)
    mailbox = inbox(clock)
    mailbox.errors[BY_KEY["webinar"].mail.id] = MailUnreadable("bad_message")
    crash = BY_KEY["results"]
    answers = {s.marker: s.golden for s in SAMPLES}
    judge = ScriptedJudge({**answers, crash.marker: ValueError("bug")})
    result = run(store, mailbox, judge, settings, clock)
    assert result.error is None and result.retried == 2
    assert len(store.cards(STUDENT)) == 16
    states = store.seen_states(STUDENT, [BY_KEY["webinar"].mail.id, crash.mail.id])
    assert {state.outcome for state in states.values()} == {"retry"}
    assert set(store.retry_ids(STUDENT)) == {BY_KEY["webinar"].mail.id, crash.mail.id}
    del mailbox.errors[BY_KEY["webinar"].mail.id]
    clock.advance(hours=12)
    again = run(store, mailbox, golden_judge(), settings, clock)
    assert again.retried == 0 and len(store.cards(STUDENT)) == 17


@pytest.mark.parametrize(
    ("error", "status"),
    [
        (NeedsReconnect("invalid_grant"), "needs_reconnect"),
        (NotConnected("no_refresh_token"), "needs_reconnect"),
        (CollegeBlocked("domain_policy"), "college_blocked"),
        (GmailUnavailable("http_503"), "connected"),
    ],
)
def test_gmail_trouble_is_recorded_and_the_start_kept(
    store: Store, settings: Settings, clock: Clock, error: Exception, status: str
) -> None:
    connected(store)
    mailbox = FakeMailbox(fake_mails(), list_error=error, now=clock)
    result = run(store, mailbox, golden_judge(), settings, clock)
    connection = store.connection(STUDENT)
    assert connection is not None
    assert result.status == status and connection.status == status
    assert connection.checked_through == MONDAY
    assert connection.last_ok_at is None
    if status != "connected":
        # Not tried again until the student signs in again; then it carries on from Monday.
        mailbox.list_error = None
        skipped = run(store, mailbox, golden_judge(), settings, clock)
        assert skipped.error == status and skipped.listed == 0
        store.connect(STUDENT, STUDENT_ADDRESS, clock())
        assert run(store, mailbox, golden_judge(), settings, clock).carded == 17


def test_gmail_failing_mid_check_keeps_what_was_settled(
    store: Store, settings: Settings, clock: Clock
) -> None:
    connected(store)
    mailbox = inbox(clock)
    mailbox.errors[BY_KEY["revaluation"].mail.id] = GmailUnavailable("http_503")
    first = run(store, mailbox, golden_judge(), settings, clock)
    assert first.error == "gmail_unavailable" and 0 < first.carded < 17
    del mailbox.errors[BY_KEY["revaluation"].mail.id]
    clock.advance(hours=1)
    run(store, mailbox, golden_judge(), settings, clock)
    assert len(store.cards(STUDENT)) == 17


def test_two_checks_never_run_at_once(store: Store, settings: Settings, clock: Clock) -> None:
    connected(store)
    assert store.acquire(STUDENT, clock(), settings.lease)
    with pytest.raises(CheckInProgress):
        run(store, inbox(clock), golden_judge(), settings, clock)
    clock.advance(minutes=15)  # a crashed holder's lease runs out
    assert run(store, inbox(clock), golden_judge(), settings, clock).carded == 17


def test_more_mail_than_one_check_takes_is_finished_by_the_next(
    store: Store, settings: Settings, clock: Clock
) -> None:
    connected(store)
    small = replace(settings, max_mails_per_run=4)
    mailbox = inbox(clock)
    judge = golden_judge()
    rounds = 0
    while True:
        result = run(store, mailbox, judge, small, clock)
        rounds += 1
        clock.advance(minutes=10)
        if not result.more:
            break
    assert rounds == 8  # 30 mails, 4 at a time
    assert len(store.cards(STUDENT)) == 17
    assert sorted(judge.calls) == sorted(s.marker for s in JUDGED)


def test_running_out_of_time_stops_cleanly(store: Store, settings: Settings, clock: Clock) -> None:
    connected(store)
    left = iter([600.0, 600.0, 30.0])
    result = run(
        store, inbox(clock), golden_judge(), settings, clock,
        time_left=lambda: next(left, 30.0),
    )  # fmt: skip
    assert result.more and result.listed == 30
    assert run(store, inbox(clock), golden_judge(), settings, clock).error is None


def test_after_a_long_outage_reading_stops_at_the_lookback(
    store: Store, settings: Settings, clock: Clock
) -> None:
    connected(store, at(30, 0) - timedelta(days=20))
    clock.set(at(4, 1))
    seen: list[datetime] = []

    class Spy(FakeMailbox):
        def list_ids(self, after: datetime) -> list[str]:
            seen.append(after)
            return super().list_ids(after)

    run(store, Spy(fake_mails(), now=clock), golden_judge(), settings, clock)
    assert seen == [clock() - settings.lookback]


def test_check_now_has_a_cooldown(store: Store, settings: Settings, clock: Clock) -> None:
    connected(store)
    mailbox = inbox(clock)
    check_now(store, mailbox, golden_judge(), STUDENT, settings, now=clock)
    clock.advance(minutes=2)
    with pytest.raises(TooSoon):
        check_now(store, mailbox, golden_judge(), STUDENT, settings, now=clock)
    check_now(store, mailbox, golden_judge(), STUDENT, settings, now=clock, force=True)
    clock.advance(minutes=6)
    check_now(store, mailbox, golden_judge(), STUDENT, settings, now=clock)
    assert [r.trigger for r in store.runs(STUDENT)] == ["check_now"] * 3
    with pytest.raises(NotConnected):
        check_now(store, mailbox, golden_judge(), "nobody", settings, now=clock)


def test_the_sweep_checks_everyone_and_one_failure_stops_no_one(
    store: Store, settings: Settings, clock: Clock
) -> None:
    store.connect("good", STUDENT_ADDRESS, MONDAY)
    store.connect("no-token", "x@mockcollege.edu.in", MONDAY)

    def mailbox_for(student_id: str) -> Mailbox:
        if student_id == "no-token":
            raise NotConnected("no_refresh_token")
        return inbox(clock)

    results = check_all(store, mailbox_for, golden_judge(), settings, now=clock)
    assert {(r.student_id, r.error) for r in results} == {
        ("good", None),
        ("no-token", "not_connected"),
    }
    broken = store.connection("no-token")
    assert broken is not None and broken.status == "needs_reconnect"
    assert store.connected_students() == ["good"]
    assert check_all(store, mailbox_for, golden_judge(), settings, now=clock,
                     time_left=lambda: 100.0) == []  # fmt: skip


class FakeJev:
    name = "jev"

    def __init__(self, kind: Kind, confidence: float, fail: bool = False) -> None:
        self.kind, self.confidence, self.fail = kind, confidence, fail

    def sort(self, rendered: str) -> Sorting | None:
        if self.fail:
            raise RuntimeError("jev down")
        if "Sent to a mailing list: yes" in rendered:
            return Sorting(self.kind, self.confidence)
        return None


@pytest.mark.parametrize(
    ("jev", "skipped_by_jev"),
    [
        (FakeJev("other", 0.95), 4),  # sure it is junk: Claude never reads those four
        (FakeJev("other", 0.5), 0),  # not sure enough: Claude reads them
        (FakeJev("placement", 0.99), 0),  # a sorter can only drop, never keep
        (FakeJev("other", 0.99, fail=True), 0),  # a broken sorter is ignored
    ],
)
def test_the_jev_slot(
    store: Store, settings: Settings, clock: Clock, jev: FakeJev, skipped_by_jev: int
) -> None:
    connected(store)
    judge = golden_judge()
    result = run(store, inbox(clock), judge, settings, clock, sorter=jev)
    assert result.judged == len(JUDGED) - skipped_by_jev
    assert len(store.cards(STUDENT)) == 17


def test_a_crash_is_recorded_the_lease_released_and_raised(
    store: Store, settings: Settings, clock: Clock, monkeypatch: pytest.MonkeyPatch
) -> None:
    connected(store)

    def broken(*args: object, **kwargs: object) -> object:
        raise RuntimeError("bug")

    monkeypatch.setattr(store, "seen_states", broken)
    with pytest.raises(RuntimeError):
        run(store, inbox(clock), golden_judge(), settings, clock)
    assert store.runs(STUDENT)[-1].error == "internal_error"
    assert store.acquire(STUDENT, clock(), settings.lease)  # not left locked


def test_a_different_google_account_starts_afresh(
    store: Store, settings: Settings, clock: Clock
) -> None:
    connected(store)
    run(store, inbox(clock), golden_judge(), settings, clock)
    store.connect(STUDENT, "other.account@mockcollege.edu.in", clock())
    connection = store.connection(STUDENT)
    assert connection is not None and connection.email == "other.account@mockcollege.edu.in"
    assert store.seen_states(STUDENT, [s.mail.id for s in SAMPLES]) == {}
    assert len(store.cards(STUDENT)) == 17  # the student's cards are theirs to keep
