"""One check of one student's mailbox, and the twice-daily sweep over every student.

A check reads three sets of mail, in this order:

1. mail it could not judge before (retried at every check, given up after `max_attempts`);
2. mail Gmail's change history says arrived, or was moved out of spam or trash, since the last
   complete check: a rescued mail keeps its old date, so no date window would ever find it;
3. every mail since the last check by date, minus a two-hour overlap for mail Gmail lists
   late, oldest first. The first check after connecting reads exactly that day.

Mail already settled is skipped by id. Each mail is settled in its own transaction: its outcome
and, if kept, its card. The date window moves forward only past mail that is settled or queued
for retry, and the history position only when a check completes, so an outage, a crash, a cap or
a lapsed lease never loses a mail and never judges one twice.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, time, timedelta

from mailfilter.checks import check, link_key
from mailfilter.config import Settings
from mailfilter.contract import ConnectionStatus
from mailfilter.dates import moment_named
from mailfilter.errors import (
    RUN_STOPPING,
    CheckInProgress,
    CollegeBlocked,
    JudgeFailed,
    LeaseLost,
    MailFilterError,
    MailUnreadable,
    NeedsReconnect,
    NotConnected,
    TooSoon,
)
from mailfilter.gmail import Mailbox
from mailfilter.judge import Judge
from mailfilter.mail import MailMessage, render
from mailfilter.sorter import NoSorter, Sorter, drops_without_claude
from mailfilter.store import CardDraft, Outcome, RunRecord, Store
from mailfilter.timekit import IST, to_ist, utc_now

log = logging.getLogger("mailfilter")
# Mail the student sent, drafts and chats are never judged. Spam and trash are not judged
# either, but not recorded: if the student rescues one, Gmail's history brings it back.
NEVER_JUDGED = frozenset({"SENT", "DRAFT", "CHAT"})
NOT_YET = frozenset({"SPAM", "TRASH"})


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
    counter: str
    judged: bool


def status_for(error: MailFilterError) -> ConnectionStatus:
    if isinstance(error, NeedsReconnect | NotConnected):
        return "needs_reconnect"
    if isinstance(error, CollegeBlocked):
        return "college_blocked"
    return "connected"


def news_time(mail: MailMessage) -> datetime:
    """When the news in a mail was sent: a forward's original date when it can be read (a
    forward of last week's notice is last week's news), else when the mail arrived."""
    if mail.content.forwarded and mail.content.forwarded_date:
        named = moment_named(mail.content.forwarded_date, to_ist(mail.received_at).date())
        if named is not None:
            day, clock = named
            moment = datetime.combine(day, clock or time(0), IST)
            if moment <= mail.received_at:
                return moment
    return mail.received_at


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
    return _Settled(received, "failed" if final else "retried", judged)


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
        return _Settled(None, "skipped", False)
    received = mail.received_at
    if mail.labels & NOT_YET:
        return _Settled(received, "skipped", False)
    if mail.labels & NEVER_JUDGED:
        store.record_mail(student_id, message_id, received, "skipped", "label", now())
        return _Settled(received, "skipped", False)
    rendered = render(mail)
    if drops_without_claude(sorter, rendered.for_claude, settings.sorter_threshold):
        store.record_mail(
            student_id, message_id, received, "dropped", f"sorter:{sorter.name}", now()
        )
        return _Settled(received, "dropped", False)
    try:
        proposal = judge.judge(rendered.for_claude)
    except JudgeFailed as error:
        return _failure(
            store, student_id, message_id, received, error.detail, attempts, settings, now, True
        )
    checked = check(proposal, mail, rendered.checkable)
    if checked.kind is None:
        store.record_mail(student_id, message_id, received, "dropped", "other", now())
        return _Settled(received, "dropped", True)
    draft = CardDraft(
        kind=checked.kind,
        title=checked.title,
        organisation=checked.organisation,
        role=checked.role,
        deadline=checked.deadline,
        event_date=checked.event_date,
        event_has_time=checked.event_has_time,
        form_link=checked.form_link,
        link_key=link_key(checked.form_link),
        details=checked.details,
        received_at=received,
        news_at=news_time(mail),
        forwarded=mail.content.forwarded,
        message_id=mail.id,
        rfc822_id=mail.content.message_id,
        thread_id=mail.thread_id,
    )
    reason = ",".join(checked.rejected) or None
    change = store.record_mail(student_id, message_id, received, "carded", reason, now(), draft)
    counter = {"created": "carded", "updated": "updated", "unchanged": "updated"}.get(
        change or "", "skipped"
    )
    return _Settled(received, counter, True)


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
    before = store.connection(student_id)
    if before is None:
        raise NotConnected("no_connection")
    result = RunResult(student_id=student_id, trigger=trigger, status=before.status)
    if before.status != "connected":
        # A mailbox Google will not open is not tried until the student reconnects.
        result.error = before.status
        return result
    started = now()
    token = store.acquire(student_id, started, settings.lease)
    if token is None:
        raise CheckInProgress("lease_held")
    connection = store.connection(student_id)  # read again, now that this check holds it
    if connection is None:
        raise NotConnected("disconnected")
    previous = connection.checked_through
    first = connection.last_ok_at is None
    window_start = max(
        previous - (timedelta(seconds=1) if first else settings.overlap),
        started - settings.lookback,
    )
    use_sorter = sorter or NoSorter()
    listed_at = started
    history_now: str | None = None
    settled_through: datetime | None = None
    complete = lost = False
    bug: Exception | None = None
    try:
        listed_at = now()
        history_now = mailbox.history_id()
        window = list(reversed(mailbox.list_ids(window_start)))
        changed: list[str] = []
        if connection.history_id:
            since = mailbox.changed_since(connection.history_id)
            if since is None:
                log.warning("gmail history expired", extra={"student_id": student_id})
            else:
                changed = since
        retries = store.retry_ids(student_id)
        states = store.seen_states(student_id, [*retries, *changed, *window])

        def still_open(message_id: str) -> bool:
            return message_id not in states or states[message_id].outcome == "retry"

        first_pass = [i for i in dict.fromkeys([*retries, *changed]) if still_open(i)]
        in_first_pass = set(first_pass)
        window_todo = [i for i in window if still_open(i) and i not in in_first_pass]
        in_window = set(window_todo)
        result.listed = len(set(window) | set(changed) | set(retries))
        stopped = False
        for index, message_id in enumerate([*first_pass, *window_todo]):
            if index >= settings.max_mails_per_run or (time_left is not None and time_left() < 60):
                stopped = True
                break
            if not store.renew(student_id, token, now(), settings.lease):
                raise LeaseLost("renew_refused")
            attempts = states[message_id].attempts if message_id in states else 0
            try:
                settled = _settle(
                    store, mailbox, judge, use_sorter, student_id, message_id, attempts,
                    settings, now,
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
            if message_id in in_window and settled.received_at is not None:
                settled_through = max(settled_through or settled.received_at, settled.received_at)
            setattr(result, settled.counter, getattr(result, settled.counter) + 1)
            result.judged += settled.judged
        result.more = stopped
        complete = not stopped
    except LeaseLost:
        lost = True
        result.error = LeaseLost.code
        log.warning("check lost its lease", extra={"student_id": student_id})
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
        if not lost:
            next_start = listed_at if complete else (settled_through or previous)
            store.finish(
                student_id,
                token,
                finished_at,
                max(previous, next_start),
                history_now if complete else None,
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
        store.release(student_id, token)
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
    """The app's "check now" button: refused within the cooldown of the last check's start,
    and while a check is running (it holds the lease)."""
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
