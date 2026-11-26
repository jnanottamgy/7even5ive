"""The rules that must hold whatever the model says.

Why these: they are the claims the deck makes (signed events, dedupe, Jev drops only at
high confidence, the LLM is gated, deny by default, one-time approvals, exact attendance).
"""

from __future__ import annotations

import json
import os
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

    # PG_TEST_URL=postgresql://... runs every test against Postgres (Supabase's engine).
    url = os.environ.get("PG_TEST_URL") or str(tmp_path / "t.db")
    if url.startswith("postgres"):
        import psycopg
        with psycopg.connect(url, autocommit=True) as c:
            c.execute("DROP TABLE IF EXISTS audit, reminders, calendar, pending_approvals,"
                      " used_approvals, items, events, subjects, students CASCADE")

    def make(jev=None, llm=None):
        a = build(url, jev=jev or ScriptedDecider({}), llm=llm or ScriptedLLM({}))
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
    assert ok.status_code == 200 and len(a.db.conn.execute("SELECT id FROM events").fetchall()) == 0


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


# --- reminders ------------------------------------------------------------------------
def test_reminder_is_noted_then_fired_exactly_once(app):
    from datetime import datetime

    from seventy5 import clock, notify

    a, sid = app()
    item = _dated_item(a, sid)  # due 2030-01-04 23:59
    r = a.gateway.call(sid, "set_reminder", {"item_id": item, "before_minutes": 60})["result"]
    again = a.gateway.call(sid, "set_reminder", {"item_id": item, "before_minutes": 60})["result"]
    assert r["reminder_id"] == again["reminder_id"]  # asked twice, stored once
    sender = notify.LogSender()
    try:
        clock.freeze(datetime(2030, 1, 4, 22, 0, tzinfo=clock.IST))
        assert notify.fire_due(a.db, sender) == 0
        clock.freeze(datetime(2030, 1, 4, 23, 0, tzinfo=clock.IST))
        assert notify.fire_due(a.db, sender) == 1
        assert notify.fire_due(a.db, sender) == 0  # never twice
    finally:
        clock.freeze(None)
    assert sender.sent[0]["title"] == "Database Management Systems: DBMS assignment"


def test_reminder_needs_a_filed_dated_item(app):
    a, sid = app()
    with pytest.raises(Denied):
        a.gateway.call(sid, "set_reminder", {"item_id": 9999})


def test_cancelled_reminder_never_fires(app):
    from datetime import datetime

    from seventy5 import clock, notify

    a, sid = app()
    item = _dated_item(a, sid)
    rid = a.gateway.call(sid, "set_reminder", {"item_id": item})["result"]["reminder_id"]
    assert a.gateway.call(sid, "cancel_reminder", {"reminder_id": rid})["result"]["cancelled"]
    try:
        clock.freeze(datetime(2030, 1, 4, 23, 0, tzinfo=clock.IST))
        assert notify.fire_due(a.db, notify.LogSender()) == 0
    finally:
        clock.freeze(None)


# --- the phone's API ---------------------------------------------------------------------
AUTH = {"authorization": f"Bearer {demo.TOKEN}"}


def test_phone_sets_lists_and_cancels_a_reminder_through_the_gateway(app):
    a, sid = app()
    item = _dated_item(a, sid)
    client = TestClient(create(a))
    r = client.post("/api/tools/set_reminder", json={"args": {"item_id": item, "before_minutes": 60}},
                    headers=AUTH)
    assert r.status_code == 200 and r.json()["status"] == "ok"
    rid = r.json()["result"]["reminder_id"]
    listed = client.post("/api/tools/list_reminders", headers=AUTH).json()["result"]
    assert [x["reminder_id"] for x in listed] == [rid]
    assert [x["reminder_id"] for x in client.get("/api/cards", headers=AUTH).json()["reminders"]] == [rid]
    out = client.post("/api/tools/cancel_reminder", json={"args": {"reminder_id": rid}}, headers=AUTH)
    assert out.json()["result"]["cancelled"]
    assert client.get("/api/cards", headers=AUTH).json()["reminders"] == []


