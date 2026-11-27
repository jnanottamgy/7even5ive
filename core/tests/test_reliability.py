"""Reliability before real students use it: every mailbox and every Classroom reached after each
1 PM and 9 PM, a Claude timeout tried again in the same slot, one card per mail card even with
two instances, Classroom work the cascade could not file filed by a later sync, a dead Google
grant shown and announced once, and events a killed Lambda left queued run again."""

from __future__ import annotations

import threading
import time
from dataclasses import replace
from datetime import timedelta

import pytest
from fastapi.testclient import TestClient

from conftest import at, file_item
from test_mail_google import ALL_SCOPES, AUTH, STUDENT_TOKEN, FakeGoogle, _connect, mail_items
from seventy5 import clock, google, lambda_demo, mail, mail_demo, tools
from seventy5.api import create
from seventy5.db import INTEGRITY, Database, token_hash
from seventy5.jev import Picked, ScriptedDecider
from seventy5.llm import Proposal, ScriptedLLM
from seventy5.scheduler import Scheduler

NOW = at(2030, 1, 7, 10, 0)  # a Monday morning
SLOT = at(2030, 1, 7, 13, 0)  # that day's 1 PM check
WORK = {"id": "w1", "title": "Mini project", "dueDate": {"year": 2030, "month": 1, "day": 10},
        "dueTime": {"hours": 18, "minutes": 29}}  # 11:59 PM India time
WORK_DUE = "2030-01-10T23:59+05:30"
SURE = {"kind": Picked("deadline", .95), "subject": Picked("Operating Systems", .95)}


@pytest.fixture
def make_app(make_app):
    """The seeded student with a token of its own: an ordinary student who may connect Google."""
    def make(*args, **kwargs):
        a, sid = make_app(*args, **kwargs)
        a.db.update_student(sid, token_hash=token_hash(STUDENT_TOKEN))
        return a, sid

    return make


@pytest.fixture
def fake(monkeypatch):
    configured = replace(google.settings, google_client_id="cid.apps.googleusercontent.com",
                         google_client_secret="secret", token_encryption_key="", public_url="")
    monkeypatch.setattr(google, "settings", configured)
    g = FakeGoogle()
    monkeypatch.setattr(google, "_http", g.client)
    return g


@pytest.fixture
def spent(monkeypatch):
    """Simulated work: seconds added to time.monotonic, which every deadline in a tick reads."""
    extra = [0.0]
    real = time.monotonic
    monkeypatch.setattr(time, "monotonic", lambda: real() + extra[0])
    return extra


def tick(a, scheduler):
    """One turn of Lambda's once-a-minute loop: every due job, sharing one 22-second budget."""
    a.deadline = time.monotonic() + lambda_demo.TICK_BUDGET_SECONDS
    try:
        return [job.name for job in scheduler.jobs if scheduler.run_once(job)]
    finally:
        a.deadline = None


def drive(a, scheduler, start, minutes):
    for minute in range(minutes + 1):
        clock.freeze(start + timedelta(minutes=minute))
        tick(a, scheduler)


def classroom_cards(a, sid):
    return a.db.conn.execute("SELECT * FROM items WHERE student_id=? AND source='classroom'",
                             (sid,)).fetchall()


