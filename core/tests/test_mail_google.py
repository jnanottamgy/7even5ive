"""College mail as cards (the mail filter behind mail.py) and the one Google sign-in on the server
(google.py): Gmail read-only, Calendar after a tap, Classroom with its own due dates."""

from __future__ import annotations

import base64
import json
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from urllib.parse import parse_qs, urlsplit

import httpx
import pytest
from fastapi.testclient import TestClient

from conftest import at, file_item
from seventy5 import clock, demo, google, mail, notify, tools
from seventy5.api import create
from seventy5.gateway import Denied
from seventy5.db import token_hash

# Google is for a student's own account, never the shared demo one (accounts.refuse_demo): the
# seeded student is given a token of its own, which makes it an ordinary student.
STUDENT_TOKEN = "own-student-token"
AUTH = {"authorization": f"Bearer {STUDENT_TOKEN}"}


@pytest.fixture
def make_app(make_app):
    def make(*args, **kwargs):
        a, sid = make_app(*args, **kwargs)
        a.db.update_student(sid, token_hash=token_hash(STUDENT_TOKEN))
        assert not demo.is_demo(a.db, sid)
        return a, sid

    return make
NOW = at(2030, 1, 7, 10, 0)  # a Monday
ALL_SCOPES = " ".join(google.SCOPES[2:])


def mail_items(a, sid, status="filed"):
    return {r["category"] + ":" + r["organisation"]: r for r in a.db.conn.execute(
        "SELECT * FROM items WHERE student_id=? AND route='mail' AND status=?",
        (sid, status)).fetchall()}


# --- the demo mailbox ---------------------------------------------------------------------------
def test_the_demo_mailbox_fills_the_inbox_with_checked_cards(make_app):
    a, sid = make_app()
    clock.freeze(NOW)
    assert mail.startup(a.db, sid) == ["mail      demo mailbox: 3 cards, 2 left out"]
    cards = mail_items(a, sid)
    nimbus = cards["placement:Nimbus Systems"]
    assert (nimbus["kind"], nimbus["due_at"], nimbus["event_at"]) == (
        "deadline", "2030-01-10T17:00+05:30", "2030-01-12T10:00+05:30")
    assert nimbus["role"] == "Graduate Engineer Trainee"
    assert nimbus["link"] == "https://forms.gle/NimbusDrive2027"
    assert nimbus["mail_link"].startswith("https://mail.google.com/")
    exam = cards["exam_notice:Controller of Examinations"]
    assert (exam["kind"], exam["due_at"], exam["event_at"]) == ("exam", "2030-01-16T09:00+05:30",
                                                                 None)
    assert cards["internship:Orbitly"]["due_at"] == "2030-01-13T23:59+05:30"
    due = [c["title"] for c in tools.due_this_week(a.db, sid)]
    assert "Nimbus Systems Campus Drive" in due and "CIE-3 Schedule – 5th Semester" not in due
    inbox = {c["category"]: c for c in tools.opportunities(a.db, sid)}
    assert set(inbox) == {"placement", "internship", "exam_notice"}
    assert inbox["placement"]["summary"] and inbox["placement"]["organisation"] == "Nimbus Systems"


def test_no_mail_words_are_stored_beside_a_card(make_app):
    a, sid = make_app()
    clock.freeze(NOW)
    mail.startup(a.db, sid)
    payloads = [json.loads(r["payload"]) for r in a.db.conn.execute(
        "SELECT payload FROM events WHERE source='gmail'").fetchall()]
    assert payloads and all(set(p) == {"mail_card"} for p in payloads)


def test_check_now_finds_the_new_mail_then_waits_five_minutes(make_app):
    a, sid = make_app()
    clock.freeze(NOW)
    mail.startup(a.db, sid)
    client = TestClient(create(a))
    first = client.post("/api/mail/check", headers=AUTH).json()
    assert first["new"] == 1 and first["mode"] == "demo" and first["cards"] == 4
    assert "internship:Zentry Labs" in mail_items(a, sid)
    again = client.post("/api/mail/check", headers=AUTH)
    assert again.status_code == 429 and "few minutes" in again.json()["detail"]
    assert client.get("/api/mail", headers=AUTH).json()["check_now_after"] is not None
    clock.freeze(NOW + timedelta(minutes=6))
    assert client.post("/api/mail/check", headers=AUTH).json()["new"] == 0
    with pytest.raises(Denied):  # the same cooldown holds for Claude and the voice assistant
        a.gateway.call(sid, "check_mail_now")