def test_health_names_the_service_and_nothing_else(app):
    a, _ = app()
    body = TestClient(create(a)).get("/api/health").json()
    assert body == {"service": "7even5ive", "version": 1}


def test_phone_tools_keep_the_gateway_rules(app):
    a, sid = app()
    client = TestClient(create(a))
    assert client.post("/api/tools/due_this_week").status_code == 401
    denied = client.post("/api/tools/send_email", json={"args": {"to": "x"}}, headers=AUTH)
    assert denied.status_code == 403 and denied.json()["detail"] == "send_email is not allowed"
    bad = client.post("/api/tools/set_reminder", json={"args": {"item_id": 9999}}, headers=AUTH)
    assert bad.status_code == 403
    assert client.post("/api/tools/due_this_week", json={"args": []}, headers=AUTH).status_code == 400


def test_calendar_from_the_phone_waits_for_a_tap_and_approves_once(app):
    a, sid = app()
    item = _dated_item(a, sid)
    client = TestClient(create(a))
    out = client.post("/api/tools/add_to_calendar", json={"args": {"item_id": item}}, headers=AUTH)
    assert out.json()["status"] == "approval_needed"
    token = client.get("/api/cards", headers=AUTH).json()["approvals"][0]["token"]
    assert client.post("/api/approve", json={"token": token}, headers=AUTH).status_code == 200
    again = client.post("/api/approve", json={"token": token}, headers=AUTH)
    assert again.status_code == 403 and again.json()["detail"] == "approval already used"


def test_expired_approvals_leave_the_phone(app, monkeypatch):
    from types import SimpleNamespace

    from seventy5 import gateway

    a, sid = app()
    item = _dated_item(a, sid)
    client = TestClient(create(a))
    client.post("/api/tools/add_to_calendar", json={"args": {"item_id": item}}, headers=AUTH)
    token = client.get("/api/cards", headers=AUTH).json()["approvals"][0]["token"]
    later = time.time() + 16 * 60
    monkeypatch.setattr(gateway, "time", SimpleNamespace(time=lambda: later))
    assert client.get("/api/cards", headers=AUTH).json()["approvals"] == []
    refused = client.post("/api/approve", json={"token": token}, headers=AUTH)
    assert refused.status_code == 403 and refused.json()["detail"] == "approval expired"


# --- Lambda handlers --------------------------------------------------------------------
def test_cascade_handler_reports_only_the_failed_record(app, monkeypatch):
    from seventy5 import aws

    a, sid = app(jev=ScriptedDecider({"kind": Picked("chitchat", .99)}))
    good = a.db.insert_event(sid, "whatsapp:w1", "whatsapp", {"text": "ok"}, "2030-01-01T00:00+05:30")
    monkeypatch.setattr(aws, "_app", a)
    out = aws.cascade_handler({"Records": [{"messageId": "m1", "body": str(good)},
                                           {"messageId": "m2", "body": "999999"}]}, None)
    assert out == {"batchItemFailures": [{"itemIdentifier": "m2"}]}
    # SQS redelivers at least once: a done event is skipped, never filed twice
    assert aws.cascade_handler({"Records": [{"messageId": "m1", "body": str(good)}]}, None) == {
        "batchItemFailures": []}


def test_http_handler_serves_the_api_through_api_gateway(app, monkeypatch):
    from seventy5 import aws

    a, _ = app()
    monkeypatch.setattr(aws, "_app", a)
    monkeypatch.setattr(aws, "_http", None)
    event = {"version": "2.0", "routeKey": "$default", "rawPath": "/api/cards", "rawQueryString": "",
             "headers": {"authorization": f"Bearer {demo.TOKEN}"},
             "requestContext": {"http": {"method": "GET", "path": "/api/cards", "sourceIp": "1.1.1.1",
                                         "protocol": "HTTP/1.1", "userAgent": "t"}, "stage": "$default"},
             "isBase64Encoded": False}
    resp = aws.http_handler(event, None)
    assert resp["statusCode"] == 200 and "due_this_week" in resp["body"]


