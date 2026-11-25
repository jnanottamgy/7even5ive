"""Wiring: one place builds the database, queue, cascade and gateway.

Why: the web API, the MCP server, the demo script and the tests all need the same
objects, and tests swap in scripted Jev / LLM here without touching anything else.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

from .cascade import Cascade, Outcome
from .db import Database
from .gateway import Gateway
from .jev import Decider, get_decider
from .config import settings
from .jobqueue import Queue, SqsQueue
from .llm import LLM, get_llm

log = logging.getLogger(__name__)


@dataclass
class App:
    db: Database
    queue: Queue | SqsQueue
    cascade: Cascade
    gateway: Gateway
    last: list[Outcome]

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


def build(db_url: str | None = None, jev: Decider | None = None, llm: LLM | None = None) -> App:
    db = Database(db_url)
    queue: Queue | SqsQueue = SqsQueue(settings.queue_url) if settings.queue_url else Queue()
    return App(db=db, queue=queue, cascade=Cascade(db, jev or get_decider(), llm or get_llm()),
               gateway=Gateway(db), last=[])
