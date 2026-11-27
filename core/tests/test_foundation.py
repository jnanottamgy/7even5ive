"""Phase 1: the database lock and migrations, the background loop, the outbox, Firebase
wake-ups, marking a card done, and reminders that follow a moved date."""

from __future__ import annotations

import base64
import json
import sqlite3
import threading
from datetime import datetime, time, timedelta

import httpx
import pytest
from fastapi.testclient import TestClient

from conftest import at, file_item
from seventy5 import clock, demo, notify
from seventy5.api import create
from seventy5.db import Database, token_hash
from seventy5.gateway import Denied
from seventy5.scheduler import Job, Scheduler, latest_slot

AUTH = {"authorization": f"Bearer {demo.TOKEN}"}


# --- database --------------------------------------------------------------------------------
def test_threads_sharing_one_connection_never_interleave_transactions(tmp_path):
    db = Database(str(tmp_path / "x.db"))
    with db.tx() as c:
        sid = int(c.execute("INSERT INTO students(name) VALUES ('A') RETURNING id").fetchone()["id"])
    errors: list[BaseException] = []

    def work() -> None:
        try:
            for _ in range(40):
                db.add_notification(sid, "reminder", "t", "b", None, "2030-01-01T00:00+05:30")
                db.notifications(sid, 0)
        except BaseException as err:  # noqa: BLE001
            errors.append(err)

    threads = [threading.Thread(target=work) for _ in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert errors == []
    assert db.latest_notification_id(sid) == 320


def test_an_old_database_gains_the_new_columns_and_keeps_its_rows(tmp_path):
    path = tmp_path / "old.db"
    raw = sqlite3.connect(path)
    raw.executescript("""
        CREATE TABLE students (id INTEGER PRIMARY KEY, name TEXT NOT NULL, wa_phone TEXT UNIQUE,
          mcp_token TEXT UNIQUE, branch TEXT, year INTEGER, interests TEXT, portal_id TEXT);
        CREATE TABLE items (id INTEGER PRIMARY KEY, student_id BIGINT NOT NULL, event_id BIGINT,
          kind TEXT NOT NULL, subject TEXT NOT NULL, title TEXT NOT NULL, due_at TEXT,
          status TEXT NOT NULL DEFAULT 'filed', route TEXT NOT NULL, source TEXT NOT NULL,
          relevance REAL, created_at TEXT NOT NULL);
        CREATE TABLE reminders (id INTEGER PRIMARY KEY, student_id BIGINT NOT NULL,
          item_id BIGINT NOT NULL REFERENCES items(id), fire_at TEXT NOT NULL,
          status TEXT NOT NULL DEFAULT 'pending', sent_at TEXT, UNIQUE(item_id, fire_at));
        CREATE TABLE notifications (id INTEGER PRIMARY KEY, student_id BIGINT NOT NULL,
          kind TEXT NOT NULL, title TEXT NOT NULL, body TEXT NOT NULL, item_id BIGINT,
          created_at TEXT NOT NULL);
        INSERT INTO students(name) VALUES ('Old');
        INSERT INTO notifications(student_id, kind, title, body, created_at)
          VALUES (1, 'reminder', 'Old title', 'Old body', 'x');
        INSERT INTO items(student_id, kind, subject, title, due_at, route, source, created_at)
          VALUES (1, 'deadline', 'X', 'T', '2030-01-04T23:59+05:30', 'bot', 'whatsapp', 'x');
        INSERT INTO reminders(student_id, item_id, fire_at) VALUES (1, 1, '2030-01-04T22:59+05:30');
    """)
    raw.close()
    db = Database(str(path))
    assert db.reminders(1)[0]["channel"] == "push"
    assert db.student(1)["call_consent_at"] is None
    old_message = db.notifications(1, 0)[0]
    assert old_message["title"] == "Old title" and old_message["reminder_id"] is None
    Database(str(path))  # a second start changes nothing


# --- the background loop ---------------------------------------------------------------------
def test_latest_slot_is_today_or_yesterdays_last():
    slots = (time(13), time(21))
    assert latest_slot(at(2030, 1, 4, 14), slots) == at(2030, 1, 4, 13)
    assert latest_slot(at(2030, 1, 4, 21), slots) == at(2030, 1, 4, 21)
    assert latest_slot(at(2030, 1, 4, 9), slots) == at(2030, 1, 3, 21)


def test_a_daily_job_runs_once_per_slot_and_catches_up_after_a_sleep(tmp_path):
    db = Database(str(tmp_path / "j.db"))
    now = [at(2030, 1, 4, 13, 5)]
    runs: list[datetime] = []
    job = Job("mail", lambda: runs.append(now[0]), at=(time(13), time(21)))
    sched = Scheduler(db, [job], now=lambda: now[0])
    assert sched.run_once(job)          # never ran: runs at once
    assert not sched.run_once(job)      # same slot: no
    now[0] = at(2030, 1, 4, 20, 59)
    assert not sched.run_once(job)
    now[0] = at(2030, 1, 5, 8)          # slept through 21:00: catches up once
    assert sched.run_once(job) and not sched.run_once(job)
    assert len(runs) == 2
    # a restart (new scheduler, same database) remembers
    assert not Scheduler(db, [job], now=lambda: now[0]).run_once(job)


def test_a_failing_job_is_recorded_and_never_stops_the_loop(tmp_path):
    db = Database(str(tmp_path / "j.db"))

    def boom() -> None:
        raise RuntimeError("secret text from a mail")

    job = Job("boom", boom, every=timedelta(seconds=30))
    sched = Scheduler(db, [job], now=lambda: at(2030, 1, 1))
    assert sched.run_once(job) is True
    assert not sched.run_once(job)  # interval not elapsed
    daily = Job("daily-boom", boom, at=(time(9),))
    Scheduler(db, [daily], now=lambda: at(2030, 1, 1, 10)).run_once(daily)
    assert db.job("daily-boom")["last_error"] == "RuntimeError"  # the type, never the text


def test_jobs_must_name_exactly_one_schedule():
    with pytest.raises(ValueError):
        Job("x", lambda: None)
    with pytest.raises(ValueError):
        Job("x", lambda: None, every=timedelta(seconds=1), at=(time(1),))


def test_the_served_api_starts_and_stops_its_background_loop(make_app):
    a, _ = make_app()
    with TestClient(create(a, run_jobs=True)) as client:
        assert client.get("/api/health").status_code == 200


# --- the outbox ------------------------------------------------------------------------------
def test_a_reminder_lands_in_the_outbox_and_the_phone_pulls_it(make_app):
    a, sid = make_app()
    woke: list[int] = []
    a.sender = notify.OutboxSender(a.db, wake=woke.append)
    item = file_item(a, sid)
    reminder = a.gateway.call(sid, "set_reminder", {"item_id": item, "before_minutes": 60})
    client = TestClient(create(a))
    first = client.get("/api/notifications?after=-1", headers=AUTH).json()
    assert first == {"notifications": [], "latest_id": 0}
    clock.freeze(at(2030, 1, 4, 23, 0))
    assert notify.fire_due(a.db, a.sender) == 1
    got = client.get("/api/notifications?after=0", headers=AUTH).json()
    assert [n["title"] for n in got["notifications"]] == [
        "Database Management Systems: DBMS assignment due Fri"]
    assert got["notifications"][0]["body"] == "Due Fri 4 Jan, 11:59 PM"
    # Which reminder fired: the phone's own alarm for it may have shown it already.
    assert got["notifications"][0]["reminder_id"] == reminder["result"]["reminder_id"]
    assert got["notifications"][0]["item_id"] == item
    assert got["latest_id"] == got["notifications"][0]["id"] and woke == [sid]
    assert client.get(f"/api/notifications?after={got['latest_id']}",
                      headers=AUTH).json()["notifications"] == []


def test_one_students_outbox_is_invisible_to_another(make_app):
    a, sid = make_app()
    with a.db.tx() as c:
        other = int(c.execute("INSERT INTO students(name, token_hash) VALUES ('B', ?)"
                              " RETURNING id", (token_hash("tok-b"),)).fetchone()["id"])
    a.db.add_notification(sid, "reminder", "mine", "x", None, "2030-01-01T00:00+05:30")
    client = TestClient(create(a))
    theirs = client.get("/api/notifications", headers={"authorization": "Bearer tok-b"}).json()
    assert theirs["notifications"] == [] and theirs["latest_id"] == 0 and other != sid


def test_a_failed_wake_up_never_loses_the_message(make_app):
    a, sid = make_app()

    def broken(_: int) -> None:
        raise httpx.ConnectError("down")

    notify.OutboxSender(a.db, wake=broken).send(sid, "t", "b")
    assert len(a.db.notifications(sid, 0)) == 1


def test_phones_register_and_unregister_for_wake_ups(make_app):
    a, sid = make_app()
    client = TestClient(create(a))
    assert client.post("/api/devices", json={"token": "fcm-1"}, headers=AUTH).json() == {"ok": True}
    assert client.post("/api/devices", json={"token": ""}, headers=AUTH).status_code == 400
    assert a.db.device_tokens(sid) == ["fcm-1"]
    assert client.post("/api/devices/remove", json={"token": "fcm-1"}, headers=AUTH).json() == {
        "removed": True}
    assert a.db.device_tokens(sid) == []
    assert client.post("/api/devices", json={"token": "x"}).status_code == 401


# --- Firebase wake-ups -----------------------------------------------------------------------
def _account():
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric import rsa

    from seventy5.fcm import ServiceAccount

    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    pem = key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
                            serialization.NoEncryption()).decode()
    return key, ServiceAccount("proj-75", "push@proj-75.iam.gserviceaccount.com", pem, "kid1")