# --- 1. after each 1 PM and 9 PM, every mailbox and every Classroom -------------------------------
def test_every_mailbox_and_classroom_is_reached_within_half_an_hour_of_the_slot(
        make_app, fake, spent, monkeypatch):
    from mailfilter.fake import FakeMailbox
    from mailfilter.judge import ScriptedJudge

    a, seeded = make_app()
    a.db.update_student(seeded, auth_user_id="someone-else")  # no mailbox in this test
    before = at(2030, 1, 6, 21, 0)  # the previous slot: every mailbox checked completely
    clock.freeze(before)
    sids = [a.db.create_student(name=f"Student {n}", auth_user_id=f"user-{n}",
                                username=f"student{n}") for n in range(8)]
    for sid in sids:
        a.db.save_google(sid, f"s{sid}@college.edu", ALL_SCOPES, google.seal("1//refresh"),
                         clock.iso(before))
    # Since then each got one placement mail, and Claude takes 3 seconds to read it.
    nimbus = mail_demo.first_batch(SLOT)[0]
    boxes = {sid: FakeMailbox([nimbus.mail], address=f"s{sid}@college.edu", now=clock.now)
             for sid in sids}
    monkeypatch.setattr(google, "gmail_mailbox", lambda db, sid: boxes[sid])
    scripted = ScriptedJudge({nimbus.marker: nimbus.answer})

    class SlowClaude:
        name = "claude"

        def judge(self, rendered):
            spent[0] += 3
            return scripted.judge(rendered)

    monkeypatch.setattr(mail, "live_judge", SlowClaude)
    for sid in sids:
        assert mail.check(a.db, sid)["judged"] == 0  # nothing had arrived yet at 9 PM
    a.db.job_ran("mail", before.isoformat(timespec="seconds"), None)
    # Classroom has one assignment for each of them, and every call to Google takes 2 seconds.
    fake.works = [dict(WORK)]
    answer = fake.handle

    def slow_google(request):
        spent[0] += 2
        return answer(request)

    fake.handle = slow_google
    a.cascade.jev = ScriptedDecider(SURE)

    # 1 PM: Lambda's tick once a minute, each with 22 seconds, for half an hour.
    drive(a, Scheduler(a.db, a.jobs()), SLOT, 30)

    def checked(sid):
        return [r for r in mail.store().runs(mail.mailbox_key(sid, "gmail"))
                if r.started_at >= SLOT and not r.more and r.error is None]

    def due(sid):
        return {c["title"]: c["due_at"] for c in tools.due_this_week(a.db, sid)}

    assert [sid for sid in sids if not checked(sid)] == [], "mail never checked after 1 PM"
    assert [sid for sid in sids if "Nimbus Systems Campus Drive" not in due(sid)] == []
    assert [sid for sid in sids if due(sid).get("Mini project") != WORK_DUE] == [], \
        "Classroom never read after 1 PM"


def test_a_busy_classroom_is_tried_again_soon_and_a_refusing_one_at_the_next_slot(make_app, fake):
    import httpx

    a, sid = make_app()
    _connect(TestClient(create(a)))
    fake.works = [dict(WORK)]
    a.cascade.jev = ScriptedDecider(SURE)
    course_list = f"{google.CLASSROOM}/courses?"
    answer, status = fake.handle, {"now": 503}

    def handle(request):
        response = answer(request)
        if str(request.url).startswith(course_list) and status["now"] != 200:
            return httpx.Response(status["now"], json={})
        return response

    fake.handle = handle
    scheduler = Scheduler(a.db, a.jobs())
    drive(a, scheduler, SLOT, 15)  # Google is busy: asked at 1 PM, and again ten minutes later
    assert len(fake.sent(course_list)) == 2
    status["now"] = 403  # the college's admin turned Classroom off for apps
    drive(a, scheduler, SLOT + timedelta(minutes=16), 60)
    assert len(fake.sent(course_list)) == 3  # refused: not asked again until the next slot
    status["now"] = 200
    drive(a, scheduler, at(2030, 1, 7, 21, 0), 2)
    assert len(fake.sent(course_list)) == 4
    assert [c["status"] for c in classroom_cards(a, sid)] == ["filed"]


# --- 2. Claude timing out is tried again in the same slot ---------------------------------------
def _claude_error(kind):
    import anthropic
    import httpx

    request = httpx.Request("POST", "https://bedrock")
    if kind == "timeout":  # no answer within mail.JUDGE_TIMEOUT
        return anthropic.APITimeoutError(request=request)
    status, error = {"rate limit": (429, anthropic.RateLimitError),
                     "5xx": (500, anthropic.InternalServerError),
                     "overload": (529, anthropic.OverloadedError)}[kind]
    response = httpx.Response(status, request=request, json={"type": "error", "error": {}})
    return error("unavailable", response=response, body=None)


