"""The rules that must hold whatever the model says.

Why these: they are the claims the deck makes (signed events, dedupe, Jev drops only at
high confidence, the LLM is gated, deny by default, one-time approvals, exact attendance).
"""

from __future__ import annotations

import json
import time

import pytest
from fastapi.testclient import TestClient

from seventy5 import demo
from seventy5.api import create
from seventy5.app import build
from seventy5.gateway import Denied
from seventy5.ingress import BadSignature, accept, sign, verify
from seventy5.jev import JevError, Likely, Picked, ScriptedDecider
from seventy5.llm import Proposal, ScriptedLLM
from seventy5 import tools


@pytest.fixture
def app(tmp_path, monkeypatch):
    from portmax.store import Store
    monkeypatch.setattr(tools, "_portal", Store(f"sqlite:///{tmp_path.as_posix()}/pm.db"))

    def make(jev=None, llm=None):
        a = build(str(tmp_path / "t.db"), jev=jev or ScriptedDecider({}), llm=llm or ScriptedLLM({}))
        return a, demo.seed(a)
    return make


def run(a, sid, text, source="whatsapp", **extra):
    accept(a.db, a.queue, sid, source, f"id-{text}-{source}", {"text": text, **extra})
    return a.work()[0]


# --- ingress --------------------------------------------------------------------------
def test_signature_accepts_fresh_and_rejects_tampered_or_stale():
    body, ts = b'{"x":1}', int(time.time())
    verify(body, str(ts), sign(body, ts))
    with pytest.raises(BadSignature):
        verify(b'{"x":2}', str(ts), sign(body, ts))
    with pytest.raises(BadSignature):
        verify(body, str(ts - 3600), sign(body, ts - 3600))


def test_redelivery_is_processed_once(app):
    a, sid = app(jev=ScriptedDecider({"kind": Picked("chitchat", .99)}))
    assert accept(a.db, a.queue, sid, "whatsapp", "wamid.1", {"text": "ok"}) is not None
    assert accept(a.db, a.queue, sid, "whatsapp", "wamid.1", {"text": "ok"}) is None
    assert len(a.work()) == 1


def test_webhook_ignores_unknown_numbers_and_bad_signatures(app):
    a, _ = app()
    client = TestClient(create(a))
    body = json.dumps({"from": "910000000000", "message_id": "m1", "text": "hi"}).encode()
    ts = int(time.time())
    assert client.post("/bot/webhook", content=body,
                       headers={"x-75-timestamp": str(ts), "x-75-signature": "bad"}).status_code == 401
    ok = client.post("/bot/webhook", content=body,
                     headers={"x-75-timestamp": str(ts), "x-75-signature": sign(body, ts)})
    assert ok.status_code == 200 and a.db.conn.execute("SELECT COUNT(*) FROM events").fetchone()[0] == 0


# --- cascade --------------------------------------------------------------------------
def test_jev_files_a_material_alone(app):
    llm = ScriptedLLM({})
    a, sid = app(jev=ScriptedDecider({"kind": Picked("material", .95), "subject": Picked("Database Management Systems", .9)}),
                 llm=llm)
    out = run(a, sid, "unit 3 notes", attachment="DBMS_U3.pdf")
    assert (out.route, out.status) == ("jev", "filed") and llm.calls == []


def test_chitchat_needs_high_confidence_to_drop(app):
    llm = ScriptedLLM({"ok": Proposal("chitchat", "Miscellaneous", "", None)})
    a, sid = app(jev=ScriptedDecider({"kind": Picked("chitchat", .85)}), llm=llm)
    out = run(a, sid, "ok")
    assert out.route == "llm" and len(llm.calls) == 1  # 0.85 < 0.9: the LLM decides


def test_dated_items_go_to_the_llm_with_jev_hints(app):
    text = "DBMS assignment due Fri"
    llm = ScriptedLLM({text: Proposal("deadline", "Database Management Systems", "DBMS assignment", "2030-01-04T23:59")})
    a, sid = app(jev=ScriptedDecider({"kind": Picked("deadline", .95), "subject": Picked("Database Management Systems", .9)}),
                 llm=llm)
    out = run(a, sid, text)
    assert out.route == "jev+llm" and llm.calls[0]["hints"] == {"kind": "deadline", "subject": "Database Management Systems"}


