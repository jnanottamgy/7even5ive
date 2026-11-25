"""The production doors: two AWS Lambda handlers.

`tool_handler` is AgentCore Gateway's Lambda target for `get_opportunities`. The student is
whoever the gateway authenticated: our REQUEST interceptor writes `student_id` from the
verified token, so this function trusts that field and nothing else about identity. The tool
name arrives in the Lambda context as `<target>___<tool>`; check the event shape against AWS's
current Lambda-target documentation before the first deploy.

`check_handler` runs the checks: EventBridge invokes it at 1 PM and 9 PM India time
(`mailfilter schedule` prints the cron expressions), and the app backend invokes it with
`{"action": "check_now", "student_id": ...}` for the "check now" button.
"""

from __future__ import annotations

import logging
import os
from collections.abc import Callable
from datetime import datetime
from functools import cache
from typing import Any

from mailfilter.adapters.gateway import TOOL
from mailfilter.config import Settings
from mailfilter.contract import KEPT_KINDS, KeptKind
from mailfilter.errors import GmailConfigError, MailFilterError
from mailfilter.gmail import Mailbox
from mailfilter.judge import ClaudeJudge, Judge
from mailfilter.run import check_all, check_now
from mailfilter.store import Store
from mailfilter.timekit import utc_now
from mailfilter.tools import opportunities_answer
from mailfilter.wiring import gmail_mailbox, google_tokens

TOOL_NAME_KEY = "bedrockAgentCoreToolName"
log = logging.getLogger("mailfilter")


@cache
def _settings() -> Settings:
    return Settings.from_env()


@cache
def _store() -> Store:
    # Created once per warm Lambda; the schema is owned by migrations in production.
    return Store(_settings().database_url, create=False)


@cache
def _judge() -> ClaudeJudge:
    return ClaudeJudge.from_settings(_settings())


def _error(code: str, detail: str) -> dict[str, Any]:
    return {"error": {"code": code, "detail": detail}}


def tool_name(event: dict[str, Any], context: Any) -> str | None:
    custom = getattr(getattr(context, "client_context", None), "custom", None) or {}
    raw = custom.get(TOOL_NAME_KEY) or event.get("tool") or ""
    name = str(raw).split("___")[-1]
    return name if name == TOOL else None


def parse_arguments(event: dict[str, Any]) -> tuple[KeptKind | None, int | None, bool]:
    kind = event.get("kind")
    if kind is not None and kind not in KEPT_KINDS:
        raise ValueError("kind")
    within = event.get("within_days")
    if within is not None and (
        isinstance(within, bool) or not isinstance(within, int) or not 1 <= within <= 90
    ):
        raise ValueError("within_days")
    include_past = event.get("include_past", False)
    if not isinstance(include_past, bool):
        raise ValueError("include_past")
    return kind, within, include_past


def handle_tool(
    event: dict[str, Any], context: Any, store: Store, settings: Settings, now: datetime
) -> dict[str, Any]:
    if tool_name(event, context) is None:
        return _error("unknown_tool", "not a mail filter tool")
    student_id = event.get("student_id")
    if not isinstance(student_id, str) or not student_id:
        return _error("unauthenticated", "no student on this call")
    try:
        kind, within, include_past = parse_arguments(event)
    except ValueError as error:
        return _error("bad_arguments", str(error))
    try:
        answer = opportunities_answer(
            store, student_id, now, settings, kind=kind, within_days=within,
            include_past=include_past,
        )  # fmt: skip
    except MailFilterError as error:
        return _error(error.code, error.detail)
    return answer.model_dump(mode="json")


def tool_handler(event: dict[str, Any], context: Any) -> dict[str, Any]:
    return handle_tool(event, context, _store(), _settings(), utc_now())


def handle_check(
    event: dict[str, Any],
    store: Store,
    settings: Settings,
    judge: Judge,
    mailbox_for: Callable[[str], Mailbox],
    now: Callable[[], datetime],
    time_left: Callable[[], float] | None,
) -> dict[str, Any]:
    action = event.get("action")
    if event.get("source") == "aws.events" or action == "scheduled":
        results = check_all(store, mailbox_for, judge, settings, now=now, time_left=time_left)
        errors: dict[str, int] = {}
        for result in results:
            if result.error:
                errors[result.error] = errors.get(result.error, 0) + 1
        return {
            "checked": len(results),
            "cards_new": sum(r.carded for r in results),
            "cards_updated": sum(r.updated for r in results),
            "errors": errors,
        }
    if action == "check_now":
        student_id = event.get("student_id")
        if not isinstance(student_id, str) or not student_id:
            return _error("unauthenticated", "no student on this call")
        try:
            result = check_now(store, mailbox_for(student_id), judge, student_id, settings, now=now)
        except MailFilterError as error:
            return _error(error.code, error.detail)
        return {
            "status": result.status,
            "error": result.error,
            "listed": result.listed,
            "cards_new": result.carded,
            "cards_updated": result.updated,
            "more": result.more,
        }
    return _error("unknown_action", "expected a schedule event or check_now")


def _mailbox_for(settings: Settings) -> Callable[[str], Mailbox]:
    if not os.environ.get("MAILFILTER_TOKEN_FILE"):
        # Production reads Google tokens from AgentCore Identity; until that is wired, refuse
        # loudly rather than look for a token file that a Lambda does not have.
        def missing(student_id: str) -> Mailbox:
            raise GmailConfigError("token_source_not_configured")

        return missing
    tokens = google_tokens(settings)
    return lambda student_id: gmail_mailbox(tokens, student_id, settings)


def check_handler(event: dict[str, Any], context: Any) -> dict[str, Any]:
    settings = _settings()

    def time_left() -> float:
        return float(context.get_remaining_time_in_millis()) / 1000.0

    return handle_check(
        event,
        _store(),
        settings,
        _judge(),
        _mailbox_for(settings),
        utc_now,
        time_left if hasattr(context, "get_remaining_time_in_millis") else None,
    )