def test_a_changed_card_moves_its_reminder_and_done_stays_done(make_app):
    a, sid = make_app()
    clock.freeze(NOW)
    mail.startup(a.db, sid)
    nimbus = mail_items(a, sid)["placement:Nimbus Systems"]
    a.gateway.call(sid, "set_reminder", {"item_id": nimbus["id"], "before_minutes": 60})
    fields = {k: nimbus[k] for k in ("kind", "subject", "title", "category", "organisation",
                                     "role", "link", "mail_link", "summary", "event_at")}
    mail._upsert(a.db, sid, nimbus["external_id"], {**fields, "due_at": "2030-01-11T17:00+05:30"},
                 clock.now())
    assert [r["fire_at"] for r in a.db.reminders(sid)] == ["2030-01-11T16:00+05:30"]
    a.gateway.call(sid, "mark_done", {"item_id": nimbus["id"]})
    mail.sync_cards(a.db, sid)
    assert a.db.item(sid, nimbus["id"])["status"] == "done"


def test_a_reset_demo_mailbox_starts_from_the_morning_again(make_app):
    a, sid = make_app()
    clock.freeze(NOW)
    mail.startup(a.db, sid)
    mail.check(a.db, sid, "check_now")
    mail.reset_demo(sid)
    assert mail.startup(a.db, sid) == ["mail      demo mailbox: 3 cards, 2 left out"]


def test_the_scheduled_job_checks_at_one_and_nine(make_app):
    a, sid = make_app()
    [job] = [j for j in a.jobs() if j.name == "mail"]
    assert [t.strftime("%H:%M") for t in job.at] == ["13:00", "21:00"]
    clock.freeze(NOW)
    assert a.check_mail() == 1 and len(mail_items(a, sid)) == 3


def test_cards_and_status_carry_the_mailbox(make_app):
    a, sid = make_app()
    clock.freeze(NOW)
    mail.startup(a.db, sid)
    got = TestClient(create(a)).get("/api/cards", headers=AUTH).json()["mail"]
    assert got["mode"] == "demo" and got["connected"] and got["left_out"] == 2
    assert got["next_check_at"] == "2030-01-07T13:00+05:30" and got["address"] is None


# --- Google sign-in -------------------------------------------------------------------------------
def _id_token(email: str) -> str:
    claims = base64.urlsafe_b64encode(json.dumps({"email": email}).encode()).decode().rstrip("=")
    return f"e30.{claims}.sig"


