"""Wiring: one place builds the database, queue, cascade and gateway.

Why: the web API, the MCP server, the demo script and the tests all need the same
objects, and tests swap in scripted Jev / LLM here without touching anything else.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import timedelta
from typing import Any

from . import notify
from .cascade import Cascade, Outcome
from .config import settings
from .db import Database
from .gateway import Gateway
from .jev import Decider, get_decider
from .jobqueue import Queue, SqsQueue
from .llm import LLM, get_llm
from .scheduler import Job

log = logging.getLogger(__name__)


@dataclass
class App:
    db: Database
    queue: Queue | SqsQueue
    cascade: Cascade
    gateway: Gateway
    last: list[Outcome]
    # Where messages for the student go (the outbox), and who rings for an urgent call.
    sender: notify.Sender = field(default_factory=notify.LogSender)
    caller: Any = None
    # When the current turn of the background loop must be done (time.monotonic()), shared by
    # every job in it; set by the Lambda tick, None on a long-running server (no limit).
    deadline: float | None = None

    def time_left(self) -> float | None:
        import time

        return None if self.deadline is None else self.deadline - time.monotonic()

    def process(self, event_id: int) -> Outcome | None:
        """One event through the cascade. Shared by the local drain and the cascade Lambda.
        An event already done (SQS delivers at least once) is skipped, not filed twice."""
        event = self.db.event(event_id)
        if event is None:
            raise LookupError(f"no event {event_id}")  # retried, then kept by the DLQ
        if event["status"] == "done":
            return None
        outcome = self.cascade.run(event_id)
        self.db.mark_event(event_id, "done")
        log.info("event %s -> %s/%s", event_id, outcome.route, outcome.status)
        return outcome

    def work(self) -> list[Outcome]:
        """Drain the local queue (on AWS the cascade Lambda consumes SQS instead)."""
        outcomes: list[Outcome] = []

        def handle(event_id: int) -> None:
            if (outcome := self.process(event_id)) is not None:
                outcomes.append(outcome)

        self.queue.drain(handle, lambda eid, err: self.db.mark_event(eid, "dead", err))
        self.last = outcomes
        return outcomes


    def jobs(self) -> list[Job]:
        """What the background loop runs (scheduler.py). Each is safe to run twice."""
        from mailfilter.config import parse_times

        return [
            Job("reminders", lambda: notify.fire_due(self.db, self.sender, self.caller),
                every=timedelta(seconds=30)),
            Job("mail", self.check_mail, at=parse_times(settings.mail_check_times)),
            # Only does anything when a check was cut short (Lambda's budget, the mail cap).
            Job("mail-continue", self.continue_mail, every=timedelta(minutes=2)),
        ]

    def continue_mail(self) -> int:
        from . import mail

        left = self.time_left()
        if left is not None and left < mail.MAIL_RESERVE + 2:
            return 0  # the mail job used this turn; the next one carries on
        return mail.continue_unfinished(self.db, self.deadline)

    def check_mail(self) -> int:
        """College mail for every student, then Classroom for those who connected it, each
        only while the turn has time for it."""
        from . import google, mail

        checked = mail.check_all(self.db, self.deadline)
        for sid in self.db.google_students():
            left = self.time_left()
            if left is not None and left < google.CLASSROOM_RESERVE:
                break  # Classroom waits for the next check rather than overrun Lambda's limit
            try:
                google.classroom_sync(self, sid, deadline=self.deadline)
            except Exception as err:  # noqa: BLE001 - one student's Classroom never stops another
                log.warning("classroom sync failed", extra={"student": sid,
                                                            "error": type(err).__name__})
        return checked


def build(db_url: str | None = None, jev: Decider | None = None, llm: LLM | None = None,
          caller: Any = None) -> App:
    from . import calls, fcm

    db = Database(db_url)
    queue: Queue | SqsQueue = SqsQueue(settings.queue_url) if settings.queue_url else Queue()
    sender = notify.OutboxSender(db, wake=fcm.get_waker(db))
    return App(db=db, queue=queue, cascade=Cascade(db, jev or get_decider(), llm or get_llm()),
               gateway=Gateway(db), last=[], sender=sender,
               caller=caller if caller is not None else calls.get_caller())