# --- the bot's own decision ---------------------------------------------------------------
def test_bot_decision_is_filed_without_any_model_call(app):
    jev, llm = ScriptedDecider({}), ScriptedLLM({})
    a, sid = app(jev=jev, llm=llm)
    out = run(a, sid, "DBMS assignment due Fri", decision={
        "kind": "deadline", "subject": "Database Management Systems",
        "title": "DBMS assignment", "due_at": "2030-01-04T23:59+05:30"})
    assert (out.route, out.status) == ("bot", "filed")
    assert jev.calls == [] and llm.calls == []


def test_bot_decision_with_an_unknown_subject_goes_to_the_cascade(app):
    text = "physics notes"
    llm = ScriptedLLM({text: Proposal("material", "Miscellaneous", "Physics notes", None)})
    a, sid = app(llm=llm)
    out = run(a, sid, text, decision={"kind": "material", "subject": "Physics"})
    assert out.route == "llm" and len(llm.calls) == 1


def test_webhook_passes_the_bot_decision_through(app):
    a, sid = app(jev=ScriptedDecider({}), llm=ScriptedLLM({}))
    client = TestClient(create(a))
    body = json.dumps({"from": demo.PHONE, "message_id": "m-bot", "text": "unit 3 notes",
                       "attachment": "DBMS_U3.pdf",
                       "decision": {"kind": "material", "subject": "Database Management Systems"}}).encode()
    ts = int(time.time())
    client.post("/bot/webhook", content=body, headers={"x-75-timestamp": str(ts), "x-75-signature": sign(body, ts)})
    assert a.last[0].route == "bot"
    assert a.db.items(sid, kinds=("material",))[0]["title"] == "DBMS_U3.pdf"


# --- the online service ------------------------------------------------------------------
def test_the_online_service_knows_the_address_the_phone_used():
    from seventy5.cloud import origin_of

    def scope(**headers):
        return {"scheme": "http", "headers": [(k.encode(), v.encode()) for k, v in headers.items()]}

    assert origin_of(scope(host="13.233.1.2")) == "http://13.233.1.2"
    # CloudFront talks plain HTTP to the server but the phone used HTTPS: its header says so.
    assert origin_of(scope(**{"host": "d1x.cloudfront.net", "cloudfront-forwarded-proto": "https"})) \
        == "https://d1x.cloudfront.net"
    assert origin_of(scope(**{"host": "x.onrender.com", "x-forwarded-proto": "https"})) \
        == "https://x.onrender.com"
    assert origin_of(scope(**{"host": "d1x.cloudfront.net", "x-amz-cf-id": "abc"})) \
        == "https://d1x.cloudfront.net"
    assert origin_of(scope()) is None


def test_the_demo_tour_goes_through_the_real_webhook_and_resets(tmp_path, monkeypatch):
    import dataclasses

    from portmax.store import Store
    from seventy5 import cloud, config

    monkeypatch.setattr(tools, "_portal", Store(f"sqlite:///{tmp_path.as_posix()}/pm.db"))
    monkeypatch.setattr(config, "settings", dataclasses.replace(
        config.settings, portmax_database_url=f"sqlite:///{tmp_path.as_posix()}/pm-api.db"))
    client = TestClient(cloud.build_router(str(tmp_path / "75.db")))
    auth = {"authorization": f"Bearer {demo.TOKEN}"}

    assert client.post("/demo/forward/quiz").status_code == 401  # only the demo student
    quiz = client.post("/demo/forward/quiz", headers=auth).json()
    assert quiz["webhook_status"] == 200
    assert quiz["filed"]["title"] == cloud.QUIZ_TITLE and quiz["filed"]["route"] == "bot"
    due = client.get("/api/cards", headers=auth).json()["due_this_week"]
    assert any(c["title"] == cloud.QUIZ_TITLE for c in due)

    notes = client.post("/demo/forward/notes", headers=auth).json()
    assert notes["filed"]["subject"] == "Operating Systems"
    stranger = client.post("/demo/forward/stranger", headers=auth).json()
    assert stranger["webhook_status"] == 200 and stranger["filed"] is None  # dropped, no row
    assert client.post("/demo/forward/forged", headers=auth).json()["webhook_status"] == 401
    assert client.post("/demo/forward/nope", headers=auth).status_code == 404

    assert client.post("/demo/reset", headers=auth).json()["ok"]
    due = client.get("/api/cards", headers=auth).json()["due_this_week"]
    assert len(due) == 4 and not any(c["title"] == cloud.QUIZ_TITLE for c in due)


