"""Wiring: one place builds the database, queue, cascade and gateway.

Why: the web API, the MCP server, the demo script and the tests all need the same
objects, and tests swap in scripted Jev / LLM here without touching anything else.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any

from . import clock, notify
from .cascade import Cascade, Outcome
from .config import settings
from .db import Database
from .gateway import Gateway
from .jev import Decider, get_decider
from .jobqueue import Queue, SqsQueue
from .llm import LLM, get_llm
from .scheduler import Job

log = logging.getLogger(__name__)

# Re-driving events a killed Lambda left queued (App.redrive). Older than REDRIVE_AFTER, the run
# that took one is gone: a drain lasts under one 30-second turn. Through SQS, its own retries
# come first: three receives, 180 seconds apart (template.yaml), then its dead-letter queue.
REDRIVE_AFTER = timedelta(minutes=5)
REDRIVE_AFTER_SQS = timedelta(minutes=10)
REDRIVE_BATCH = 5  # events per turn at most
REDRIVE_TRIES = 3  # then the event is parked as dead, as the queue does
REDRIVE_RESERVE = 15.0  # seconds one event may need: Jev, then the LLM
REDRIVE_LEASE = timedelta(minutes=2)  # one instance at a time; longer than any turn
REDRIVE_LEASE_NAME = "lease:events-redrive"


def _seconds(at: datetime) -> str:
    """India time to the second, as the jobs table keeps it (text order is time order)."""
    return at.astimezone(clock.IST).isoformat(timespec="seconds")


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
        An event already done (SQS delivers at least once) is skipped, not filed twice, and so
        is one whose card is already filed (a run killed between filing it and marking the
        event done). One that left a card for review runs again: its card takes that one's
        place (db.file_item)."""
        event = self.db.event(event_id)
        if event is None:
            raise LookupError(f"no event {event_id}")  # retried, then kept by the DLQ
        if event["status"] == "done":
            return None
        if self.db.card_of_event(event_id) is not None:
            self.db.mark_event(event_id, "done")
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
        """What the background loop runs (scheduler.py). Each is safe to run twice. On Lambda
        they share one turn's time, in this order; mail-continue runs every other turn, so
        Classroom gets whole turns too while both have work left."""
        from mailfilter.config import parse_times

        return [
            Job("reminders", lambda: notify.fire_due(self.db, self.sender, self.caller),
                every=timedelta(seconds=30)),
            Job("events-redrive", self.redrive, every=timedelta(minutes=5)),
            Job("mail", self.check_mail, at=parse_times(settings.mail_check_times)),
            # Whatever the slot has not finished: mailboxes the 1 PM job had no time for, checks
            # cut short (the turn's time, the mail cap), Claude or Gmail unreachable.
            Job("mail-continue", self.continue_mail, every=timedelta(minutes=2)),
            # Every turn (Lambda ticks once a minute): Classroom for each connected student once
            # per mail slot, least recently read first.
            Job("classroom", self.sync_classroom, every=timedelta(seconds=30)),
        ]

    def continue_mail(self) -> int:
        from . import mail

        left = self.time_left()
        if left is not None and left < mail.MAIL_RESERVE + 2:
            return 0  # the mail job used this turn; the next one carries on
        return mail.continue_unfinished(self.db, self.deadline)

    def check_mail(self) -> int:
        """College mail at 1 PM and 9 PM, for every student this turn has time for;
        mail-continue takes the rest over the next turns."""
        from . import mail

        return mail.check_all(self.db, self.deadline)

    def sync_classroom(self) -> int:
        """Classroom for every student who connected it, once per mail slot, over as many turns
        as it takes: least recently read first, each only started with CLASSROOM_RESERVE seconds
        left. Returns how many were read completely."""
        from . import google

        done = 0
        for sid in google.classroom_due(self.db):
            left = self.time_left()
            if left is not None and left < google.CLASSROOM_RESERVE:
                break  # the next turn carries on, starting with whoever waited longest
            done += google.classroom_turn(self, sid, deadline=self.deadline)
        return done

    def redrive(self) -> int:
        """Events still queued REDRIVE_AFTER after they arrived: the run that took them was
        killed (a Lambda stopped mid-drain, an in-memory queue lost with it), and the source's
        own retry is dropped as a duplicate, so nothing else would ever run them. A few per
        turn, oldest first, each only with time for the cascade. One instance at a time (a
        lease); each try is counted, and one that keeps failing is parked as dead. Safe to run
        twice: a done event is skipped, and an event whose card exists is only marked done.
        Returns how many ran."""
        now = clock.now()
        after = REDRIVE_AFTER_SQS if isinstance(self.queue, SqsQueue) else REDRIVE_AFTER
        stale = self.db.stale_events(clock.iso(now - after), REDRIVE_TRIES, REDRIVE_BATCH)
        left = self.time_left()
        if not stale or (left is not None and left < REDRIVE_RESERVE):
            return 0
        if not self.db.take_lease(REDRIVE_LEASE_NAME, _seconds(now),
                                  _seconds(now - REDRIVE_LEASE)):
            return 0  # another instance is re-driving right now
        ran = 0
        for row in stale:
            left = self.time_left()
            if left is not None and left < REDRIVE_RESERVE:
                break
            tries = self.db.claim_event(int(row["id"]))
            if tries is None:
                continue  # finished meanwhile
            try:
                self.process(int(row["id"]))
                ran += 1
            except Exception as err:  # noqa: BLE001 - logged by type only; it may quote content
                log.warning("re-driven event failed", extra={"event": row["id"], "tries": tries,
                                                             "error": type(err).__name__})
                if tries >= REDRIVE_TRIES:
                    self.db.mark_event(int(row["id"]), "dead", type(err).__name__)
        return ran


def build(db_url: str | None = None, jev: Decider | None = None, llm: LLM | None = None,
          caller: Any = None) -> App:
    from . import calls, fcm

    db = Database(db_url)
    queue: Queue | SqsQueue = SqsQueue(settings.queue_url) if settings.queue_url else Queue()
    sender = notify.OutboxSender(db, wake=fcm.get_waker(db))
    return App(db=db, queue=queue, cascade=Cascade(db, jev or get_decider(), llm or get_llm()),
               gateway=Gateway(db), last=[], sender=sender,
               caller=caller if caller is not None else calls.get_caller())