@pytest.mark.parametrize("failure", ["timeout", "5xx", "overload", "rate limit"])
def test_claude_unreachable_is_tried_again_later_in_the_same_slot(make_app, fake, monkeypatch,
                                                                  failure):
    from mailfilter.fake import FakeMailbox
    from mailfilter.judge import ClaudeJudge, ScriptedJudge

    a, sid = make_app()
    _connect(TestClient(create(a)))
    clock.freeze(SLOT)
    inbox = mail_demo.first_batch(SLOT)
    monkeypatch.setattr(google, "gmail_mailbox", lambda db, s: FakeMailbox(
        [m.mail for m in inbox], address="student@college.edu", now=clock.now))

    class Unavailable:  # Claude on Bedrock, failing the way `failure` says
        class messages:
            @staticmethod
            def create(**kwargs):
                raise _claude_error(failure)

    judge = {"now": ClaudeJudge(Unavailable(), "haiku")}
    monkeypatch.setattr(mail, "live_judge", lambda: judge["now"])
    assert a.check_mail() == 1
    key = mail.mailbox_key(sid, "gmail")
    assert mail.store().runs(key)[-1].error == "judge_unavailable" and mail_items(a, sid) == {}
    assert mail.unfinished(key)
    judge["now"] = ScriptedJudge({m.marker: m.answer for m in inbox})  # Claude answers again
    clock.freeze(SLOT + timedelta(minutes=2))
    assert a.continue_mail() == 0  # not at once: Claude was unreachable a moment ago
    clock.freeze(SLOT + timedelta(minutes=12))
    assert a.continue_mail() == 1
    assert len(mail_items(a, sid)) == 3 and not mail.unfinished(key)
    clock.freeze(SLOT + timedelta(minutes=30))
    assert a.continue_mail() == 0  # done for this slot


# --- 3. one card per mail card, whatever runs at once ------------------------------------------
CARD_FIELDS = {"kind": "deadline", "subject": "Miscellaneous",
               "title": "Nimbus Systems Campus Drive", "due_at": "2030-01-10T17:00+05:30",
               "category": "placement",
               "organisation": "Nimbus Systems", "role": None, "link": None, "mail_link": None,
               "summary": None, "event_at": None, "details": None}


