"""One check of one student's mailbox, and the twice-daily sweep over every student.

A check reads every mail since the last check (minus a two-hour overlap for mail Gmail lists
late; mail already judged is skipped by id), oldest first. Each mail is settled in its own
transaction: its outcome and, if kept, its card. Where the next check starts moves forward only
past mail that is settled, so a crash, an outage or a cap never loses a mail:

- Claude or Gmail down: the check stops; the next one starts before the first unsettled mail.
- One mail Claude cannot judge, or Gmail cannot give us: retried at the next checks, and given
  up after `max_attempts` so one bad mail cannot hold the mailbox back for ever.
- More mail than one check takes: the next check carries on where this one stopped.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime, timedelta

from mailfilter.checks import card_key, check
from mailfilter.config import Settings
from mailfilter.contract import ConnectionStatus
from mailfilter.errors import (
    RUN_STOPPING,
    CheckInProgress,
    CollegeBlocked,
    JudgeFailed,
    MailFilterError,
    MailUnreadable,
    NeedsReconnect,
    NotConnected,
    TooSoon,
)
from mailfilter.gmail import Mailbox
from mailfilter.judge import Judge
from mailfilter.mail import render
from mailfilter.sorter import NoSorter, Sorter, drops_without_claude
from mailfilter.store import CardDraft, Outcome, RunRecord, Store
from mailfilter.timekit import utc_now

log = logging.getLogger("mailfilter")


@dataclass
class RunResult:
    student_id: str
    trigger: str
    listed: int = 0
    judged: int = 0
    carded: int = 0
    updated: int = 0
    dropped: int = 0
    skipped: int = 0
    retried: int = 0
    failed: int = 0
    more: bool = False
    error: str | None = None
    status: ConnectionStatus = "connected"


@dataclass(frozen=True)
class _Settled:
    received_at: datetime | None
    final: bool
    counter: str
    judged: bool


@dataclass
class _Progress:
    """What decides where the next check starts."""

    complete: bool = False
    settled_through: datetime | None = None
    unsettled_from: datetime | None = None
    unsettled_unknown: bool = False
    listed_at: datetime | None = None
    reasons: list[str] = field(default_factory=list)

    def add(self, settled: _Settled) -> None:
        when = settled.received_at
        if settled.final:
            if when is not None:
                self.settled_through = max(self.settled_through or when, when)
        elif when is None:
            self.unsettled_unknown = True
        else:
            self.unsettled_from = min(self.unsettled_from or when, when)

    def next_start(self, previous: datetime) -> datetime:
        if self.unsettled_unknown:
            return previous
        if self.complete and self.listed_at is not None:
            candidate = self.listed_at
        else:
            candidate = self.settled_through or previous
        if self.unsettled_from is not None:
            candidate = min(candidate, self.unsettled_from)
        return max(previous, candidate)


def status_for(error: MailFilterError) -> ConnectionStatus:
    if isinstance(error, NeedsReconnect | NotConnected):
        return "needs_reconnect"
    if isinstance(error, CollegeBlocked):
        return "college_blocked"
    return "connected"


def _failure(
    store: Store,
    student_id: str,
    message_id: str,
    received: datetime | None,
    reason: str,
    attempts: int,
    settings: Settings,
    now: Callable[[], datetime],
    judged: bool,
) -> _Settled:
    final = attempts + 1 >= settings.max_attempts
    outcome: Outcome = "failed" if final else "retry"
    store.record_mail(student_id, message_id, received, outcome, reason, now())
    return _Settled(received, final, "failed" if final else "retried", judged)


def _settle(
    store: Store,
    mailbox: Mailbox,
    judge: Judge,
    sorter: Sorter,
    student_id: str,
    message_id: str,
    attempts: int,
    settings: Settings,
    now: Callable[[], datetime],
) -> _Settled:
    try:
        mail = mailbox.get(message_id)
    except MailUnreadable as error:
        return _failure(
            store, student_id, message_id, None, error.detail, attempts, settings, now, False
        )
    if mail is None:
        store.record_mail(student_id, message_id, None, "gone", None, now())
        return _Settled(None, True, "skipped", False)
    received = mail.received_at
    if mail.skipped:
        store.record_mail(student_id, message_id, received, "skipped", "label", now())
        return _Settled(received, True, "skipped", False)
    rendered = render(mail)
    if drops_without_claude(sorter, rendered.for_claude, settings.sorter_threshold):
        store.record_mail(
            student_id, message_id, received, "dropped", f"sorter:{sorter.name}", now()
        )
        return _Settled(received, True, "dropped", False)
    try:
        proposal = judge.judge(rendered.for_claude)
    except JudgeFailed as error:
        return _failure(
            store, student_id, message_id, received, error.detail, attempts, settings, now, True
        )
    checked = check(proposal, mail, rendered.checkable)
    if not checked.keep or checked.kind is None:
        store.record_mail(student_id, message_id, received, "dropped", "other", now())
        return _Settled(received, True, "dropped", True)
    draft = CardDraft(
        key=card_key(checked, mail),
        kind=checked.kind,
        title=checked.title,
        organisation=checked.organisation,
        role=checked.role,
        deadline=checked.deadline,
        event_date=checked.event_date,
        event_has_time=checked.event_has_time,
        form_link=checked.form_link,
        details=checked.details,
        received_at=received,
        message_id=mail.id,
        rfc822_id=mail.content.message_id,
        thread_id=mail.thread_id,
        authoritative=not mail.content.forwarded,
    )
    reason = ",".join(checked.rejected) or None
    change = store.record_mail(student_id, message_id, received, "carded", reason, now(), draft)
    return _Settled(received, True, "carded" if change == "created" else "updated", True)


def check_mailbox(
    store: Store,
    mailbox: Mailbox,
    judge: Judge,
    student_id: str,
    settings: Settings,
    *,
    sorter: Sorter | None = None,
    trigger: str = "scheduled",
    now: Callable[[], datetime] = utc_now,
    time_left: Callable[[], float] | None = None,
) -> RunResult:
    connection = store.connection(student_id)
    if connection is None:
        raise NotConnected("no_connection")
    result = RunResult(student_id=student_id, trigger=trigger, status=connection.status)
    if connection.status != "connected":
        # A mailbox Google will not open is not tried until the student reconnects.
        result.error = connection.status
        return result
    started = now()
    if not store.acquire(student_id, started, settings.lease):
        raise CheckInProgress("lease_held")
    use_sorter = sorter or NoSorter()
    if connection.last_run_at is None:
        # The first check reads exactly that day's mail, from midnight in India (a second
        # earlier, in case Gmail's `after:` excludes the boundary itself).
        window_start = max(
            connection.checked_through - timedelta(seconds=1), started - settings.lookback
        )
    else:
        window_start = max(
            connection.checked_through - settings.overlap, started - settings.lookback
        )
    progress = _Progress()
    bug: Exception | None = None
    try:
        progress.listed_at = now()
        ids, capped = mailbox.list_ids(window_start, settings.max_listed)
        if capped:
            log.warning("listing capped", extra={"student_id": student_id, "listed": len(ids)})
        oldest_first = list(reversed(ids))
        result.listed = len(oldest_first)
        states = store.seen_states(student_id, oldest_first)
        todo = [
            message_id
            for message_id in oldest_first
            if message_id not in states or states[message_id].outcome == "retry"
        ]
        result.more = capped or len(todo) > settings.max_mails_per_run
        stopped_early = False
        for message_id in todo[: settings.max_mails_per_run]:
            if time_left is not None and time_left() < 60:
                result.more = stopped_early = True
                break
            attempts = states[message_id].attempts if message_id in states else 0
            try:
                settled = _settle(
                    store, mailbox, judge, use_sorter, student_id, message_id, attempts, settings,
                    now,
                )  # fmt: skip
            except RUN_STOPPING:
                raise
            except Exception as error:  # noqa: BLE001 - a bug on one mail costs that mail only
                log.error(
                    "mail failed",
                    extra={
                        "student_id": student_id,
                        "message_id": message_id,
                        "error": type(error).__name__,
                    },
                )
                settled = _failure(
                    store, student_id, message_id, None, f"error:{type(error).__name__}",
                    attempts, settings, now, False,
                )  # fmt: skip
            progress.add(settled)
            setattr(result, settled.counter, getattr(result, settled.counter) + 1)
            if settled.judged:
                result.judged += 1
        progress.complete = not stopped_early and not result.more
        result.status = "connected"
    except MailFilterError as error:
        result.error = error.code
        result.status = status_for(error)
        log.warning(
            "check stopped",
            extra={"student_id": student_id, "error": error.code, "detail": error.detail},
        )
    except Exception as error:  # noqa: BLE001 - recorded, the lease released, then re-raised
        bug = error
        result.error = "internal_error"
        log.error("check crashed", extra={"student_id": student_id, "error": type(error).__name__})
    finally:
        finished_at = now()
        store.finish(
            student_id,
            finished_at,
            progress.next_start(connection.checked_through),
            result.status,
            result.error,
        )
        store.record_run(
            RunRecord(
                student_id=student_id,
                trigger=trigger,
                started_at=started,
                finished_at=finished_at,
                window_start=window_start,
                listed=result.listed,
                judged=result.judged,
                carded=result.carded + result.updated,
                dropped=result.dropped,
                skipped=result.skipped,
                failed=result.failed + result.retried,
                more=result.more,
                error=result.error,
            )
        )
        store.release(student_id)
    if bug is not None:
        raise bug
    log.info(
        "check finished",
        extra={
            "student_id": student_id,
            "trigger": trigger,
            "listed": result.listed,
            "judged": result.judged,
            "carded": result.carded,
            "updated": result.updated,
            "dropped": result.dropped,
            "skipped": result.skipped,
            "retried": result.retried,
            "failed": result.failed,
            "more": result.more,
            "error": result.error,
        },
    )
    return result


def check_now(
    store: Store,
    mailbox: Mailbox,
    judge: Judge,
    student_id: str,
    settings: Settings,
    *,
    sorter: Sorter | None = None,
    now: Callable[[], datetime] = utc_now,
    force: bool = False,
    trigger: str = "check_now",
) -> RunResult:
    """The app's "check now" button: refused within the cooldown of the last check."""
    connection = store.connection(student_id)
    if connection is None:
        raise NotConnected("no_connection")
    last = connection.last_run_at
    if not force and last is not None and now() - last < settings.check_now_cooldown:
        raise TooSoon("cooldown")
    return check_mailbox(
        store, mailbox, judge, student_id, settings, sorter=sorter, trigger=trigger, now=now
    )


