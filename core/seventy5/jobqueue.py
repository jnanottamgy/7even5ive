"""The queue between ingress and the workers.

Locally an in-process list; on AWS it is SQS with a dead-letter queue (see aws.py). Both
retry a failed event up to MAX_ATTEMPTS, then park it as 'dead' for a human to look at.
Why a queue at all: a slow model call never holds a webhook open, and a crash mid-run
retries instead of losing the message.
Not: Celery/Redis -- SQS is managed and free at this volume.
"""

from __future__ import annotations

import logging
from collections import deque
from typing import Callable

log = logging.getLogger(__name__)
MAX_ATTEMPTS = 3


class Queue:
    def __init__(self) -> None:
        self._items: deque[int] = deque()

    def send(self, event_id: int) -> None:
        self._items.append(event_id)

    def drain(self, handle: Callable[[int], None], on_dead: Callable[[int, str], None]) -> int:
        """Run every queued event. Returns how many finished."""
        done = 0
        while self._items:
            event_id = self._items.popleft()
            for attempt in range(1, MAX_ATTEMPTS + 1):
                try:
                    handle(event_id)
                    done += 1
                    break
                except Exception as err:  # any failure retries; the last one dead-letters
                    log.warning("event failed", extra={"event": event_id, "attempt": attempt})
                    if attempt == MAX_ATTEMPTS:
                        on_dead(event_id, type(err).__name__)
        return done