def test_the_firebase_assertion_is_a_valid_rs256_jwt():
    from cryptography.hazmat.primitives import hashes
    from cryptography.hazmat.primitives.asymmetric import padding

    from seventy5.fcm import SCOPE, signed_assertion

    key, account = _account()
    token = signed_assertion(account, 1_900_000_000)
    head, body, sig = token.split(".")
    pad = lambda s: s + "=" * (-len(s) % 4)  # noqa: E731
    claims = json.loads(base64.urlsafe_b64decode(pad(body)))
    assert claims == {"iss": account.client_email, "scope": SCOPE,
                      "aud": "https://oauth2.googleapis.com/token",
                      "iat": 1_900_000_000, "exp": 1_900_003_600}
    assert json.loads(base64.urlsafe_b64decode(pad(head)))["alg"] == "RS256"
    key.public_key().verify(base64.urlsafe_b64decode(pad(sig)), f"{head}.{body}".encode(),
                            padding.PKCS1v15(), hashes.SHA256())


def test_a_wake_up_carries_no_content_and_drops_dead_tokens(make_app):
    from seventy5.fcm import FcmWaker

    a, sid = make_app()
    _, account = _account()
    a.db.add_device("live", sid, "android", "x")
    a.db.add_device("gone", sid, "android", "x")
    sent: list[dict] = []

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.host == "oauth2.googleapis.com":
            assert b"jwt-bearer" in request.content
            return httpx.Response(200, json={"access_token": "at", "expires_in": 3600})
        body = json.loads(request.content)
        sent.append(body)
        assert request.headers["authorization"] == "Bearer at"
        if body["message"]["token"] == "gone":
            return httpx.Response(404, json={"error": {"status": "NOT_FOUND", "details": [
                {"@type": "type.googleapis.com/google.firebase.fcm.v1.FcmError",
                 "errorCode": "UNREGISTERED"}]}})
        return httpx.Response(200, json={"name": "projects/proj-75/messages/1"})

    waker = FcmWaker(a.db, account, http=httpx.Client(transport=httpx.MockTransport(handler)),
                     background=False)
    waker(sid)
    assert [m["message"]["data"] for m in sent] == [{"type": "sync"}, {"type": "sync"}]
    assert all("notification" not in m["message"] for m in sent)
    assert a.db.device_tokens(sid) == ["live"]