# --- portal data, files, share, ask ---------------------------------------------------------


def _client(a):
    return TestClient(create(a)), {"Authorization": f"Bearer {demo.TOKEN}"}


def test_cards_carry_timetable_marks_and_results_from_portmax(app):
    a, sid = app()
    client, auth = _client(a)
    cards = client.get("/api/cards", headers=auth).json()
    assert cards["timetable"]["connected"] and cards["timetable"]["data"][0]["day"] == "Mon"
    assert cards["marks"]["data"][0]["component"] == "CIE-1"
    assert cards["results"]["data"]["semesters"][-1]["cgpa"] == 8.58
    assert a.gateway.call(sid, "marks")["status"] == "ok"


def test_demo_files_are_real_pdf_and_docx():
    import base64
    import io
    import zipfile

    from seventy5 import files

    pdf = base64.b64decode(files.demo_file_b64("OS_Unit4_Deadlocks.pdf"))
    assert pdf.startswith(b"%PDF-1.4") and pdf.rstrip().endswith(b"%%EOF")
    docx = base64.b64decode(files.demo_file_b64("DCN_Lab_Manual.docx"))
    assert "word/document.xml" in zipfile.ZipFile(io.BytesIO(docx)).namelist()
    assert files.demo_file_b64("nope.pdf") is None


def _webhook(client, body):
    raw = json.dumps(body).encode()
    ts = int(time.time())
    return client.post("/bot/webhook", content=raw,
                       headers={"x-75-timestamp": str(ts), "x-75-signature": sign(raw, ts)})


def test_a_forwarded_file_opens_from_the_phone_and_only_for_its_student(app):
    import base64

    from seventy5 import files

    a, sid = app()
    client, auth = _client(a)
    b64 = files.demo_file_b64("OS_Unit4_Deadlocks.pdf")
    _webhook(client, {"from": demo.PHONE, "message_id": "wamid.f1", "text": "OS notes",
                      "attachment": "OS_Unit4_Deadlocks.pdf", "file": b64,
                      "decision": {"kind": "material", "subject": "Operating Systems"}})
    _webhook(client, {"from": demo.PHONE, "message_id": "wamid.f2", "text": "bad file",
                      "attachment": "bad.pdf", "file": "%%%not base64",
                      "decision": {"kind": "material", "subject": "Operating Systems"}})
    a.work()
    mats = {m["title"]: m for m in tools.materials(a.db, sid)}
    assert mats["OS_Unit4_Deadlocks.pdf"]["has_file"] and not mats["bad.pdf"]["has_file"]
    r = client.get(f"/api/files/{mats['OS_Unit4_Deadlocks.pdf']['id']}", headers=auth)
    assert r.status_code == 200 and r.headers["content-type"] == "application/pdf"
    assert r.content == base64.b64decode(b64)
    assert client.get(f"/api/files/{mats['bad.pdf']['id']}", headers=auth).status_code == 404
    assert client.get(f"/api/files/{mats['OS_Unit4_Deadlocks.pdf']['id']}").status_code == 401


