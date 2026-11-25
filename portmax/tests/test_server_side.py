from __future__ import annotations

import asyncio
from datetime import timedelta
from types import SimpleNamespace
from typing import Any

import pytest
from fastapi.testclient import TestClient

from portmax.adapters.gateway import tool_schemas
from portmax.adapters.lambda_handler import handle
from portmax.adapters.mcp_server import build_server
from portmax.api import DevTokens, create_api
from portmax.connector import Connector
from portmax.contract import TOOLS, AttendanceAnswer, utc_now
from portmax.errors import NotConnected, SessionExpired, UnsafePlan
from portmax.ingest import ingest
from portmax.manifest import Manifest
from portmax.mock_portal.data import MockState, expected_attendance, expected_profile
from portmax.pages import Page
from portmax.store import Store
from portmax.tools import answer
from portmax.wakeups import LogNotifier, wake_overdue
from tests.conftest import FakeClock, login, refresh

STUDENT = "student-asha"


@pytest.fixture
def connected(portal: TestClient, connector: Connector, store: Store) -> list[Page]:
    """The student has logged in on the phone, and the first full refresh has been uploaded."""
    login(portal)
    pages = refresh(connector, portal)
    ingest(store, connector, STUDENT, pages, utc_now())
    return pages


def test_a_full_refresh_saves_every_answer_and_no_page(
    connected: list[Page], store: Store, state: MockState
) -> None:
    student = state.student("1MC24CS042")
    attendance = answer(store, STUDENT, "get_attendance", utc_now())
    assert isinstance(attendance, AttendanceAnswer)
    assert attendance.data == expected_attendance(student)
    assert answer(store, STUDENT, "get_profile", utc_now()).data == expected_profile(student)
    login_state = store.login(STUDENT)
    assert login_state is not None and login_state.last_refresh_at is not None
    with store.engine.connect() as db:  # the pages themselves were never written anywhere
        dumped = "\n".join(db.connection.iterdump())  # type: ignore[attr-defined]
    assert "Asha Rao" not in dumped and "<table" not in dumped


def test_a_keep_alive_upload_keeps_the_login_without_a_full_refresh(
    connected: list[Page],
    portal: TestClient,
    connector: Connector,
    store: Store,
    clock: FakeClock,
) -> None:
    before = store.login(STUDENT)
    clock.advance(16 * 60)
    ping = refresh(connector, portal, steps=[connector.plan.keepalive_step])
    result = ingest(store, connector, STUDENT, ping, utc_now() + timedelta(minutes=16))
    after = store.login(STUDENT)
    assert result.saved == ["get_profile"]  # the dashboard only feeds the profile
    assert before is not None and after is not None
    assert after.last_ok_at > before.last_ok_at
    assert after.last_refresh_at == before.last_refresh_at


def test_an_upload_of_the_login_page_marks_the_login_expired(
    connected: list[Page], connector: Connector, store: Store
) -> None:
    dashboard = connected[0]
    login_page = dashboard.model_copy(update={"html": "<form id='pm-login'></form>"})
    with pytest.raises(SessionExpired):
        ingest(store, connector, STUDENT, [login_page], utc_now())
    login_state = store.login(STUDENT)
    assert login_state is not None and login_state.state == "expired"


@pytest.mark.parametrize(
    "tamper",
    [
        {"url": "https://elsewhere.example.com/index.php?task=dashboard"},  # mixed sites
        {"step": "fees"},  # not a step of the plan
        {"url": "http://testserver/index.php?option=com_fees&task=paynow"},  # not read-only
    ],
)
def test_pages_outside_the_plan_are_refused(
    connected: list[Page], connector: Connector, store: Store, tamper: dict[str, Any]
) -> None:
    pages = [*connected[:2], connected[2].model_copy(update=tamper)]
    with pytest.raises(UnsafePlan):
        ingest(store, connector, STUDENT, pages, utc_now())


