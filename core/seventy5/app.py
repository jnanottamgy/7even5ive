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
from .jobqueue import Queue
from .llm import LLM, get_llm

log = logging.getLogger(__name__)


@dataclass
class App:
    db: Database
    queue: Queue
    cascade: Cascade
    gateway: Gateway
    last: list[Outcome]

    def work(self) -> list[Outcome]:
        """Drain the queue through the cascade (on AWS: the cascade Lambda on SQS)."""
        outcomes: list[Outcome] = []

        def handle(event_id: int) -> None:
            outcome = self.cascade.run(event_id)
            self.db.mark_event(event_id, "done")
            outcomes.append(outcome)
            log.info("event %s -> %s/%s", event_id, outcome.route, outcome.status)

        self.queue.drain(handle, lambda eid, err: self.db.mark_event(eid, "dead", err))
        self.last = outcomes
        return outcomes


def build(db_path: str | None = None, jev: Decider | None = None, llm: LLM | None = None) -> App:
    db = Database(db_path)
    return App(db=db, queue=Queue(), cascade=Cascade(db, jev or get_decider(), llm or get_llm()),
               gateway=Gateway(db), last=[])
