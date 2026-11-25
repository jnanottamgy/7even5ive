"""The five tools, answered from what the student's last refresh saved. No portal call here."""

from __future__ import annotations

from datetime import datetime, timedelta

from portmax.contract import ANSWER_MODELS, Answer, ToolName
from portmax.errors import NotConnected
from portmax.store import Store

# Attendance changes daily, so an answer more than a day old is flagged; the briefing says so.
STALE_AFTER = timedelta(hours=24)


def answer(
    store: Store,
    student_id: str,
    tool: ToolName,
    now: datetime,
    *,
    stale_after: timedelta = STALE_AFTER,
) -> Answer:
    snapshot = store.snapshot(student_id, tool)
    if snapshot is None:
        raise NotConnected(f"no {tool} saved yet: connect the portal in the app")
    return ANSWER_MODELS[tool].model_validate(
        {
            "college": snapshot.college,
            "connector_version": snapshot.connector_version,
            "fetched_at": snapshot.fetched_at,
            "stale": now - snapshot.fetched_at > stale_after,
            "data": snapshot.data,
        }
    )