# --- done, undo, and what reminders do about it ----------------------------------------------
def test_marking_done_takes_it_off_the_list_and_skips_its_reminder(make_app):
    a, sid = make_app()
    item = file_item(a, sid, due="2030-01-04T23:59")
    a.gateway.call(sid, "set_reminder", {"item_id": item, "before_minutes": 60})
    clock.freeze(at(2030, 1, 1, 9))
    assert [d["id"] for d in a.gateway.call(sid, "due_this_week")["result"]] == [item]
    assert a.gateway.call(sid, "mark_done", {"item_id": item})["result"]["status"] == "done"
    assert a.gateway.call(sid, "due_this_week")["result"] == []
    with pytest.raises(Denied):
        a.gateway.call(sid, "mark_done", {"item_id": item})  # a double tap changes nothing
    clock.freeze(at(2030, 1, 4, 23, 0))
    sender = notify.LogSender()
    assert notify.fire_due(a.db, sender) == 0 and sender.sent == []
    assert a.db.conn.execute("SELECT status FROM reminders").fetchone()["status"] == "skipped"


def test_reopen_undoes_mark_done(make_app):
    a, sid = make_app()
    item = file_item(a, sid)
    clock.freeze(at(2030, 1, 1, 9))
    a.gateway.call(sid, "mark_done", {"item_id": item})
    assert a.gateway.call(sid, "reopen", {"item_id": item})["result"]["status"] == "filed"
    assert [d["id"] for d in a.gateway.call(sid, "due_this_week")["result"]] == [item]
    with pytest.raises(Denied):
        a.gateway.call(sid, "reopen", {"item_id": item})


