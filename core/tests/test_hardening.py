"""Odd input, the shared demo's limits and the development secrets: refused cleanly, the same
way on SQLite and Postgres, never a crash and never a cost to someone else."""

from __future__ import annotations

import inspect
import json

import pytest
from fastapi.testclient import TestClient

from conftest import file_item
from seventy5 import api as api_module
from seventy5 import calls, config, demo, gateway
from seventy5.api import create
from seventy5.db import BadInput
from seventy5.gateway import Denied
from test_accounts import bearer, signed_in, supa  # noqa: F401 (supa is a fixture)

DEMO = bearer(demo.TOKEN)


def test_the_argument_list_matches_every_tool():
    for name, fn in {**gateway.OWN, **gateway.WRITES}.items():
        params = list(inspect.signature(fn).parameters)[2:]
        assert set(params) == set(gateway.ARGS.get(name, {})), name


@pytest.mark.parametrize("tool, args", [
    ("add_to_calendar", {"item_id": "abc"}),
    ("add_to_calendar", {"item_id": [1]}),
    ("mark_done", {"item_id": 1e400}),
    ("mark_done", {"item_id": 2**70}),
    ("mark_done", {}),
    ("materials", {"subject": {}}),
    ("materials", {"subject": "x" * 500}),
    ("due_this_week", {"student_id": 1}),
    ("set_reminder", {"item_id": 1, "before_minutes": -5}),
    ("list_library_files", {"unsorted": "yes"}),
])
def test_wrong_arguments_are_a_plain_refusal(make_app, tool, args):
    a, sid = make_app()
    with pytest.raises(Denied) as refused:
        a.gateway.call(sid, tool, args)
    assert "got multiple values" not in str(refused.value)


def test_an_approval_with_arguments_its_tool_never_takes_is_refused_and_kept(make_app):
    a, sid = make_app()
    item = file_item(a, sid)
    token = gateway.mint_token(sid, "add_to_calendar", {"item_id": item, "x": 1})
    with pytest.raises(Denied):
        a.gateway.approve(sid, token)
    nonce = gateway.read_token(token)["n"]
    assert a.db.spend_nonce(nonce, "2030-01-01T00:00+05:30")  # still unspent


@pytest.mark.parametrize("bad", ["a\\u0000b", "\\ud800", "x\\u0000"])
def test_text_no_database_can_hold_is_a_400_on_every_engine(make_app, supa, bad):
    """bad is JSON escape text: what an attacker sends (\\u0000 is a NUL, \\ud800 half a
    character); the server's JSON parser turns it into the real thing."""
    a, client, me, sid = signed_in(make_app, supa)
    as_json = {"content-type": "application/json"}
    reply = client.post("/api/me", headers=me | as_json, content='{"name": "%s"}' % bad)
    assert reply.status_code == 400
    login = client.post("/api/auth/login", headers=as_json,
                        content='{"login": "%s", "password": "x"}' % bad)
    assert login.status_code == 400
    device = client.post("/api/devices", headers=me | as_json,
                         content='{"token": "%s", "platform": "android"}' % bad)
    assert device.status_code in (400, 422)
    with pytest.raises(BadInput):
        a.db.student_by_username(json.loads('"%s"' % bad))


def test_an_unsigned_webhook_with_a_huge_timestamp_is_refused_before_parsing(make_app):
    a, _ = make_app()
    client = TestClient(create(a))
    reply = client.post("/bot/webhook", content=b"{}",
                        headers={"x-75-timestamp": "9" * 5000, "x-75-signature": "00"})
    assert reply.status_code == 401


def test_quiet_hours_must_be_text(make_app, supa):
    a, client, me, sid = signed_in(make_app, supa)
    assert client.post("/api/settings/calls", headers=me,
                       json={"quiet_start": 5}).status_code == 400


def test_a_very_long_login_never_becomes_a_rate_limit_key(make_app, supa):
    a, client, me, sid = signed_in(make_app, supa)
    reply = client.post("/api/auth/login", json={"login": "x" * 100000, "password": "p"})
    assert reply.status_code == 400
    assert all(len(k) <= 300 for k in api_module._login_by_name._hits)


# --- the shared demo (its token is public) ------------------------------------------------------
def test_the_demo_never_uses_a_real_number(make_app, monkeypatch):
    monkeypatch.setenv("DEMO_PHONE", "919812345678")
    a, sid = make_app()
    assert a.db.student(sid)["wa_phone"] == demo.PHONE == "919900000001"
    assert calls.phone_for(a.db.student(sid)) is None  # no DEMO_STUDENT_PHONE: never rung


def test_a_demo_reset_keeps_the_calls_and_audit_its_daily_limits_count(make_app):
    a, sid = make_app()
    a.db.audit(sid, "demo_voice", "allow", "demo", "2030-01-01T10:00+05:30")
    with a.db.tx() as c:
        c.execute("INSERT INTO calls(student_id, status, provider, created_at) VALUES"
                  " (?,?,?,?)", (sid, "placed", "log", "2030-01-01T10:00+05:30"))
    demo.seed(a)
    assert a.db.conn.execute("SELECT COUNT(*) AS n FROM calls WHERE student_id=?",
                             (sid,)).fetchone()["n"] == 1
    assert a.db.audit_count(sid, "demo_voice", "2030-01-01T00:00+05:30") == 1


