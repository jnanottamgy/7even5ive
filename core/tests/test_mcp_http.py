"""MCP over HTTP on the online service: the student's own AI gets the gateway's rules, nothing
more, with the student named by a Bearer token on every request."""

from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient

from conftest import at, file_item
from seventy5 import clock, demo
from seventy5.cloud import Router
from seventy5.mcp_server import http_app
from seventy5.db import token_hash

HEADERS = {"authorization": f"Bearer {demo.TOKEN}", "accept": "application/json, text/event-stream",
           "content-type": "application/json"}


@pytest.fixture
def mcp(make_app):
    a, sid = make_app()
    router = Router(core=None, portmax=None, portal=None)
    router.app = a
    router.mcp = http_app(lambda: router.app)
    client = TestClient(router)
    counter = {"id": 0}

    def rpc(method: str, params: dict | None = None, headers: dict | None = None):
        counter["id"] += 1
        body = {"jsonrpc": "2.0", "id": counter["id"], "method": method, "params": params or {}}
        return client.post("/mcp", content=json.dumps(body), headers=headers or HEADERS)

    return a, sid, rpc


def tool(rpc, name: str, **args):
    reply = rpc("tools/call", {"name": name, "arguments": args})
    assert reply.status_code == 200, reply.text
    return reply.json()["result"]


def test_initialize_and_list_the_tools(mcp):
    a, sid, rpc = mcp
    init = rpc("initialize", {"protocolVersion": "2025-06-18", "capabilities": {},
                              "clientInfo": {"name": "claude-test", "version": "1"}}).json()
    assert init["result"]["serverInfo"]["name"] == "7even5ive"
    names = {t["name"] for t in rpc("tools/list").json()["result"]["tools"]}
    assert {"due_this_week", "briefing", "timetable_today", "check_mail_now", "mark_done",
            "reopen", "add_to_calendar", "attendance"} <= names
    assert not {"send_email", "submit_on_portal"} & names


def test_a_read_comes_back_as_the_gateway_answered(mcp):
    a, sid, rpc = mcp
    item = file_item(a, sid, due="2030-01-04T23:59")
    clock.freeze(at(2030, 1, 1, 9))
    result = tool(rpc, "due_this_week")
    answer = json.loads(result["content"][0]["text"])
    assert not result["isError"] and answer["status"] == "ok"
    assert [c["id"] for c in answer["result"]] == [item]


def test_a_write_still_waits_for_the_tap(mcp):
    a, sid, rpc = mcp
    item = file_item(a, sid, due="2030-01-04T23:59")
    result = tool(rpc, "add_to_calendar", item_id=item)
    assert "approval_needed" in result["content"][0]["text"]
    assert len(a.db.pending(sid)) == 1 and a.db.calendar(sid) == []


def test_a_refused_call_is_a_tool_error_not_a_crash(mcp):
    a, sid, rpc = mcp
    result = tool(rpc, "mark_done", item_id=999)
    assert result["isError"] and "denied" in result["content"][0]["text"]


def test_no_token_no_mcp(mcp):
    a, sid, rpc = mcp
    reply = rpc("tools/list", headers={k: v for k, v in HEADERS.items() if k != "authorization"})
    assert reply.status_code == 401 and reply.headers["www-authenticate"].startswith("Bearer")
    wrong = rpc("tools/list", headers={**HEADERS, "authorization": "Bearer guess"})
    assert wrong.status_code == 401


def test_each_request_is_its_own_student(mcp):
    a, sid, rpc = mcp
    with a.db.tx() as c:
        c.execute("INSERT INTO students(name, token_hash) VALUES ('B', ?)", (token_hash('tok-b'),))
    mine = file_item(a, sid, due="2030-01-04T23:59")
    clock.freeze(at(2030, 1, 1, 9))
    theirs = json.loads(tool(rpc, "due_this_week")["content"][0]["text"])
    other = rpc("tools/call", {"name": "due_this_week", "arguments": {}},
                headers={**HEADERS, "authorization": "Bearer tok-b"}).json()["result"]
    assert [c["id"] for c in theirs["result"]] == [mine]
    assert json.loads(other["content"][0]["text"])["result"] == []
