"""The background loop inside the one web service.

Jobs: reminders and urgent calls every 30 seconds; college mail at 1 PM and 9 PM India time,
finished over the next turns by mail-continue; Classroom once per mail slot, in its own job;
events a killed run left queued, every 5 minutes (app.App.jobs). Started by the online service
(cloud.py) and the laptop demo.

Why in-process: the prototype is one service on a free host, with no EventBridge; on AWS the
same jobs are scheduled Lambdas (decision 44) calling the same functions.
Why one task per job: a slow mail check (Claude reading fifty mails) never delays a reminder.
Why daily jobs save their last run: a restart does not run the 1 PM check twice, and a check
missed while the service slept runs as soon as it wakes.
Not: retries inside a job. Each job is safe to run again (claims, leases, idempotency keys),
so a failure simply waits for the next turn.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from datetime import datetime, time, timedelta
from typing import Callable

from . import clock
from .db import Database

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class Job:
    name: str
    run: Callable[[], object]
    every: timedelta | None = None  # an interval job ...
    at: tuple[time, ...] = ()  # ... or a daily job at these India times

    def __post_init__(self) -> None:
        if (self.every is None) == (not self.at):
            raise ValueError(f"job {self.name}: give exactly one of every= or at=")


def latest_slot(now: datetime, at: tuple[time, ...]) -> datetime:
    """The most recent scheduled moment at or before `now`: today's, else yesterday's last."""
    local = now.astimezone(clock.IST)
    today = [datetime.combine(local.date(), t, clock.IST) for t in at]
    past = [m for m in today if m <= local]
    if past:
        return max(past)
    return datetime.combine(local.date() - timedelta(days=1), max(at), clock.IST)


class Scheduler:
    def __init__(self, db: Database | Callable[[], Database], jobs: list[Job], *,
                 tick_seconds: float = 15.0, now: Callable[[], datetime] = clock.now) -> None:
        """db: the database, or a function returning the current one (the online service's
        demo reset swaps it)."""
        names = [j.name for j in jobs]
        if len(set(names)) != len(names):
            raise ValueError("job names must be unique")
        self._db, self.jobs, self.tick, self.now = db, jobs, tick_seconds, now
        self._last: dict[str, datetime] = {}  # interval jobs: in memory is enough
        self._tasks: list[asyncio.Task[None]] = []

    @property
    def db(self) -> Database:
        return self._db if isinstance(self._db, Database) else self._db()

    def is_due(self, job: Job, now: datetime) -> bool:
        if job.every is not None:
            last = self._last.get(job.name)
            return last is None or now - last >= job.every
        row = self.db.job(job.name)
        if row is None:
            return True  # never ran: catch up now
        return datetime.fromisoformat(row["last_run_at"]) < latest_slot(now, job.at)

    def run_once(self, job: Job) -> bool:
        """Runs the job if it is due. Returns whether it ran. Never raises."""
        now = self.now()
        try:
            if not self.is_due(job, now):
                return False
        except Exception:  # noqa: BLE001 - a broken jobs row must not stop the loop
            log.exception("job due check failed", extra={"job": job.name})
            return False
        error: str | None = None
        try:
            job.run()
        except Exception as err:  # noqa: BLE001 - logged by type only; it may quote content
            error = type(err).__name__
            log.error("job failed", extra={"job": job.name, "error": error})
        if job.every is not None:
            self._last[job.name] = now
        else:
            try:
                self.db.job_ran(job.name, now.isoformat(timespec="seconds"), error)
            except Exception:  # noqa: BLE001
                log.exception("job record failed", extra={"job": job.name})
        return True

    async def _loop(self, job: Job) -> None:
        while True:
            await asyncio.to_thread(self.run_once, job)
            await asyncio.sleep(self.tick)

    def start(self) -> None:
        """Starts one task per job on the running event loop."""
        if self._tasks:
            return
        self._tasks = [asyncio.create_task(self._loop(job), name=f"job:{job.name}")
                       for job in self.jobs]
        log.info("background jobs started", extra={"jobs": len(self.jobs)})

    async def stop(self) -> None:
        for task in self._tasks:
            task.cancel()
        await asyncio.gather(*self._tasks, return_exceptions=True)
        self._tasks = []