def test_shared_with_a_kind_is_filed_as_the_student_said(app):
    import base64

    a, sid = app()
    client, auth = _client(a)
    pdf = base64.b64encode(b"%PDF-1.4 tiny").decode()
    r = client.post("/api/share", headers=auth, json={
        "text": "PnS formula sheet", "file_name": "PnS_formulas.pdf", "file_b64": pdf,
        "kind": "material", "subject": "Probability and Statistics"}).json()
    assert r["status"] == "filed" and r["item"]["route"] == "you"
    assert r["item"]["title"] == "PnS_formulas.pdf"
    assert client.get(f"/api/files/{r['item']['id']}", headers=auth).content == b"%PDF-1.4 tiny"

    # A dated kind needs a date: no date fails the check, so the cascade decides (here: review).
    r = client.post("/api/share", headers=auth, json={
        "text": "lab record submission", "kind": "deadline",
        "subject": "Operating Systems"}).json()
    assert r["status"] == "needs_review"
    r = client.post("/api/share", headers=auth, json={
        "text": "lab record submission", "kind": "deadline", "subject": "Operating Systems",
        "title": "OS lab record", "due_at": demo._at(2, 17)}).json()
    assert r["status"] == "filed" and r["item"]["due_at"]
    assert client.post("/api/share", headers=auth, json={}).status_code == 400
    assert client.post("/api/share", json={"text": "x"}).status_code == 401


def test_offline_ask_answers_from_gateway_tools_and_says_so(app):
    a, sid = app()
    client, auth = _client(a)

    def ask(q):
        r = client.post("/api/ask", headers=auth, json={"question": q})
        assert r.status_code == 200
        return r.json()

    day = demo.clock.now().weekday()
    skip = ask("can I skip " + ["monday", "tuesday", "wednesday", "thursday", "friday",
                                "saturday", "sunday"][0])
    assert skip["route"] == "offline" and "Skipping Monday" in skip["answer"]
    assert {"attendance", "timetable"} <= set(skip["tools"])
    assert "Database Management Systems" in ask("how is my dbms attendance")["answer"]
    assert "CGPA 8.58" in ask("what's my cgpa")["answer"]
    assert "CIE-1" in ask("show my CIE marks for DBMS")["answer"]
    assert "Nothing due" in ask("what's due this week?")["answer"]
    client.post("/api/share", headers=auth, json={
        "text": "DBMS Assignment 3", "kind": "deadline", "subject": "Database Management Systems",
        "title": "DBMS Assignment 3", "due_at": demo._at(2, 23, 59)})
    assert "DBMS Assignment 3" in ask("what's due this week?")["answer"]
    assert "offline" in ask("tell me a joke")["answer"]
    assert day in range(7)
    # Every fact came through the gateway, so the audit shows the calls (tool names only).
    assert any(r["tool"] == "timetable" for r in a.db.audit_log(sid))
    assert client.post("/api/ask", headers=auth, json={"question": ""}).status_code == 400


def test_claude_ask_runs_tools_through_the_gateway(app, monkeypatch):
    from types import SimpleNamespace as NS

    from seventy5 import ask as ask_mod

    a, sid = app()
    item_id = _dated_item(a, sid)
    replies = [
        NS(content=[NS(type="tool_use", id="t1", name="add_to_calendar",
                       input={"item_id": item_id})]),
        NS(content=[NS(type="tool_use", id="t2", name="send_email", input={"to": "x"})]),
        NS(content=[NS(type="text", text="Done: it's waiting for your tap.")]),
    ]
    seen = []

    class Messages:
        def create(self, **kw):
            seen.append(kw["messages"][-1])
            return replies.pop(0)

    monkeypatch.setattr(ask_mod, "_client", lambda: (NS(messages=Messages()), "m"))
    import dataclasses
    monkeypatch.setattr(ask_mod, "settings", dataclasses.replace(ask_mod.settings, anthropic_api_key="k"))
    out = ask_mod.answer(a.gateway, sid, "put the assignment in my calendar")
    assert out == {"answer": "Done: it's waiting for your tap.", "route": "claude",
                   "tools": ["add_to_calendar", "send_email"]}
    assert len(a.db.pending(sid)) == 1  # the write waits for the student, as for any MCP client
    assert "denied" in seen[-1]["content"][0]["content"]
