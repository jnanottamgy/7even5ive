"""The in-app voice assistant: a signed conversation the phone opens itself, and tools that only
ever run through the gateway on the phone's own token."""

from __future__ import annotations

import json
from dataclasses import replace

import httpx
import pytest
from fastapi.testclient import TestClient

from conftest import at
from seventy5 import clock, demo, voice
from seventy5.api import create
from seventy5.gateway import POLICY

AUTH = {"authorization": f"Bearer {demo.TOKEN}"}


@pytest.fixture
def live(monkeypatch):
    from seventy5 import calls

    configured = replace(voice.settings, elevenlabs_api_key="xi",
                         elevenlabs_assistant_agent_id="agent_va",
                         elevenlabs_api="https://api.elevenlabs.io")
    monkeypatch.setattr(voice, "settings", configured)
    monkeypatch.setattr(calls, "settings", configured)


def test_every_voice_tool_is_a_gateway_tool_the_gateway_does_not_deny():
    assert voice.NAMES and all(POLICY.get(name) in ("allow", "ask") for name in voice.NAMES)
    assert not {"send_email", "submit_on_portal"} & set(voice.NAMES)


def test_without_elevenlabs_the_app_is_told_why(make_app):
    a, sid = make_app()
    got = TestClient(create(a)).get("/api/voice/session", headers=AUTH).json()
    assert got == {"available": False,
                   "reason": "The voice assistant needs ElevenLabs set up on the server."}


def test_a_session_is_a_signed_url_the_key_never_leaves(make_app, live):
    a, sid = make_app()
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, json={"signed_url": "wss://api.elevenlabs.io/v1/convai/"
                                                       "conversation?conversation_signature=s1"})

    clock.freeze(at(2030, 1, 7, 8, 0))
    out = voice.session(a.db, sid, http=httpx.Client(transport=httpx.MockTransport(handler)))
    assert seen[0].url.path == "/v1/convai/conversation/get-signed-url"
    assert seen[0].url.params["agent_id"] == "agent_va" and seen[0].headers["xi-api-key"] == "xi"
    assert out["signed_url"].startswith("wss://") and "xi" not in json.dumps(out).replace("wss", "")
    assert out["dynamic_variables"] == {"student_name": "Demo", "today": "Monday 7 January 2030"}
    assert out["tools"] == list(voice.NAMES) and out["max_seconds"] == 300


@pytest.mark.parametrize("response", [httpx.Response(401, json={}),
                                      httpx.Response(200, json={"signed_url": "http://x"})])
def test_a_refused_session_says_so(make_app, live, monkeypatch, response):
    a, sid = make_app()
    real = httpx.Client
    monkeypatch.setattr(voice.httpx, "Client", lambda **kw: real(
        transport=httpx.MockTransport(lambda r: response)))
    r = TestClient(create(a)).get("/api/voice/session", headers=AUTH)
    assert r.status_code == 503 and r.json()["detail"].startswith("The voice service")


def test_a_session_needs_the_students_token(make_app, live):
    a, _ = make_app()
    assert TestClient(create(a)).get("/api/voice/session").status_code == 401


def test_setup_updates_our_tools_by_name_and_locks_the_agent(live):
    calls: list[tuple[str, str, dict | None]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content) if request.content else None
        calls.append((request.method, request.url.path, body))
        if request.method == "GET":
            return httpx.Response(200, json={"tools": [
                {"id": "t_due", "tool_config": {"type": "client", "name": "due_this_week"}},
                {"id": "t_web", "tool_config": {"type": "webhook", "name": "attendance"}}]})
        if request.url.path == "/v1/convai/tools":
            return httpx.Response(200, json={"id": f"t_{body['tool_config']['name']}"})
        return httpx.Response(200, json={"agent_id": "agent_va"})

    agent = voice.setup_assistant(httpx.Client(transport=httpx.MockTransport(handler)))
    assert agent == "agent_va"
    assert ("PATCH", "/v1/convai/tools/t_due") in [(m, p) for m, p, _ in calls]
    created = [b["tool_config"]["name"] for m, p, b in calls if p == "/v1/convai/tools" and m == "POST"]
    assert "attendance" in created and "due_this_week" not in created  # a webhook tool is not ours
    method, path, config = calls[-1]
    assert (method, path) == ("PATCH", "/v1/convai/agents/agent_va")
    prompt = config["conversation_config"]["agent"]["prompt"]
    assert prompt["tool_ids"][0] == "t_due" and len(prompt["tool_ids"]) == len(voice.NAMES)
    assert set(prompt["built_in_tools"]) == {"end_call"}
    assert config["platform_settings"]["auth"]["enable_auth"] is True
    every = [b["tool_config"] for m, p, b in calls if b and "tool_config" in b]
    assert all(t["type"] == "client" and t["expects_response"] for t in every)
