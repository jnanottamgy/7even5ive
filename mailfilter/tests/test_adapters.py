from __future__ import annotations

import asyncio
from datetime import datetime
from types import SimpleNamespace
from typing import Any

import pytest

from mailfilter.adapters import lambda_handler
from mailfilter.adapters.gateway import TOOL, tool_schemas
from mailfilter.adapters.lambda_handler import handle_check, handle_tool
from mailfilter.adapters.mcp_server import build_server
from mailfilter.config import Settings
from mailfilter.errors import GmailConfigError
from mailfilter.fake import STUDENT_ADDRESS, FakeMailbox
from mailfilter.gmail import Mailbox
from mailfilter.run import check_mailbox
from mailfilter.samples import fake_mails, golden_judge
from mailfilter.store import Store
from mailfilter.timekit import IST
from tests.conftest import MONDAY, STUDENT, Clock

FRIDAY = datetime(2026, 12, 4, 1, 0, tzinfo=IST)


@pytest.fixture
def week(store: Store, settings: Settings, clock: Clock) -> Store:
    store.connect(STUDENT, STUDENT_ADDRESS, MONDAY)
    check_mailbox(store, FakeMailbox(fake_mails(), now=clock), golden_judge(), STUDENT, settings,
                  now=clock)  # fmt: skip
    return store


def gateway(tool: str) -> SimpleNamespace:
    return SimpleNamespace(
        client_context=SimpleNamespace(custom={"bedrockAgentCoreToolName": f"mail___{tool}"})
    )


def call(
    store: Store, settings: Settings, event: dict[str, Any], tool: str = TOOL
) -> dict[str, Any]:
    return handle_tool(event, gateway(tool), store, settings, FRIDAY)


def test_the_gateway_schema_never_asks_for_the_student() -> None:
    [schema] = tool_schemas()
    assert schema["name"] == "get_opportunities"
    assert set(schema["inputSchema"]["properties"]) == {"kind", "within_days", "include_past"}
    assert "student_id" not in str(schema) and schema["inputSchema"]["required"] == []


def test_the_lambda_answers_the_student_the_gateway_names(week: Store, settings: Settings) -> None:
    answer = call(week, settings, {"student_id": STUDENT, "kind": "placement"})
    assert answer["tool"] == "get_opportunities"
    assert {card["kind"] for card in answer["data"]} == {"placement"}
    assert answer["data"][0]["deadline"] == "2026-12-04T11:00:00+05:30"


@pytest.mark.parametrize(
    ("event", "tool", "code"),
    [
        ({"student_id": STUDENT}, "delete_mail", "unknown_tool"),
        ({}, TOOL, "unauthenticated"),
        ({"student_id": STUDENT, "kind": "spam"}, TOOL, "bad_arguments"),
        ({"student_id": STUDENT, "within_days": 0}, TOOL, "bad_arguments"),
        ({"student_id": STUDENT, "within_days": True}, TOOL, "bad_arguments"),
        ({"student_id": STUDENT, "include_past": "yes"}, TOOL, "bad_arguments"),
        ({"student_id": "nobody"}, TOOL, "not_connected"),
    ],
)
def test_the_lambda_refuses_by_name(
    week: Store, settings: Settings, event: dict[str, Any], tool: str, code: str
) -> None:
    assert call(week, settings, event, tool)["error"]["code"] == code


def test_scheduled_and_check_now_events(store: Store, settings: Settings, clock: Clock) -> None:
    store.connect(STUDENT, STUDENT_ADDRESS, MONDAY)
    store.connect("second", "two@mockcollege.edu.in", MONDAY)

    def mailbox_for(student_id: str) -> Mailbox:
        return FakeMailbox(fake_mails(), now=clock)

    scheduled = handle_check(
        {"source": "aws.events", "detail-type": "Scheduled Event"}, store, settings,
        golden_judge(), mailbox_for, clock, None,
    )  # fmt: skip
    assert scheduled == {"checked": 2, "cards_new": 34, "cards_updated": 4, "errors": {}}
    clock.advance(minutes=1)
    too_soon = handle_check({"action": "check_now", "student_id": STUDENT}, store, settings,
                            golden_judge(), mailbox_for, clock, None)  # fmt: skip
    assert too_soon["error"]["code"] == "too_soon"
    clock.advance(minutes=10)
    now = handle_check({"action": "check_now", "student_id": STUDENT}, store, settings,
                       golden_judge(), mailbox_for, clock, None)  # fmt: skip
    assert now["error"] is None and now["status"] == "connected" and now["cards_new"] == 0
    assert handle_check({"action": "check_now"}, store, settings, golden_judge(), mailbox_for,
                        clock, None)["error"]["code"] == "unauthenticated"  # fmt: skip
    assert handle_check({"action": "delete"}, store, settings, golden_judge(), mailbox_for, clock,
                        None)["error"]["code"] == "unknown_action"  # fmt: skip


def test_without_a_token_source_checks_fail_loudly(
    store: Store, settings: Settings, clock: Clock, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("MAILFILTER_TOKEN_FILE", raising=False)
    store.connect(STUDENT, STUDENT_ADDRESS, MONDAY)
    mailbox_for = lambda_handler._mailbox_for(settings)
    with pytest.raises(GmailConfigError):
        mailbox_for(STUDENT)
    result = handle_check({"source": "aws.events"}, store, settings, golden_judge(), mailbox_for,
                          clock, None)  # fmt: skip
    assert result["errors"] == {"gmail_config": 1}
    connection = store.connection(STUDENT)
    assert connection is not None and connection.last_error == "gmail_config"


def test_the_mcp_server_serves_the_same_cards(week: Store, settings: Settings) -> None:
    server = build_server(week, STUDENT, settings)

    async def ask() -> tuple[list[str], Any]:
        tools = [tool.name for tool in await server.list_tools()]
        result = await server.call_tool("get_opportunities", {"kind": "exam_notice"})
        return tools, result

    tools, result = asyncio.run(ask())
    assert tools == ["get_opportunities"]
    structured = result.structured_content
    assert structured is not None
    payload = structured.get("result", structured)
    assert {card["kind"] for card in payload["data"]} == {"exam_notice"}


def test_the_mcp_server_refuses_bad_input_and_unknown_students(
    week: Store, settings: Settings
) -> None:
    async def ask(student: str, arguments: dict[str, Any]) -> Any:
        return await build_server(week, student, settings).call_tool("get_opportunities", arguments)

    for student, arguments in (("nobody", {}), (STUDENT, {"within_days": 500})):
        try:
            result = asyncio.run(ask(student, arguments))
        except Exception as error:  # noqa: BLE001 - either form of refusal is fine
            assert "not_connected" in str(error) or "bad_arguments" in str(error)
        else:
            assert getattr(result, "is_error", False)