def test_a_page_that_changed_keeps_the_last_good_answer(
    connected: list[Page], connector: Connector, store: Store
) -> None:
    broken = [
        p.model_copy(update={"html": p.html.replace("Classes held", "Lectures held")})
        if p.step == "course"
        else p
        for p in connected
    ]
    result = ingest(store, connector, STUDENT, broken, utc_now())
    assert "get_attendance" in result.failed
    assert answer(store, STUDENT, "get_attendance", utc_now()).data  # still the earlier answer


def test_answers_say_when_they_are_stale(connected: list[Page], store: Store) -> None:
    later = utc_now() + timedelta(hours=25)
    assert answer(store, STUDENT, "get_attendance", later).stale
    with pytest.raises(NotConnected):
        answer(store, "someone-else", "get_attendance", utc_now())


def test_overdue_phones_are_woken(
    connected: list[Page], connector: Connector, store: Store
) -> None:
    def manifests(_: str) -> Manifest:
        return connector.manifest

    notifier = LogNotifier()
    assert wake_overdue(store, manifests, notifier, utc_now() + timedelta(minutes=10)) == []
    # 20-minute timeout: ping every 16 minutes; at 19 minutes the ping is overdue.
    late = utc_now() + timedelta(minutes=19)
    assert wake_overdue(store, manifests, notifier, late) == [STUDENT]
    assert notifier.woken == [STUDENT]


def gateway_call(tool: str, event: dict[str, Any], store: Store) -> dict[str, Any]:
    context = SimpleNamespace(
        client_context=SimpleNamespace(custom={"bedrockAgentCoreToolName": f"portmax___{tool}"})
    )
    return handle(event, context, store)


def test_the_lambda_answers_the_student_the_gateway_names(
    connected: list[Page], store: Store
) -> None:
    result = gateway_call("get_attendance", {"student_id": STUDENT}, store)
    assert result["tool"] == "get_attendance" and len(result["data"]) == 6
    assert gateway_call("get_attendance", {}, store)["error"]["code"] == "unauthenticated"
    assert gateway_call("delete_everything", {"student_id": STUDENT}, store)["error"]["code"] == (
        "unknown_tool"
    )
    unknown = gateway_call("get_marks", {"student_id": "nobody"}, store)
    assert unknown["error"]["code"] == "not_connected"


def test_the_gateway_schema_lists_the_five_tools_with_no_inputs() -> None:
    schemas = tool_schemas()
    assert [s["name"] for s in schemas] == list(TOOLS)
    assert all(s["inputSchema"]["properties"] == {} for s in schemas)


def test_the_mcp_server_serves_the_same_answers(connected: list[Page], store: Store) -> None:
    server = build_server(store, STUDENT)

    async def call() -> tuple[list[str], Any]:
        tools = [tool.name for tool in await server.list_tools()]
        result = await server.call_tool("get_attendance", {})
        return tools, result

    tools, result = asyncio.run(call())
    assert sorted(tools) == sorted(TOOLS)
    structured = result.structured_content
    assert structured is not None
    payload = structured.get("result", structured)
    assert payload["tool"] == "get_attendance" and len(payload["data"]) == 6


def test_the_phone_api_takes_pages_and_hands_out_the_plan(
    portal: TestClient, connector: Connector, store: Store
) -> None:
    api = TestClient(create_api(store, DevTokens("tok:" + STUDENT), lambda _: connector))
    auth = {"authorization": "Bearer tok"}
    assert api.get("/v1/connectors/mockcollege").status_code == 401
    settings = api.get("/v1/connectors/mockcollege", headers=auth).json()
    assert settings["keepalive_minutes"] == 16 and settings["push_wakeup"] is False
    assert settings["plan"]["keepalive_step"] == "dashboard"
    login(portal)
    pages = [p.model_dump(mode="json") for p in refresh(connector, portal)]
    uploaded = api.post("/v1/pages", json={"college": "mockcollege", "pages": pages}, headers=auth)
    assert uploaded.status_code == 200, uploaded.text
    assert sorted(uploaded.json()["saved"]) == sorted(TOOLS)
    expired = [{**pages[0], "html": "<form id='pm-login'></form>"}]
    gone = api.post("/v1/pages", json={"college": "mockcollege", "pages": expired}, headers=auth)
    assert gone.status_code == 409 and gone.json()["code"] == "session_expired"