def test_two_instances_copying_the_same_mail_card_make_one_card(make_app, monkeypatch):
    a, sid = make_app()
    clock.freeze(NOW)
    other = Database(a.db.conn.url)  # a second instance, with its own connection
    external = "mail:gmail-1:card-1"
    looked_up = Database.item_by_external
    both_looked = threading.Barrier(2, timeout=10)
    first_look = threading.local()

    def item_by_external(self, student_id, external_id):
        row = looked_up(self, student_id, external_id)
        if not getattr(first_look, "done", False):
            first_look.done = True
            both_looked.wait()  # each saw no card before either copied it
        return row

    monkeypatch.setattr(Database, "item_by_external", item_by_external)
    errors: list[BaseException] = []

    def copy(db):
        try:
            mail._upsert(db, sid, external, dict(CARD_FIELDS), clock.now())
        except BaseException as err:  # noqa: BLE001
            errors.append(err)

    threads = [threading.Thread(target=copy, args=(db,)) for db in (a.db, other)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    other.close()
    assert errors == []
    rows = a.db.conn.execute("SELECT id FROM items WHERE student_id=? AND external_id=?",
                             (sid, external)).fetchall()
    assert len(rows) == 1


def test_copies_made_before_the_unique_index_fold_into_the_first_at_the_next_start(make_app):
    a, sid = make_app()
    clock.freeze(NOW)
    db = a.db
    db.conn.execute("DROP INDEX items_external_unique")  # a database from before the index
    card = {"student_id": sid, "kind": "deadline", "subject": "Miscellaneous",
            "title": "Nimbus Systems Campus Drive", "route": "mail", "source": "gmail",
            "created_at": clock.iso(NOW), "external_id": "mail:gmail-1:card-1"}
    # Two instances copied the card at once; later the mail moved the date, and only the
    # first copy followed it. The student set a reminder and was called on the second.
    first = db.insert_item(**card, due_at="2030-01-11T17:00+05:30")
    second = db.insert_item(**card, due_at="2030-01-10T17:00+05:30")
    third = db.insert_item(**card, due_at="2030-01-10T17:00+05:30")
    db.add_reminder(sid, second, "2030-01-10T16:00+05:30")
    db.add_reminder(sid, third, "2030-01-10T16:00+05:30")  # the same moment again: kept once
    db.add_reminder(sid, first, "2030-01-11T09:00+05:30")
    with db.tx() as c:
        c.execute("INSERT INTO calls(student_id, item_id, status, provider, created_at)"
                  " VALUES (?,?,?,?,?)", (sid, second, "missed", "log", clock.iso(NOW)))
    db.add_notification(sid, "call", "Missed call", "Placement drive", second, clock.iso(NOW))
    db.add_pending("nonce-1", sid, "add_to_calendar", {"item_id": third}, "token",
                   clock.iso(NOW))
    other = db.insert_item(**{**card, "external_id": "mail:gmail-1:card-2"}, due_at=None)

    Database(db.conn.url).close()  # the next start

    rows = db.conn.execute("SELECT id FROM items WHERE student_id=? AND external_id LIKE"
                           " 'mail:%' ORDER BY id", (sid,)).fetchall()
    assert [r["id"] for r in rows] == [first, other]
    assert sorted((r["item_id"], r["fire_at"]) for r in db.reminders(sid)) == [
        (first, "2030-01-11T09:00+05:30"), (first, "2030-01-11T16:00+05:30")]
    assert db.conn.execute("SELECT item_id FROM calls WHERE student_id=?",
                           (sid,)).fetchone()["item_id"] == first
    assert db.notifications(sid, 0)[-1]["item_id"] == first
    assert db.pending(sid) == []  # its approval named a card that is gone
    # From now on the database itself refuses a second copy.
    with pytest.raises(INTEGRITY):
        db.insert_item(**card, due_at=None)
    assert db.insert_item_once(**card, due_at=None) is None
    Database(db.conn.url).close()  # and a later start has nothing left to do


def test_two_deliveries_of_a_new_bot_deadline_at_once_make_one_card(make_app, monkeypatch):
    from seventy5 import sync

    a, sid = make_app()
    clock.freeze(NOW)
    other = Database(a.db.conn.url)
    looked_up = Database.item_by_external
    both_looked = threading.Barrier(2, timeout=10)
    first_look = threading.local()

    def item_by_external(self, student_id, external_id):
        row = looked_up(self, student_id, external_id)
        if not getattr(first_look, "done", False):
            first_look.done = True
            both_looked.wait()
        return row

    monkeypatch.setattr(Database, "item_by_external", item_by_external)
    deadline = {"id": 7, "title": "DBMS assignment", "subject": "Database Management Systems",
                "due_at": "2030-01-09T23:59+05:30"}
    results = {}

    def deliver(db, version):
        event = db.insert_event(sid, f"bot:evt-{version}", "bot", {}, clock.iso(NOW))
        results[version] = sync.apply(db, sid, event, {"type": "deadline.updated",
                                                       "version": version, "deadline": deadline})

    threads = [threading.Thread(target=deliver, args=(db, v)) for db, v in ((a.db, 1), (other, 2))]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    other.close()
    rows = a.db.conn.execute("SELECT * FROM items WHERE student_id=? AND external_id=?",
                             (sid, "bot:deadline:7")).fetchall()
    assert len(rows) == 1 and rows[0]["external_version"] == 2  # the newer delivery won
    assert sorted(r.status for r in results.values()) in (["filed", "updated"], ["filed", "stale"])


# --- 4. Classroom work the cascade could not file is filed by a later sync ----------------------
class Reads:
    """The LLM, back again (and reading the time wrong: Classroom's own date must win)."""

    def propose(self, text, subjects, today, hints):
        return Proposal("deadline", "Operating Systems", "Mini project", "2030-01-10T09:00+05:30")


@pytest.mark.parametrize("next_time", ["the LLM is back", "Jev is sure this time"])
def test_classroom_work_left_for_review_is_filed_by_the_next_sync(make_app, fake, next_time):
    a, sid = make_app()
    _connect(TestClient(create(a)))
    clock.freeze(NOW)
    fake.works = [dict(WORK)]
    # Jev is unsure of the subject and the LLM is down: a card for the student to review.
    a.cascade.jev = ScriptedDecider({})
    a.cascade.llm = ScriptedLLM({})
    assert google.classroom_sync(a, sid) == 0
    assert [r["status"] for r in classroom_cards(a, sid)] == ["needs_review"]
    assert not [c for c in tools.due_this_week(a.db, sid) if c["title"] == "Mini project"]

    if next_time == "the LLM is back":
        a.cascade.llm = Reads()
    else:
        a.cascade.jev = ScriptedDecider(SURE)  # files it by Classroom's own date, no LLM
    assert google.classroom_sync(a, sid) == 1
    [card] = [c for c in tools.due_this_week(a.db, sid) if c["title"] == "Mini project"]
    assert card["due_at"] == WORK_DUE and card["subject"] == "Operating Systems"
    assert [r["status"] for r in classroom_cards(a, sid)] == ["filed"]  # the same card, filed
    a.gateway.call(sid, "set_reminder", {"item_id": card["id"], "before_minutes": 60})
    assert google.classroom_sync(a, sid) == 0  # nothing new, nothing run again
    assert [r["id"] for r in classroom_cards(a, sid)] == [card["id"]]


def test_classroom_work_whose_run_was_cut_off_is_filed_by_the_next_sync(make_app, fake):
    from seventy5.jobqueue import Queue

    a, sid = make_app()
    _connect(TestClient(create(a)))
    clock.freeze(NOW)
    fake.works = [dict(WORK)]
    a.cascade.jev = ScriptedDecider(SURE)
    a.work = lambda: []  # the Lambda is stopped before its drain runs ...
    assert google.classroom_sync(a, sid) == 0
    a.queue = Queue()  # ... and the in-memory queue goes with it
    del a.work
    assert classroom_cards(a, sid) == []
    assert google.classroom_sync(a, sid) == 1
    [card] = [c for c in tools.due_this_week(a.db, sid) if c["title"] == "Mini project"]
    assert card["due_at"] == WORK_DUE and len(classroom_cards(a, sid)) == 1


# --- 5. a dead Google grant -------------------------------------------------------------------
def test_a_dead_google_grant_asks_to_reconnect_once_and_waits_for_it(make_app, fake, monkeypatch):
    from mailfilter.judge import ScriptedJudge

    a, sid = make_app()
    client = TestClient(create(a))
    _connect(client)
    clock.freeze(SLOT)
    item = file_item(a, sid, due="2030-01-09T23:59")
    monkeypatch.setattr(mail, "live_judge", lambda: ScriptedJudge({}))
    fake.works = [dict(WORK)]
    a.cascade.jev = ScriptedDecider(SURE)
    fake.refresh_error = "invalid_grant"  # the Testing-mode week passed, or the student revoked
    scheduler = Scheduler(a.db, a.jobs())
    tick(a, scheduler)  # 1 PM: the mail check meets Google's refusal

    settings = client.get("/api/settings", headers=AUTH).json()["google"]
    assert settings["needs_reconnect"] and settings["connected"]  # still linked: say Reconnect
    assert settings["gmail"] and settings["classroom"]  # the old fields keep their meaning
    notes = client.get("/api/notifications", headers=AUTH).json()["notifications"]
    assert [(n["kind"], n["title"]) for n in notes] == [("google", "Reconnect Google")]
    assert "Settings" in notes[0]["body"]
    assert client.get("/api/mail", headers=AUTH).json()["needs_reconnect"]

    # Nothing more is asked of Google, and nothing more is said, however often the jobs run.
    asked = len(fake.requests)
    drive(a, scheduler, SLOT + timedelta(minutes=1), 40)
    drive(a, scheduler, at(2030, 1, 7, 21, 0), 10)
    check = client.post("/api/mail/check", headers=AUTH)
    assert check.status_code == 409 and "Reconnect Google" in check.json()["detail"]
    assert tools.add_to_calendar(a.db, sid, item)["google"] == {"ok": False,
                                                                "reason": "invalid_grant"}
    assert len(fake.requests) == asked
    assert classroom_cards(a, sid) == []
    assert len(client.get("/api/notifications", headers=AUTH).json()["notifications"]) == 1

    # Connecting again clears it, and Google's work starts again at once.
    fake.refresh_error = None
    clock.freeze(at(2030, 1, 7, 21, 15))
    _connect(client)
    settings = client.get("/api/settings", headers=AUTH).json()["google"]
    assert settings["connected"] and not settings["needs_reconnect"]
    assert not client.get("/api/mail", headers=AUTH).json()["needs_reconnect"]
    drive(a, scheduler, at(2030, 1, 7, 21, 16), 3)
    [card] = classroom_cards(a, sid)
    assert card["status"] == "filed" and card["due_at"] == WORK_DUE
    assert tools.add_to_calendar(a.db, sid, item)["google"]["ok"]


def test_a_grant_refused_after_the_student_reconnected_does_not_flag_the_new_one(make_app, fake):
    a, sid = make_app()
    client = TestClient(create(a))
    _connect(client)
    old = a.db.google_account(sid)["refresh_token"]
    _connect(client)  # a new grant replaced it while a tick still held the old one
    google._grant_lost(a.db, sid, old, "invalid_grant")
    assert not client.get("/api/settings", headers=AUTH).json()["google"]["needs_reconnect"]
    assert client.get("/api/notifications", headers=AUTH).json()["notifications"] == []


# --- 6. events a killed Lambda left queued --------------------------------------------------------
def _lost_events(a, sid, n):
    """Accepted, then the Lambda died: its in-memory queue went with it."""
    from seventy5.ingress import accept
    from seventy5.jobqueue import Queue

    return [accept(a.db, Queue(), sid, "whatsapp", f"wamid.lost{i}",
                   {"text": f"OS unit {i} slides", "attachment": f"OS_Unit{i}.pdf"})
            for i in range(n)]


def test_an_event_a_killed_lambda_left_queued_runs_again_once(make_app):
    from seventy5.app import build

    a, sid = make_app()
    clock.freeze(NOW)
    [job] = [j for j in a.jobs() if j.name == "events-redrive"]
    assert job.every is not None
    material = {"kind": Picked("material", .95), "subject": Picked("Operating Systems", .95)}
    a.cascade.jev = ScriptedDecider(material)
    [event] = _lost_events(a, sid, 1)
    assert a.redrive() == 0 and a.db.event(event)["status"] == "queued"  # it may still be running

    clock.freeze(NOW + timedelta(minutes=6))
    other = build(a.db.conn.url, jev=ScriptedDecider(material))  # a second instance
    seen_by_other = []

    class Busy(ScriptedDecider):
        """While this instance runs the event, the other instance's tick comes round."""

        def decide(self, state, questions):
            seen_by_other.append(other.redrive())
            return super().decide(state, questions)

    a.cascade.jev = Busy(material)
    assert a.redrive() == 1
    assert seen_by_other == [0]
    assert a.db.event(event)["status"] == "done"
    clock.freeze(NOW + timedelta(minutes=20))
    assert a.redrive() == 0 and other.redrive() == 0  # done: nothing runs it again
    cards = a.db.conn.execute("SELECT * FROM items WHERE event_id=?", (event,)).fetchall()
    assert [(c["kind"], c["status"]) for c in cards] == [("material", "filed")]
    other.db.close()


def test_redriving_is_bounded_keeps_to_the_tick_and_parks_what_keeps_failing(make_app):
    from seventy5 import app as app_module

    a, sid = make_app()
    clock.freeze(NOW)
    material = {"kind": Picked("material", .95), "subject": Picked("Operating Systems", .95)}
    a.cascade.jev = ScriptedDecider(material)
    events = _lost_events(a, sid, app_module.REDRIVE_BATCH + 2)
    clock.freeze(NOW + timedelta(minutes=6))
    a.deadline = time.monotonic() + 5  # a turn the mail check already used
    assert a.redrive() == 0
    a.deadline = None
    assert a.redrive() == app_module.REDRIVE_BATCH  # a few per turn, oldest first
    assert [a.db.event(e)["status"] for e in events] == (
        ["done"] * app_module.REDRIVE_BATCH + ["queued", "queued"])
    clock.freeze(NOW + timedelta(minutes=12))
    a.cascade.jev = ScriptedDecider(RuntimeError("cascade bug"))  # every try fails
    for minute in range(12, 12 + 6 * app_module.REDRIVE_TRIES, 6):
        clock.freeze(NOW + timedelta(minutes=minute))
        a.redrive()
    assert [a.db.event(e)["status"] for e in events[-2:]] == ["dead", "dead"]
    assert a.db.event(events[-1])["last_error"] == "RuntimeError"


def test_a_mail_card_or_backfill_event_left_queued_is_closed_without_the_cascade(make_app):
    a, sid = make_app()
    clock.freeze(NOW)
    card = a.db.insert_event(sid, "mail:demo-1:9", "gmail", {"mail_card": "mail:demo-1:9"},
                             clock.iso(NOW))
    backfill = a.db.insert_event(sid, "bot:backfill:x", "bot", {"type": "backfill"},
                                 clock.iso(NOW))
    clock.freeze(NOW + timedelta(minutes=6))
    a.redrive()
    assert a.db.event(card)["status"] == a.db.event(backfill)["status"] == "done"
    assert a.db.conn.execute("SELECT COUNT(*) AS n FROM items WHERE student_id=?",
                             (sid,)).fetchone()["n"] == 0  # no "Unreadable message" card
