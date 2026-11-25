"""Ingress: verify who sent an event, give it an idempotency key, put it on the queue.

Why HMAC over timestamp + body: the bot signs each push, so a forged or replayed request
fails before it costs a model call. compare_digest keeps the check constant-time.
Why the key comes from the source's own id (wamid, Gmail message id): redeliveries
collide on the UNIQUE constraint and are dropped, so Gmail's 2-3x pushes cost one run.
Not: answering inside the webhook. It returns at once; the worker does the work.
"""

from __future__ import annotations

import hashlib
import hmac
import time
from typing import Any

from . import clock
from .config import settings
from .db import Database
from .jobqueue import Queue


class BadSignature(Exception):
    pass


def sign(body: bytes, timestamp: int, secret: str | None = None) -> str:
    key = (secret or settings.bot_secret).encode()
    return hmac.new(key, f"{timestamp}.".encode() + body, hashlib.sha256).hexdigest()


def verify(body: bytes, timestamp: str | None, signature: str | None,
           now: float | None = None) -> None:
    if not timestamp or not signature or not timestamp.isdigit():
        raise BadSignature("missing signature")
    if abs((now or time.time()) - int(timestamp)) > settings.bot_max_skew_seconds:
        raise BadSignature("stale timestamp")
    if not hmac.compare_digest(sign(body, int(timestamp)), signature):
        raise BadSignature("bad signature")


def accept(db: Database, queue: Queue, student_id: int, source: str, source_id: str,
           payload: dict[str, Any]) -> int | None:
    """Store and enqueue. Returns the event id, or None for a duplicate delivery."""
    event_id = db.insert_event(student_id, f"{source}:{source_id}", source, payload,
                               clock.iso(clock.now()))
    if event_id is not None:
        queue.send(event_id)
    return event_id