def check_all(
    store: Store,
    mailbox_for: Callable[[str], Mailbox],
    judge: Judge,
    settings: Settings,
    *,
    sorter: Sorter | None = None,
    now: Callable[[], datetime] = utc_now,
    time_left: Callable[[], float] | None = None,
    reserve_seconds: float = 300.0,
) -> list[RunResult]:
    """The scheduled sweep. One student's failure never stops the others; students left when
    time runs short are first in line next time (longest-unchecked first)."""
    results: list[RunResult] = []
    for student_id in store.connected_students():
        if time_left is not None and time_left() < reserve_seconds:
            log.warning("sweep out of time", extra={"left_unchecked": student_id})
            break
        try:
            mailbox = mailbox_for(student_id)
            results.append(
                check_mailbox(
                    store,
                    mailbox,
                    judge,
                    student_id,
                    settings,
                    sorter=sorter,
                    now=now,
                    time_left=time_left,
                )  # fmt: skip
            )
        except CheckInProgress:
            continue
        except MailFilterError as error:
            store.mark(student_id, status_for(error), error.code)
            results.append(
                RunResult(student_id, "scheduled", error=error.code, status=status_for(error))
            )
        except Exception as error:  # noqa: BLE001 - the next student still gets checked
            log.error("student check crashed", extra={"student_id": student_id,
                                                       "error": type(error).__name__})  # fmt: skip
            results.append(RunResult(student_id, "scheduled", error="internal_error"))
    return results