def test_jev_failure_falls_through_to_the_llm(app):
    text = "lab moved to thu"
    llm = ScriptedLLM({text: Proposal("notice", "Computer Networks", "Lab moved to Thu", None)})
    a, sid = app(jev=ScriptedDecider(JevError("down")), llm=llm)
    assert run(a, sid, text).route == "llm"


def test_gate_rejects_an_invented_subject(app):
    text = "physics quiz tomorrow"
    llm = ScriptedLLM({text: Proposal("exam", "Physics", "Quiz", "2030-01-01T09:00")})
    a, sid = app(llm=llm)
    assert run(a, sid, text).status == "needs_review"


def test_email_spam_is_filtered_only_at_high_confidence(app):
    a, sid = app(jev=ScriptedDecider({"spam": Likely(.95)}))
    assert run(a, sid, "pay 499 to register", source="gmail").status == "filtered"


def test_classroom_due_date_wins_without_an_llm_call(app):
    llm = ScriptedLLM({})
    a, sid = app(jev=ScriptedDecider({"subject": Picked("Operating Systems", .95)}), llm=llm)
    out = run(a, sid, "New assignment", source="classroom",
              classroom={"title": "OOAD project", "due_at": "2030-01-01T23:59"})
    assert out.route == "classroom" and llm.calls == []


# --- gateway --------------------------------------------------------------------------
def _dated_item(a, sid):
    text = "DBMS assignment due Fri"
    a.cascade.jev = ScriptedDecider({"kind": Picked("deadline", .95), "subject": Picked("Database Management Systems", .9)})
    a.cascade.llm = ScriptedLLM({text: Proposal("deadline", "Database Management Systems", "DBMS assignment", "2030-01-04T23:59")})
    return run(a, sid, text).item_id


def test_unknown_tools_are_denied(app):
    a, sid = app()
    with pytest.raises(Denied):
        a.gateway.call(sid, "delete_everything")
    with pytest.raises(Denied):
        a.gateway.call(sid, "send_email")


def test_calendar_write_needs_one_time_approval(app):
    a, sid = app()
    item = _dated_item(a, sid)
    assert a.gateway.call(sid, "add_to_calendar", {"item_id": item})["status"] == "approval_needed"
    token = a.db.pending(sid)[0]["token"]
    assert a.gateway.approve(sid, token)["status"] == "ok"
    with pytest.raises(Denied):
        a.gateway.approve(sid, token)  # replay
    assert len(a.db.calendar(sid)) == 1


def test_write_refuses_values_75_did_not_file(app):
    a, sid = app()
    with pytest.raises(Denied):
        a.gateway.call(sid, "add_to_calendar", {"item_id": 9999})


def test_approval_cannot_be_used_by_another_student(app):
    a, sid = app()
    item = _dated_item(a, sid)
    a.gateway.call(sid, "add_to_calendar", {"item_id": item})
    token = a.db.pending(sid)[0]["token"]
    with pytest.raises(Denied):
        a.gateway.approve(sid + 1, token)


# --- attendance (PortMax) ------------------------------------------------------------
def test_attendance_comes_from_portmax_worst_first(app):
    a, sid = app()
    plan = a.gateway.call(sid, "attendance")["result"]
    assert plan["connected"] and plan["subjects"][0]["subject_name"] == "Database Management Systems"
    assert plan["subjects"][0]["must_attend"] == 2  # 22/30 -> 24/32 = 75%


def test_attendance_says_not_connected_before_a_portal_refresh(app):
    a, sid = app()
    a.db.conn.execute("UPDATE students SET portal_id='nobody' WHERE id=?", (sid,))
    assert a.gateway.call(sid, "attendance")["result"] == {"connected": False, "subjects": []}
