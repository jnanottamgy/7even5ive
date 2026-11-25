"""Which phones to wake so their keep-alive runs on time.

Android runs the keep-alive with WorkManager, but an idle phone batches background work and can
run it late, past the portal's idle timeout. Our server knows when each student's last ping
landed; when one is overdue, it sends a push message that wakes the app to ping right away.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime, timedelta
from typing import Protocol

from portmax.manifest import Manifest, keepalive_interval_minutes
from portmax.store import Store

# A ping this late is overdue; the margin inside the interval still covers the session.
GRACE = timedelta(minutes=2)


class Notifier(Protocol):
    def wake(self, student_id: str) -> None: ...


class LogNotifier:
    """Development stand-in for Firebase Cloud Messaging: records who would have been woken."""

    def __init__(self) -> None:
        self.woken: list[str] = []

    def wake(self, student_id: str) -> None:
        self.woken.append(student_id)


def overdue(store: Store, manifests: Callable[[str], Manifest], now: datetime) -> list[str]:
    due: list[str] = []
    for login in store.connected():
        interval = timedelta(minutes=keepalive_interval_minutes(manifests(login.college).session))
        if now - login.last_ok_at > interval + GRACE:
            due.append(login.student_id)
    return due


def wake_overdue(
    store: Store, manifests: Callable[[str], Manifest], notifier: Notifier, now: datetime
) -> list[str]:
    due = overdue(store, manifests, now)
    for student_id in due:
        notifier.wake(student_id)
    return due