class FakeGoogle:
    def __init__(self, scopes: str = ALL_SCOPES) -> None:
        self.scopes = scopes
        self.requests: list[httpx.Request] = []
        self.refresh_error: str | None = None
        self.calendar_conflict = False
        self.works: list[dict] = []

    def client(self) -> httpx.Client:
        return httpx.Client(transport=httpx.MockTransport(self.handle))

    def handle(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        url = str(request.url)
        if url == google.TOKEN_URL:
            form = parse_qs(request.content.decode())
            if form["grant_type"] == ["authorization_code"]:
                return httpx.Response(200, json={"refresh_token": "1//refresh", "scope":
                                                 self.scopes, "access_token": "ya29.first",
                                                 "id_token": _id_token("student@college.edu")})
            if self.refresh_error:
                return httpx.Response(400, json={"error": self.refresh_error})
            return httpx.Response(200, json={"access_token": "ya29.fresh", "expires_in": 3600})
        if url.startswith(google.REVOKE_URL):
            return httpx.Response(200)
        if url.startswith(google.CALENDAR):
            if request.method == "POST" and self.calendar_conflict:
                return httpx.Response(409, json={})
            return httpx.Response(200, json={"htmlLink": "https://calendar.google.com/e/1"})
        if url.startswith(f"{google.CLASSROOM}/courses/c1/courseWork"):
            return httpx.Response(200, json={"courseWork": self.works})
        if url.startswith(f"{google.CLASSROOM}/courses"):
            return httpx.Response(200, json={"courses": [{"id": "c1", "name": "Operating Systems"}]})
        return httpx.Response(404)

    def sent(self, prefix: str) -> list[httpx.Request]:
        return [r for r in self.requests if str(r.url).startswith(prefix)]


@pytest.fixture
def fake(monkeypatch):
    configured = replace(google.settings, google_client_id="cid.apps.googleusercontent.com",
                         google_client_secret="secret", token_encryption_key="", public_url="")
    monkeypatch.setattr(google, "settings", configured)
    g = FakeGoogle()
    monkeypatch.setattr(google, "_http", g.client)
    return g


def _connect(client: TestClient, headers: dict | None = None) -> httpx.Response:
    """Start, come back from Google, and let the app finish, as the real flow does."""
    url = client.post("/api/google/start", headers=AUTH).json()["url"]
    state = parse_qs(urlsplit(url).query)["state"][0]
    page = client.get(f"/api/google/callback?code=4/abc&state={state}")
    assert page.status_code == 200 and "sevenfive://google?" in page.text
    done = client.post("/api/google/finish", json={"code": "4/abc", "state": state},
                       headers=headers or AUTH)
    done.state = state  # type: ignore[attr-defined]
    return done


def test_without_a_client_the_app_is_told_what_is_missing(make_app):
    a, _ = make_app()
    r = TestClient(create(a)).post("/api/google/start", headers=AUTH)
    assert r.status_code == 503 and "GOOGLE_CLIENT_ID" in r.json()["detail"]


def test_the_consent_page_carries_a_one_time_state_and_no_student_token(make_app, fake):
    a, sid = make_app()
    url = TestClient(create(a)).post("/api/google/start", headers=AUTH).json()["url"]
    query = parse_qs(urlsplit(url).query)
    assert url.startswith(google.AUTH_URL) and STUDENT_TOKEN not in url
    assert query["redirect_uri"] == ["http://testserver/api/google/callback"]
    assert query["code_challenge_method"] == ["S256"] and query["access_type"] == ["offline"]
    assert set(query["scope"][0].split()) == set(google.SCOPES)
    row = a.db.conn.execute("SELECT * FROM connect_codes").fetchone()
    assert row["code"] == query["state"][0] and row["student_id"] == sid


def test_the_sign_in_stores_an_encrypted_grant_once(make_app, fake):
    a, sid = make_app()
    client = TestClient(create(a))
    clock.freeze(NOW)
    mail.startup(a.db, sid)
    done = _connect(client)
    assert done.status_code == 200 and done.json()["google"]["connected"]
    row = a.db.google_account(sid)
    assert row["email"] == "student@college.edu" and row["refresh_token"] != "1//refresh"
    assert google.unseal(row["refresh_token"]) == "1//refresh"
    exchange = parse_qs(fake.sent(google.TOKEN_URL)[0].content.decode())
    assert exchange["code_verifier"][0] and exchange["redirect_uri"] == [
        "http://testserver/api/google/callback"]
    status = client.get("/api/settings", headers=AUTH).json()["google"]
    assert status["connected"] and status["gmail"] and status["calendar"] and status["classroom"]
    assert mail_items(a, sid) == {}  # the invented demo mail left the Inbox at once
    assert len(mail_items(a, sid, "cancelled")) == 3
    reused = client.post("/api/google/finish", json={"code": "4/abc", "state": done.state},
                         headers=AUTH)
    assert reused.status_code == 409 and "already used" in reused.json()["detail"]
    assert client.get(f"/api/google/callback?code=4/abc&state={done.state}").status_code == 400


def test_only_the_student_who_started_a_sign_in_can_finish_it(make_app, fake):
    a, sid = make_app()
    with a.db.tx() as c:
        c.execute("INSERT INTO students(name, token_hash) VALUES ('B', ?)", (token_hash('tok-b'),))
    client = TestClient(create(a))
    url = client.post("/api/google/start", headers=AUTH).json()["url"]
    state = parse_qs(urlsplit(url).query)["state"][0]
    # The consent link went to someone else, who agreed and finished it in their own app.
    theirs = client.post("/api/google/finish", json={"code": "4/abc", "state": state},
                         headers={"authorization": "Bearer tok-b"})
    assert theirs.status_code == 409 and "another account" in theirs.json()["detail"]
    assert a.db.google_account(sid) is None and not fake.sent(google.TOKEN_URL)
    mine = client.post("/api/google/finish", json={"code": "4/abc", "state": state}, headers=AUTH)
    assert mine.status_code == 200  # not spent by the refusal


def test_the_hand_off_page_carries_only_the_code_and_state_escaped(make_app, fake):
    a, sid = make_app()
    client = TestClient(create(a))
    url = client.post("/api/google/start", headers=AUTH).json()["url"]
    state = parse_qs(urlsplit(url).query)["state"][0]
    page = client.get(f"/api/google/callback?code=<script>x</script>&state={state}").text
    assert "<script>x</script>" not in page and "package=com.sevenfive.app" in page
    assert STUDENT_TOKEN not in page


def test_a_spent_expired_or_refused_sign_in_shows_why(make_app, fake):
    a, sid = make_app()
    client = TestClient(create(a))
    url = client.post("/api/google/start", headers=AUTH).json()["url"]
    state = parse_qs(urlsplit(url).query)["state"][0]
    assert "allow access" in client.get(f"/api/google/callback?error=access_denied&state={state}").text
    clock.freeze(clock.now() + timedelta(minutes=11))
    late = client.get(f"/api/google/callback?code=4/abc&state={state}")
    assert late.status_code == 400 and "expired" in late.text
    finished_late = client.post("/api/google/finish", json={"code": "4/abc", "state": state},
                                headers=AUTH)
    assert finished_late.status_code == 409
    clock.freeze(None)
    assert client.get("/api/google/callback?code=4/abc&state=made-up").status_code == 400
    assert a.db.google_account(sid) is None


def test_access_tokens_are_cached_and_a_revoked_grant_asks_to_reconnect(make_app, fake):
    from mailfilter.errors import NeedsReconnect

    a, sid = make_app()
    _connect(TestClient(create(a)))
    assert google.access_token(a.db, sid) == google.access_token(a.db, sid) == "ya29.fresh"
    assert len(fake.sent(google.TOKEN_URL)) == 2  # the code exchange, then one refresh
    fake.refresh_error = "invalid_grant"
    with pytest.raises(NeedsReconnect):
        google.access_token(a.db, sid, fresh=True)


def test_disconnect_revokes_then_forgets_everything(make_app, fake):
    a, sid = make_app()
    client = TestClient(create(a))
    _connect(client)
    out = client.post("/api/google/disconnect", headers=AUTH).json()
    assert out["disconnected"] and not out["google"]["connected"]
    assert parse_qs(fake.sent(google.REVOKE_URL)[0].content.decode())["token"] == ["1//refresh"]
    assert a.db.google_account(sid) is None and mail.mode(a.db, sid) == "demo"


def test_a_grant_sealed_with_another_key_asks_to_reconnect(make_app, fake, monkeypatch):
    from mailfilter.errors import NeedsReconnect

    a, sid = make_app()
    _connect(TestClient(create(a)))
    monkeypatch.setattr(google, "settings", replace(google.settings,
                                                    token_encryption_key="a long random string"))
    with pytest.raises(NeedsReconnect):
        google.access_token(a.db, sid, fresh=True)
    assert google.unseal(google.seal("x")) == "x"  # any long string works as a key


# --- Gmail, Calendar and Classroom once connected -----------------------------------------------
def test_real_mail_needs_claude_then_is_judged_and_checked(make_app, fake, monkeypatch):
    from mailfilter.fake import FakeMailbox
    from mailfilter.judge import ScriptedJudge

    from seventy5 import mail_demo

    a, sid = make_app()
    _connect(TestClient(create(a)))
    clock.freeze(NOW)
    with pytest.raises(mail.MailUnavailable, match="needs Claude"):
        mail.check(a.db, sid)
    inbox = mail_demo.first_batch(NOW)
    monkeypatch.setattr(google, "gmail_mailbox", lambda db, s: FakeMailbox(
        [m.mail for m in inbox], address="student@college.edu", now=clock.now))
    monkeypatch.setattr(mail, "live_judge", lambda: ScriptedJudge({m.marker: m.answer
                                                                     for m in inbox}))
    out = mail.check(a.db, sid)
    assert out["mode"] == "gmail" and out["cards"] == 3
    assert all(":gmail-" in r["external_id"] for r in mail_items(a, sid).values())


def test_an_approved_calendar_write_goes_to_google_with_the_fixed_id(make_app, fake):
    a, sid = make_app()
    _connect(TestClient(create(a)))
    item = file_item(a, sid, due="2030-01-09T23:59")
    gw = a.gateway
    gw.call(sid, "add_to_calendar", {"item_id": item})
    token = a.db.pending(sid)[0]["token"]
    fake.calendar_conflict = True  # the event exists already: rewrite it, never a second one
    out = gw.approve(sid, token)["result"]
    assert out["google"]["ok"] and out["calendar_event"] == tools.calendar_key(sid, item)
    post, put = fake.sent(google.CALENDAR)
    assert post.method == "POST" and put.method == "PUT" and put.url.path.endswith(
        out["calendar_event"])
    event = json.loads(put.content)
    assert event["id"] == out["calendar_event"] and event["start"]["timeZone"] == "Asia/Kolkata"
    assert put.headers["authorization"] == "Bearer ya29.fresh"


def test_a_calendar_failure_still_keeps_the_card_and_says_so(make_app, fake):
    a, sid = make_app()
    _connect(TestClient(create(a)))
    fake.refresh_error = "invalid_grant"
    item = file_item(a, sid, due="2030-01-09T23:59")
    out = tools.add_to_calendar(a.db, sid, item)
    assert out["google"] == {"ok": False, "reason": "invalid_grant"}
    assert a.db.calendar(sid)[0]["event_key"] == out["calendar_event"]


def test_classroom_due_dates_win_and_move_the_card(make_app, fake):
    from seventy5.jev import Picked, ScriptedDecider

    a, sid = make_app()
    _connect(TestClient(create(a)))
    clock.freeze(NOW)
    a.cascade.jev = ScriptedDecider({"kind": Picked("deadline", .95),
                                     "subject": Picked("Operating Systems", .95)})
    fake.works = [
        {"id": "w1", "title": "Mini project", "dueDate": {"year": 2030, "month": 1, "day": 10},
         "dueTime": {"hours": 18, "minutes": 29}},
        {"id": "w0", "title": "Old lab", "dueDate": {"year": 2029, "month": 12, "day": 1},
         "dueTime": {}}]
    assert google.classroom_sync(a, sid) == 1
    [card] = [c for c in tools.due_this_week(a.db, sid) if c["title"] == "Mini project"]
    assert card["due_at"] == "2030-01-10T23:59+05:30" and card["route"] == "classroom"
    a.gateway.call(sid, "set_reminder", {"item_id": card["id"], "before_minutes": 60})
    fake.works[0]["dueDate"]["day"] = 11  # the teacher gave an extension
    assert google.classroom_sync(a, sid) == 0
    assert a.db.item(sid, card["id"])["due_at"] == "2030-01-11T23:59+05:30"
    assert [r["fire_at"] for r in a.db.reminders(sid)] == ["2030-01-11T22:59+05:30"]


def test_classroom_times_are_utc_and_omitted_zeros_mean_midnight():
    assert google._due({"dueDate": {"year": 2030, "month": 1, "day": 10}, "dueTime": {}}) == \
        datetime(2030, 1, 10, 0, 0, tzinfo=timezone.utc)
    assert google._due({"dueDate": {"year": 2030, "month": 1, "day": 10}}) == \
        datetime(2030, 1, 10, 23, 59, tzinfo=timezone.utc)
    assert google._due({"dueDate": {"year": 2030}}) is None


def test_without_the_classroom_scope_nothing_is_read(make_app, fake):
    a, sid = make_app()
    fake.scopes = google.GMAIL_SCOPE
    _connect(TestClient(create(a)))
    assert google.classroom_sync(a, sid) == 0 and not fake.sent(google.CLASSROOM)


def test_a_check_cut_short_goes_on_at_the_next_turn(make_app, monkeypatch):
    from dataclasses import replace as swap

    a, sid = make_app()
    real = mail.mail_settings
    monkeypatch.setattr(mail, "mail_settings", lambda: swap(real(), max_mails_per_run=2))
    clock.freeze(NOW)
    mail.startup(a.db, sid)  # 5 mails, 2 per run: stopped early
    assert len(mail_items(a, sid)) < 3 and mail.unfinished(mail.mailbox_key(sid, "demo"))
    for _ in range(3):
        a.continue_mail()
    assert len(mail_items(a, sid)) == 3
    assert not mail.unfinished(mail.mailbox_key(sid, "demo")) and a.continue_mail() == 0


def test_reconnecting_google_revives_a_mailbox_google_cut_off(make_app, fake, monkeypatch):
    from mailfilter.fake import FakeMailbox
    from mailfilter.judge import ScriptedJudge

    from seventy5 import mail_demo

    a, sid = make_app()
    client = TestClient(create(a))
    _connect(client)
    clock.freeze(NOW)
    key = mail.mailbox_key(sid, "gmail")
    assert mail.store().connection(key).status == "connected"  # connected at sign-in, not later
    mail.store().mark(key, "needs_reconnect", "invalid_grant")  # a Testing-mode week passed
    _connect(client)
    assert mail.store().connection(key).status == "connected"
    inbox = mail_demo.first_batch(NOW)
    monkeypatch.setattr(google, "gmail_mailbox", lambda db, s: FakeMailbox(
        [m.mail for m in inbox], address="student@college.edu", now=clock.now))
    monkeypatch.setattr(mail, "live_judge", lambda: ScriptedJudge({m.marker: m.answer
                                                                     for m in inbox}))
    assert mail.check(a.db, sid)["cards"] == 3


def test_disconnect_then_reconnect_shows_the_new_cards(make_app, fake, monkeypatch):
    from mailfilter.fake import FakeMailbox
    from mailfilter.judge import ScriptedJudge

    from seventy5 import mail_demo

    a, sid = make_app()
    client = TestClient(create(a))
    clock.freeze(NOW)
    mail.startup(a.db, sid)  # the demo mailbox first
    inbox = mail_demo.first_batch(NOW)
    monkeypatch.setattr(google, "gmail_mailbox", lambda db, s: FakeMailbox(
        [m.mail for m in inbox], address="student@college.edu", now=clock.now))
    monkeypatch.setattr(mail, "live_judge", lambda: ScriptedJudge({m.marker: m.answer
                                                                     for m in inbox}))
    _connect(client)
    mail.check(a.db, sid)
    assert len(mail_items(a, sid)) == 3
    client.post("/api/google/disconnect", headers=AUTH)
    assert len(mail_items(a, sid)) == 3  # the demo mailbox's cards are back
    assert not [r for r in mail_items(a, sid).values() if ":gmail-" in r["external_id"]]
    assert a.db.conn.execute("SELECT COUNT(*) AS n FROM items WHERE external_id LIKE"
                             " 'mail:gmail-%'").fetchone()["n"] == 0  # read from Gmail: gone
    _connect(client)
    mail.check(a.db, sid)
    shown = mail_items(a, sid)
    assert len(shown) == 3 and all(":gmail-" in r["external_id"] for r in shown.values())



def test_check_now_stays_inside_its_deadline_and_the_rest_goes_on_later(make_app, monkeypatch):
    a, sid = make_app()
    clock.freeze(NOW)
    monkeypatch.setattr(mail, "CHECK_NOW_SECONDS", 0.0)  # no time at all: nothing is judged
    out = TestClient(create(a)).post("/api/mail/check", headers=AUTH).json()
    assert out["judged"] == 0 and out["more"]
    assert mail.unfinished(mail.mailbox_key(sid, "demo"))
    a.continue_mail()  # the background loop finishes it, the Check now's new mail included
    assert len(mail_items(a, sid)) == 4


def test_a_tick_that_used_its_time_leaves_the_rest_for_the_next(make_app, monkeypatch):
    import time as clock_time

    a, sid = make_app()
    clock.freeze(NOW)
    a.deadline = clock_time.monotonic() + 5  # less than one mail's reserve left
    assert a.check_mail() == 0  # no mailbox started
    assert a.continue_mail() == 0
    a.deadline = None
    assert a.check_mail() == 1
