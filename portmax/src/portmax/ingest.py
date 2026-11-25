"""Pages in from the student's phone; answers out to the store; the pages themselves discarded.

The phone ran the fetch plan inside the student's own login and sends us what it fetched. We
check every page is a read-only page of that portal and a logged-in one, parse each tool, keep
only the answers, and never write the HTML anywhere.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any
from urllib.parse import urlsplit

from pydantic import TypeAdapter

from portmax.connector import TOOL_TYPES, Connector
from portmax.contract import ToolName
from portmax.errors import PortalChanged, SessionExpired, UnsafePlan
from portmax.executor import check_session
from portmax.pages import Page, by_step
from portmax.plan import check_path
from portmax.store import Store


@dataclass(frozen=True)
class IngestResult:
    college: str
    fetched_at: datetime
    saved: list[ToolName]
    failed: dict[ToolName, str] = field(default_factory=dict)


def _check_pages(connector: Connector, pages: list[Page]) -> None:
    if not pages:
        raise UnsafePlan("no pages")
    known = {step.id for step in connector.plan.steps}
    origins = {urlsplit(page.url)[:2] for page in pages}
    if len(origins) != 1:
        raise UnsafePlan("pages come from more than one site")
    for page in pages:
        if page.step not in known:
            raise UnsafePlan(f"{page.step} is not a step of this plan")
        parts = urlsplit(page.url)
        check_path(parts.path + (f"?{parts.query}" if parts.query else ""))


def ingest(
    store: Store,
    connector: Connector,
    student_id: str,
    pages: list[Page],
    now: datetime,
) -> IngestResult:
    _check_pages(connector, pages)
    for page in pages:
        try:
            check_session(page, connector.manifest.markers)
        except SessionExpired:
            store.record_expired(student_id, now)
            raise
    # The phone's clock can be wrong; never accept a time from the future.
    fetched_at = min(max(page.fetched_at for page in pages), now)
    grouped = by_step(pages)
    answers: dict[ToolName, Any] = {}
    failed: dict[ToolName, str] = {}
    for tool in connector.manifest.tools:
        needed = connector.plan.tool_steps.get(tool, [])
        if not all(grouped.get(step) for step in needed):
            continue  # this upload did not include that tool's pages (a keep-alive, say)
        try:
            parsed = connector.parse(tool, grouped)
        except PortalChanged as error:
            failed[tool] = error.detail  # keep the last good answer rather than a wrong one
            continue
        answers[tool] = TypeAdapter(TOOL_TYPES[tool]).dump_python(parsed, mode="json")
    store.save_answers(
        student_id, connector.college, connector.manifest.connector_version, fetched_at, answers
    )
    refreshed = set(answers) | set(failed) == set(connector.manifest.tools)
    store.record_ok(student_id, connector.college, now, refreshed=refreshed and not failed)
    return IngestResult(
        college=connector.college, fetched_at=fetched_at, saved=list(answers), failed=failed
    )