def test_the_demos_voice_sessions_are_capped(make_app, monkeypatch):
    a, sid = make_app()
    client = TestClient(create(a))
    monkeypatch.setattr(api_module, "_demo_voice_by_ip", api_module.auth.Limiter(100, 3600))
    monkeypatch.setattr(api_module, "DEMO_VOICE_PER_DAY", 2)
    answers = [client.get("/api/voice/session", headers=DEMO).status_code for _ in range(3)]
    assert answers[:2] != [429, 429] and answers[2] == 429


def test_the_demos_new_briefing_clips_are_capped(make_app, monkeypatch, tmp_path):
    from seventy5 import briefing

    a, sid = make_app()
    client = TestClient(create(a))
    made = []
    monkeypatch.setattr(briefing, "speak", lambda text, http=None: made.append(text) or b"ID3")
    monkeypatch.setattr(briefing, "_cache_path",
                        lambda sid, day, text: tmp_path / f"{sid}-{day}-{hash(text)}.mp3")
    monkeypatch.setattr(api_module, "DEMO_AUDIO_PER_DAY", 1)
    first = client.get("/api/briefing/audio", headers=DEMO)
    assert first.status_code == 200 and len(made) == 1
    again = client.get("/api/briefing/audio", headers=DEMO)  # the same text: from the cache
    assert again.status_code == 200 and len(made) == 1
    monkeypatch.setattr(briefing, "build", lambda db, sid, now=None: {
        "day": "2030-01-01", "text": "A changed briefing needs a new clip."})
    changed = client.get("/api/briefing/audio", headers=DEMO)
    assert changed.status_code == 503 and len(made) == 1  # the day's cap: the phone reads it


# --- the development secrets on a deployed server --------------------------------------------------
def test_approvals_refuse_the_public_secret_on_a_deployed_server(make_app, monkeypatch):
    a, sid = make_app()
    item = file_item(a, sid)
    monkeypatch.setenv("AWS_LAMBDA_FUNCTION_NAME", "7even5ive")
    with pytest.raises(Denied) as refused:
        a.gateway.call(sid, "add_to_calendar", {"item_id": item})
    assert refused.value.status == 503
    monkeypatch.delenv("AWS_LAMBDA_FUNCTION_NAME")
    assert a.gateway.call(sid, "add_to_calendar", {"item_id": item})["status"] == "approval_needed"


def test_google_refuses_the_public_key_on_a_deployed_server(make_app, supa, monkeypatch):
    a, client, me, sid = signed_in(make_app, supa)
    monkeypatch.setenv("AWS_LAMBDA_FUNCTION_NAME", "7even5ive")
    reply = client.post("/api/google/start", headers=me)
    assert reply.status_code == 503 and "isn't set up" in reply.json()["detail"]


def test_deployed_means_lambda_or_postgres(monkeypatch):
    monkeypatch.delenv("AWS_LAMBDA_FUNCTION_NAME", raising=False)
    monkeypatch.setenv("DATABASE_URL", "/tmp/x.db")
    assert not config.deployed()
    monkeypatch.setenv("DATABASE_URL", "postgresql+psycopg://u@h/db")
    assert config.deployed()


# --- the urgent call's outcome and ElevenLabs' privacy settings ----------------------------------
def test_only_outcome_events_count_and_answered_is_final(make_app):
    from seventy5 import calls

    a, sid = make_app()
    with a.db.tx() as c:
        c.execute("INSERT INTO calls(student_id, status, provider, provider_id, created_at)"
                  " VALUES (?,?,?,?,?)", (sid, "placed", "twilio", "conv_1",
                                          "2030-01-01T10:00+05:30"))
    answered = {"type": "post_call_transcription",
                "data": {"conversation_id": "conv_1", "status": "done",
                         "metadata": {"call_duration_secs": 42, "termination_reason": "end_call"}}}
    assert calls.handle_webhook(a.db, a.sender, answered)["outcome"] == "answered"
    audio = {"type": "post_call_audio", "data": {"conversation_id": "conv_1", "full_audio": "..."}}
    assert calls.handle_webhook(a.db, a.sender, audio) == {"matched": False}
    late = {"type": "call_initiation_failure", "data": {"conversation_id": "conv_1"}}
    assert calls.handle_webhook(a.db, a.sender, late)["outcome"] == "answered"
    row = a.db.conn.execute("SELECT status FROM calls WHERE provider_id='conv_1'").fetchone()
    assert row["status"] == "answered" and a.db.notifications(sid, 0) == []


def test_elevenlabs_keeps_no_recording_and_no_conversation_for_ever():
    from seventy5 import calls, voice

    for config in (calls.agent_config(), voice.assistant_config(["t1"])):
        privacy = config["platform_settings"]["privacy"]
        assert privacy["record_voice"] is False and 0 < privacy["retention_days"] <= 30


def test_an_approval_on_a_server_without_its_secret_says_not_set_up(make_app, monkeypatch):
    a, sid = make_app()
    item = file_item(a, sid)
    client = TestClient(create(a))
    monkeypatch.setenv("AWS_LAMBDA_FUNCTION_NAME", "7even5ive")
    reply = client.post("/api/tools/add_to_calendar", headers=DEMO, json={"args": {"item_id": item}})
    assert reply.status_code == 503 and "aren't set up" in reply.json()["detail"]