def test_another_students_card_cannot_be_marked_done(make_app):
    a, sid = make_app()
    item = file_item(a, sid)
    with pytest.raises(Denied):
        a.gateway.call(sid + 1, "mark_done", {"item_id": item})


def test_a_reminder_found_after_its_deadline_passed_is_skipped_not_sent(make_app):
    a, sid = make_app()
    item = file_item(a, sid, due="2030-01-04T23:59")
    a.gateway.call(sid, "set_reminder", {"item_id": item, "before_minutes": 60})
    clock.freeze(at(2030, 1, 5, 8))  # the service slept through it
    sender = notify.LogSender()
    assert notify.fire_due(a.db, sender) == 0 and sender.sent == []


def test_a_cancelled_reminder_can_be_set_again(make_app):
    a, sid = make_app()
    item = file_item(a, sid)
    rid = a.gateway.call(sid, "set_reminder", {"item_id": item})["result"]["reminder_id"]
    a.gateway.call(sid, "cancel_reminder", {"reminder_id": rid})
    again = a.gateway.call(sid, "set_reminder", {"item_id": item})["result"]["reminder_id"]
    assert again == rid and [r["reminder_id"] for r in notify.list_reminders(a.db, sid)] == [rid]


def test_a_moved_deadline_moves_its_reminders(make_app):
    a, sid = make_app()
    item = file_item(a, sid, due="2030-01-04T23:59")
    a.gateway.call(sid, "set_reminder", {"item_id": item, "before_minutes": 24 * 60})
    a.gateway.call(sid, "set_reminder", {"item_id": item, "before_minutes": 60})
    clock.freeze(at(2030, 1, 1, 9))
    a.db.move_item_due(sid, item, "2030-01-06T17:00+05:30", clock.iso(clock.now()))
    fires = sorted(r["fire_at"] for r in a.db.reminders(sid))
    assert fires == ["2030-01-05T17:00+05:30", "2030-01-06T16:00+05:30"]


def test_a_deadline_moved_earlier_fires_an_overdue_reminder_at_once_and_only_once(make_app):
    a, sid = make_app()
    item = file_item(a, sid, due="2030-01-04T23:59")
    a.gateway.call(sid, "set_reminder", {"item_id": item, "before_minutes": 24 * 60})
    a.gateway.call(sid, "set_reminder", {"item_id": item, "before_minutes": 48 * 60})
    clock.freeze(at(2030, 1, 3, 12))
    a.db.move_item_due(sid, item, "2030-01-03T18:00+05:30", clock.iso(clock.now()))
    rows = a.db.conn.execute("SELECT status, fire_at FROM reminders ORDER BY id").fetchall()
    assert sorted(r["status"] for r in rows) == ["pending", "skipped"]
    assert [r["fire_at"] for r in rows if r["status"] == "pending"] == ["2030-01-03T12:00+05:30"]


def test_a_deadline_that_moved_into_the_past_skips_its_reminders(make_app):
    a, sid = make_app()
    item = file_item(a, sid, due="2030-01-04T23:59")
    a.gateway.call(sid, "set_reminder", {"item_id": item})
    clock.freeze(at(2030, 1, 3, 12))
    a.db.move_item_due(sid, item, "2030-01-03T09:00+05:30", clock.iso(clock.now()))
    assert a.db.reminders(sid) == []
