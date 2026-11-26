"""Accounts on Supabase Auth: signed-in students, their profiles, tokens and WhatsApp, deletion;
the demo account's limits; and the database being safe to share (Supabase)."""

from __future__ import annotations

import json
import os
import time
from dataclasses import replace

import httpx
import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import ec
from fastapi.testclient import TestClient

from conftest import at, file_item
from seventy5 import accounts, auth, clock, config, demo, mail
from seventy5 import api as api_module
from seventy5.api import create
from seventy5.db import STUDENT_TABLES, Database, token_hash
from seventy5.ingress import sign

URL = "https://abcdefghijklmnopqrst.supabase.co"
PUB = "sb_publishable_test"
SECRET = "sb_secret_test"
ASHA = "6f1c2a52-6f0e-4bd5-9a5e-2f0d1e9a7c11"
RAVI = "0b8c7f4e-2b0e-4f7f-8f1e-3a2b1c0d9e8f"


class FakeSupabase:
    """One Supabase project, in memory: its signing key served as JWKS, its Auth endpoints."""

    def __init__(self) -> None:
        self.key = ec.generate_private_key(ec.SECP256R1())
        self.kid = "k1"
        self.requests: list[httpx.Request] = []
        self.deleted: list[str] = []
        self.passwords = {"asha@example.com": "correct horse"}
        self.delete_status = 200

    def jwks(self) -> dict:
        public = json.loads(jwt.algorithms.ECAlgorithm.to_jwk(self.key.public_key()))
        return {"keys": [public | {"kid": self.kid, "alg": "ES256", "use": "sig"}]}

    def token(self, sub: str = ASHA, email: str = "asha@example.com", exp_in: int = 3600,
              key=None, kid: str | None = None, alg: str = "ES256", **extra) -> str:
        now = int(time.time())
        claims = {"iss": f"{URL}/auth/v1", "aud": "authenticated", "role": "authenticated",
                  "sub": sub, "email": email, "exp": now + exp_in, "iat": now,
                  "session_id": "s-1", "is_anonymous": False} | extra
        return jwt.encode(claims, key or self.key, algorithm=alg, headers={"kid": kid or self.kid})

    def handler(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        path = request.url.path
        if path == "/auth/v1/.well-known/jwks.json":
            return httpx.Response(200, json=self.jwks())
        if request.method == "DELETE" and path.startswith("/auth/v1/admin/users/"):
            assert request.headers["apikey"] == SECRET
            assert "authorization" not in request.headers  # a secret key is not a JWT
            self.deleted.append(path.rsplit("/", 1)[1])
            return httpx.Response(self.delete_status, json={})
        if path == "/auth/v1/token" and request.url.params.get("grant_type") == "password":
            body = json.loads(request.content)
            if self.passwords.get(body["email"]) == body["password"]:
                return httpx.Response(200, json={"access_token": self.token(),
                                                 "refresh_token": "r1", "expires_in": 3600,
                                                 "token_type": "bearer"})
            return httpx.Response(400, json={"error_code": "invalid_credentials",
                                             "msg": "Invalid login credentials"})
        return httpx.Response(404, json={})

    def client(self) -> httpx.Client:
        return httpx.Client(transport=httpx.MockTransport(self.handler))


@pytest.fixture
def supa(monkeypatch):
    fake = FakeSupabase()
    on = replace(config.settings, supabase_url=URL, supabase_publishable_key=PUB,
                 supabase_secret_key=SECRET, bot_whatsapp_number="919900000075")
    for module in (auth, api_module, accounts):
        monkeypatch.setattr(module, "settings", on)
    monkeypatch.setattr(auth, "_client", fake.client)
    monkeypatch.setattr(auth, "_verifier", None)
    for limiter in (api_module._username_checks, api_module._login_by_ip,
                    api_module._login_by_name):
        monkeypatch.setattr(limiter, "_hits", {})
    return fake


def bearer(token: str) -> dict:
    return {"authorization": f"Bearer {token}"}


def signed_in(make_app, supa, profile: dict | None = None):
    """(app, client, Asha's headers, Asha's student id) with Asha's profile set up."""
    a, demo_sid = make_app()
    client = TestClient(create(a))
    me = bearer(supa.token())
    body = {"username": "asha.k", "name": "Asha K", "branch": "CSE", "year": 3,
            "subjects": ["Operating Systems", "Computer Networks"]} | (profile or {})
    answer = client.post("/api/me", headers=me, json=body)
    assert answer.status_code == 200, answer.text
    return a, client, me, int(a.db.student_by_auth(ASHA)["id"])


# --- signing in and setting up the profile ------------------------------------------------
def test_the_app_learns_how_to_sign_in_and_nothing_secret(make_app, supa, monkeypatch):
    a, _ = make_app()
    client = TestClient(create(a))
    config_ = client.get("/api/auth/config").json()
    assert config_ == {"enabled": True, "supabase_url": URL, "publishable_key": PUB,
                       "username_login": True, "delete_account": True,
                       "password_min_length": 8, "demo": True}
    assert SECRET not in json.dumps(config_)
    monkeypatch.setattr(api_module, "settings", replace(api_module.settings, supabase_url=""))
    monkeypatch.setattr(auth, "settings", replace(auth.settings, supabase_url=""))
    off = client.get("/api/auth/config").json()
    assert off["enabled"] is False and off["publishable_key"] is None


def test_a_new_sign_in_is_sent_to_set_up_a_profile_first(make_app, supa):
    a, _ = make_app()
    client = TestClient(create(a))
    me = bearer(supa.token())
    refused = client.get("/api/cards", headers=me)
    assert refused.status_code == 403 and refused.json()["code"] == "profile_required"
    assert client.get("/api/me", headers=me).json() == {
        "onboarded": False, "email": "asha@example.com", "profile": None, "demo": False}


def test_a_profile_makes_a_student_of_their_own_with_nothing_invented(make_app, supa):
    a, client, me, sid = signed_in(make_app, supa)
    profile = client.get("/api/me", headers=me).json()["profile"]
    assert profile["username"] == "asha.k" and profile["name"] == "Asha K"
    assert profile["subjects"] == ["Operating Systems", "Computer Networks"]
    assert profile["email"] == "asha@example.com" and profile["demo"] is False
    row = a.db.student(sid)
    assert row["portal_id"].startswith("u") and row["portal_id"] != demo.PORTAL_ID
    cards = client.get("/api/cards", headers=me).json()
    assert cards["due_this_week"] == [] and cards["student"]["name"] == "Asha K"
    assert "token_hash" not in cards["student"] and "auth_user_id" not in cards["student"]
    # A real account never gets the demo's invented college mail.
    assert cards["mail"]["mode"] == "none" and not cards["mail"]["connected"]
    check = client.post("/api/mail/check", headers=me)
    assert check.status_code == 409 and "Connect Google" in check.json()["detail"]
    assert mail.check_all(a.db) == 1  # only the demo student's mailbox
    # Changing the profile later: only what is sent changes.
    changed = client.post("/api/me", headers=me, json={"year": 4, "subjects": ["DBMS"]}).json()
    assert changed["profile"]["year"] == 4 and changed["profile"]["username"] == "asha.k"
    assert changed["profile"]["subjects"] == ["DBMS"]


def test_usernames_are_unique_lowercase_and_follow_the_rules(make_app, supa):
    a, client, me, sid = signed_in(make_app, supa)
    ravi = bearer(supa.token(sub=RAVI, email="ravi@example.com"))
    for bad in ("ab", "a" * 31, ".asha", "asha.", "as..ha", "asha k", "admin", "demo", "___"):
        answer = client.post("/api/me", headers=ravi, json={"username": bad, "name": "Ravi"})
        assert answer.status_code == 400, bad
        assert answer.json()["code"] == "invalid_username"
    taken = client.post("/api/me", headers=ravi, json={"username": "ASHA.K", "name": "Ravi"})
    assert taken.status_code == 409 and taken.json()["code"] == "username_taken"
    assert client.get("/api/auth/username", params={"u": "Asha.K"}).json() == {
        "username": "asha.k", "available": False, "message": "That username is taken."}
    assert client.get("/api/auth/username", params={"u": "ravi_s"}).json()["available"]
    made = client.post("/api/me", headers=ravi, json={"username": "Ravi_S", "name": "Ravi"})
    assert made.json()["profile"]["username"] == "ravi_s"
    # Keeping your own name is fine; a name is required the first time.
    assert client.post("/api/me", headers=me, json={"username": "asha.k"}).status_code == 200
    third = bearer(supa.token(sub="9a9a9a9a-0000-4000-8000-000000000001", email="c@example.com"))
    assert client.post("/api/me", headers=third, json={"username": "charu"}).status_code == 400


def test_the_username_check_is_limited_per_address(make_app, supa):
    a, _ = make_app()
    client = TestClient(create(a))
    answers = [client.get("/api/auth/username", params={"u": f"name{i}"}).status_code
               for i in range(61)]
    assert answers[:60] == [200] * 60 and answers[60] == 429


# --- what counts as a session ----------------------------------------------------------------
def test_only_good_sessions_from_this_project_are_accepted(make_app, supa):
    a, client, me, sid = signed_in(make_app, supa)
    other_key = ec.generate_private_key(ec.SECP256R1())
    bad = {
        "expired": supa.token(exp_in=-120),
        "another project": supa.token(iss="https://zzzz.supabase.co/auth/v1"),
        "not for users": supa.token(aud="service"),
        "anonymous": supa.token(is_anonymous=True),
        "anon role": supa.token(role="anon"),
        "forged": supa.token(key=other_key),
        "garbage": "eyJhbGciOi.nonsense.x",
    }
    for name, token in bad.items():
        answer = client.get("/api/cards", headers=bearer(token))
        assert answer.status_code == 401, name
        assert answer.json()["code"] == "session_expired", name
    unsigned = jwt.encode({"sub": ASHA}, key=None, algorithm="none")
    assert client.get("/api/cards", headers=bearer(unsigned)).status_code == 401
    # Within the 30 s leeway a token that just expired still works (phones' clocks drift).
    assert client.get("/api/cards", headers=bearer(supa.token(exp_in=-10))).status_code == 200


def test_a_rotated_signing_key_is_picked_up_without_a_restart(supa):
    now = [1000.0]
    verifier = auth.Verifier(URL, PUB, http=supa.client(), clock=lambda: now[0])
    assert verifier.verify(supa.token()).user_id == ASHA
    supa.key, supa.kid = ec.generate_private_key(ec.SECP256R1()), "k2"
    fresh = supa.token()
    with pytest.raises(auth.AuthError):
        verifier.verify(fresh)  # an unknown key: the set was fetched a moment ago
    now[0] += auth.JWKS_RETRY_SECONDS + 1
    assert verifier.verify(fresh).user_id == ASHA
    fetched = [r for r in supa.requests if r.url.path.endswith("jwks.json")]
    assert len(fetched) == 2 and fetched[0].headers["apikey"] == PUB


def test_a_legacy_project_is_checked_with_its_secret_or_by_asking_supabase(supa):
    secret = "legacy-jwt-secret-legacy-jwt-secret"
    token = supa.token(key=secret, alg="HS256")
    assert auth.Verifier(URL, PUB, jwt_secret=secret, http=supa.client()).verify(
        token).user_id == ASHA
    with pytest.raises(auth.AuthError):
        auth.Verifier(URL, PUB, jwt_secret="another-secret-another-secret-0123",
                      http=supa.client()).verify(token)
    asked: list[str] = []

    def user_endpoint(request: httpx.Request) -> httpx.Response:
        asked.append(request.headers["authorization"])
        assert request.headers["apikey"] == PUB
        good = request.headers["authorization"] == f"Bearer {token}"
        return httpx.Response(200 if good else 401,
                              json={"id": ASHA, "email": "asha@example.com"} if good else {})

    verifier = auth.Verifier(URL, PUB, http=httpx.Client(
        transport=httpx.MockTransport(user_endpoint)))
    assert verifier.verify(token).user_id == ASHA
    assert verifier.verify(token).user_id == ASHA  # remembered: Supabase asked once
    assert len(asked) == 1
    with pytest.raises(auth.AuthError) as refused:
        verifier.verify(supa.token(key=secret, alg="HS256", sub=RAVI))
    assert refused.value.status == 401
    with pytest.raises(auth.AuthError):  # expired: refused before asking anyone
        verifier.verify(supa.token(key=secret, alg="HS256", exp_in=-600))
    assert len(asked) == 2


def test_supabase_unreachable_is_a_retry_not_a_sign_out(make_app, supa, monkeypatch):
    a, client, me, sid = signed_in(make_app, supa)

    def down(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("no route", request=request)

    monkeypatch.setattr(auth, "_verifier", auth.Verifier(
        URL, PUB, http=httpx.Client(transport=httpx.MockTransport(down))))
    answer = client.get("/api/cards", headers=me)
    assert answer.status_code == 503 and answer.json()["code"] == "auth_unavailable"


# --- personal tokens, the demo account ---------------------------------------------------------
def test_a_personal_token_is_shown_once_stored_hashed_and_good_for_mcp_only(make_app, supa):
    from seventy5.cloud import Router
    from seventy5.mcp_server import http_app

    a, client, me, sid = signed_in(make_app, supa)
    made = client.post("/api/me/token", headers=me).json()
    token = made["token"]
    assert token.startswith("75p_") and made["mcp_url"].endswith("/mcp")
    row = a.db.student(sid)
    assert row["token_hash"] == token_hash(token) and token not in json.dumps(dict(row))
    assert client.get("/api/me", headers=me).json()["profile"]["personal_token"]["exists"]
    # Not a key to the app's own API, nor to the account.
    assert client.get("/api/cards", headers=bearer(token)).status_code == 401
    assert client.post("/api/me/delete", headers=bearer(token),
                       json={"confirm": "DELETE"}).status_code == 401
    router = Router(core=None, portmax=None, portal=None)
    router.app = a
    router.mcp = http_app(lambda: router.app)
    mcp = TestClient(router)
    headers = bearer(token) | {"accept": "application/json, text/event-stream",
                               "content-type": "application/json"}
    rpc = {"jsonrpc": "2.0", "id": 1, "method": "initialize",
           "params": {"protocolVersion": "2025-06-18", "capabilities": {},
                      "clientInfo": {"name": "t", "version": "1"}}}
    assert mcp.post("/mcp", headers=headers, json=rpc).status_code == 200
    assert client.post("/api/me/token/delete", headers=me).json() == {"deleted": True}
    assert mcp.post("/mcp", headers=headers, json=rpc).status_code == 401


def test_the_demo_account_cannot_be_changed_linked_given_a_token_or_deleted(make_app, supa):
    a, sid = make_app()
    client = TestClient(create(a))
    shared = bearer(demo.TOKEN)
    assert client.get("/api/me", headers=shared).json()["demo"] is True
    for path, body in (("/api/me", {"name": "x"}), ("/api/me/token", {}),
                       ("/api/me/whatsapp", {}), ("/api/me/delete", {"confirm": "DELETE"}),
                       ("/api/google/start", {})):
        answer = client.post(path, headers=shared, json=body)
        assert answer.status_code == 403, path
        assert answer.json()["code"] == "demo_account", path
    assert client.get("/api/cards", headers=shared).status_code == 200


def test_only_the_demo_account_can_run_the_demo_tour(tmp_path, monkeypatch, supa):
    from mailfilter.store import Store as MailStore
    from portmax.store import Store

    from seventy5 import cloud, tools

    monkeypatch.setattr(tools, "_portal", Store(f"sqlite:///{tmp_path.as_posix()}/pm.db"))
    monkeypatch.setattr(mail, "_store", MailStore(f"sqlite:///{tmp_path.as_posix()}/mail.db"))
    monkeypatch.setattr(mail, "_demo", {})
    client = TestClient(cloud.build_router(str(tmp_path / "75.db")))
    me = bearer(supa.token())
    assert client.post("/api/me", headers=me, json={"username": "asha", "name": "Asha"}
                       ).status_code == 200
    for path in ("/demo/reset", "/demo/forward/quiz"):
        answer = client.post(path, headers=me)
        assert answer.status_code == 403 and "demo account" in answer.json()["detail"]
    assert client.post("/demo/reset", headers=bearer(demo.TOKEN)).json()["ok"]
    # PortMax answers to the same sign-in: Asha's token is Asha's portal, not the demo's.
    assert client.get("/v1/connectors/mockcollege", headers=me).status_code == 200
    assert client.get("/v1/connectors/mockcollege").status_code == 401


# --- WhatsApp ------------------------------------------------------------------------------------
def _bot(client, text: str, phone: str):
    body = json.dumps({"from": phone, "message_id": f"wamid.{time.time_ns()}",
                       "text": text}).encode()
    ts = int(time.time())
    return client.post("/bot/webhook", content=body,
                       headers={"x-75-timestamp": str(ts), "x-75-signature": sign(body, ts)})


def test_whatsapp_is_linked_by_a_code_the_bot_saw_come_from_that_number(make_app, supa):
    a, client, me, sid = signed_in(make_app, supa)
    start = client.post("/api/me/whatsapp", headers=me).json()
    code = start["code"]
    assert start["message"] == f"LINK {code}" and start["bot_number"] == "+919900000075"
    assert start["link"] == f"https://wa.me/919900000075?text=LINK%20{code}"
    # Unsigned or wrong: nothing happens.
    assert _bot(client, "LINK 75-ZZZZZZ", "919812345678").json()["linked"] is False
    linked = _bot(client, f"link {code.lower()}", "919812345678").json()
    assert linked["linked"] is True and "Linked" in linked["reply"]
    assert a.db.student(sid)["wa_phone"] == "919812345678"
    assert client.get("/api/me", headers=me).json()["profile"]["whatsapp"] == "+91 ••••• •5678"
    assert _bot(client, f"LINK {code}", "919800000001").json()["linked"] is False  # spent
    assert a.db.conn.execute("SELECT COUNT(*) AS n FROM events WHERE student_id=?",
                             (sid,)).fetchone()["n"] == 0  # a code is never filed as a message
    # Now the bot's forwards from that number are Asha's.
    _bot(client, "DBMS notes", "919812345678")
    assert a.db.conn.execute("SELECT COUNT(*) AS n FROM events WHERE student_id=?",
                             (sid,)).fetchone()["n"] == 1
    unlinked = client.post("/api/me/whatsapp/delete", headers=me).json()
    assert unlinked["profile"]["whatsapp"] is None


def test_a_link_code_expires_and_a_number_moves_to_whoever_proves_it(make_app, supa):
    a, client, me, sid = signed_in(make_app, supa)
    ravi = bearer(supa.token(sub=RAVI, email="ravi@example.com"))
    client.post("/api/me", headers=ravi, json={"username": "ravi", "name": "Ravi"})
    clock.freeze(at(2030, 1, 7, 10, 0))
    old = client.post("/api/me/whatsapp", headers=me).json()["code"]
    clock.freeze(at(2030, 1, 7, 10, 16))
    assert _bot(client, f"LINK {old}", "919812345678").json()["linked"] is False
    code = client.post("/api/me/whatsapp", headers=me).json()["code"]
    assert _bot(client, f"LINK {code}", "919812345678").json()["linked"] is True
    code = client.post("/api/me/whatsapp", headers=ravi).json()["code"]
    assert _bot(client, f"LINK {code}", "919812345678").json()["linked"] is True
    assert a.db.student(sid)["wa_phone"] is None
    assert a.db.student_by_auth(RAVI)["wa_phone"] == "919812345678"


# --- deleting an account --------------------------------------------------------------------------
def test_deleting_an_account_removes_every_row_and_the_login(make_app, supa):
    a, client, me, sid = signed_in(make_app, supa)
    item = file_item(a, sid)
    a.db.add_reminder(sid, item, "2030-01-04T22:59+05:30")
    a.db.add_device("phone-1", sid, "android", "x")
    a.db.add_notification(sid, "reminder", "t", "b", item, "x")
    client.post("/api/me/token", headers=me)
    demo_sid = demo.student_id(a.db)
    demo_items = len(a.db.all_cards(demo_sid))
    assert client.post("/api/me/delete", headers=me, json={}).status_code == 400  # not confirmed
    assert client.post("/api/me/delete", headers=me, json={"confirm": "DELETE"}).json() == {
        "deleted": True}
    assert supa.deleted == [ASHA]
    assert a.db.student(sid) is None
    for table in STUDENT_TABLES:
        left = a.db.conn.execute(f"SELECT COUNT(*) AS n FROM {table} WHERE student_id=?",
                                 (sid,)).fetchone()["n"]
        assert left == 0, table
    assert len(a.db.all_cards(demo_sid)) == demo_items  # no one else's rows
    # Signing in again (Supabase still had a session) is a fresh start, not the old account.
    assert client.get("/api/me", headers=me).json()["onboarded"] is False


def test_deleting_needs_the_secret_key_and_a_failed_login_removal_can_be_retried(
        make_app, supa, monkeypatch):
    a, client, me, sid = signed_in(make_app, supa)
    monkeypatch.setattr(auth, "settings", replace(auth.settings, supabase_secret_key=""))
    refused = client.post("/api/me/delete", headers=me, json={"confirm": "DELETE"})
    assert refused.status_code == 503 and a.db.student(sid) is not None  # nothing deleted
    monkeypatch.setattr(auth, "settings", replace(auth.settings, supabase_secret_key=SECRET))
    supa.delete_status = 500
    failed = client.post("/api/me/delete", headers=me, json={"confirm": "DELETE"})
    assert failed.status_code == 502 and a.db.student(sid) is None
    supa.delete_status = 404  # already gone at Supabase counts as removed
    assert client.post("/api/me/delete", headers=me, json={"confirm": "DELETE"}).json() == {
        "deleted": True}


# --- signing in with a username -------------------------------------------------------------------
def test_a_username_signs_in_without_revealing_who_has_an_account(make_app, supa):
    a, client, me, sid = signed_in(make_app, supa)
    good = client.post("/api/auth/login", json={"login": "Asha.K", "password": "correct horse"})
    assert good.status_code == 200 and good.json()["refresh_token"] == "r1"
    sent = [r for r in supa.requests if r.url.path == "/auth/v1/token"][-1]
    assert sent.headers["apikey"] == SECRET and sent.headers["sb-forwarded-for"]
    wrong = client.post("/api/auth/login", json={"login": "asha.k", "password": "nope"})
    nobody = client.post("/api/auth/login", json={"login": "nobody", "password": "nope"})
    assert wrong.status_code == nobody.status_code == 400
    assert wrong.json() == nobody.json() == {"detail": "Wrong username or password.",
                                            "code": "invalid_credentials"}
    tries = [client.post("/api/auth/login", json={"login": "asha.k", "password": "x"}).status_code
             for _ in range(10)]
    assert 429 in tries  # ten a few minutes, per address and per name


# --- the database, shared with every account -----------------------------------------------------
def test_reseeding_the_demo_touches_no_one_else_and_keeps_its_id(make_app, supa):
    a, client, me, sid = signed_in(make_app, supa)
    item = file_item(a, sid)
    demo_sid = demo.student_id(a.db)
    a.db.add_device("demo-phone", demo_sid, "android", "x")
    assert demo.seed(a) == demo_sid
    assert a.db.item(sid, item) is not None and a.db.student(sid)["name"] == "Asha K"
    assert a.db.device_tokens(demo_sid) == ["demo-phone"]  # its phones stay


def test_the_demo_morning_is_kept_for_the_day_then_refreshed(tmp_path, make_app):
    a, sid = make_app()
    clock.freeze(at(2030, 1, 7, 9, 0))
    demo.seed(a)
    assert demo.seeded_today(a.db)
    clock.freeze(at(2030, 1, 7, 23, 0))
    assert demo.seeded_today(a.db)
    clock.freeze(at(2030, 1, 8, 0, 5))
    assert not demo.seeded_today(a.db)


def test_the_demo_morning_never_lands_in_a_real_account_that_linked_its_number(make_app, supa):
    a, client, me, sid = signed_in(make_app, supa)
    code = client.post("/api/me/whatsapp", headers=me).json()["code"]
    assert _bot(client, f"LINK {code}", demo.PHONE).json()["linked"] is True
    demo_sid = demo.seed(a)
    assert a.db.student(demo_sid)["wa_phone"] is None
    assert a.db.student(sid)["wa_phone"] == demo.PHONE
    lines = demo.play(a, client, demo_sid)
    assert not any(line.startswith("whatsapp") for line in lines)
    assert a.db.conn.execute("SELECT COUNT(*) AS n FROM events WHERE student_id=?",
                             (sid,)).fetchone()["n"] == 0


def test_classmates_share_classroom_ids_but_each_gets_the_card(make_app):
    a, sid = make_app()
    other = a.db.create_student(name="B")
    first = a.db.insert_event(sid, "classroom:classroom:123", "classroom", {}, "x")
    second = a.db.insert_event(other, "classroom:classroom:123", "classroom", {}, "x")
    assert first and second and first != second
    assert a.db.insert_event(other, "classroom:classroom:123", "classroom", {}, "x") is None


def test_old_plain_tokens_are_kept_only_as_hashes(tmp_path):
    import sqlite3

    path = tmp_path / "old.db"
    raw = sqlite3.connect(path)
    raw.executescript("""
        CREATE TABLE students (id INTEGER PRIMARY KEY, name TEXT NOT NULL, wa_phone TEXT UNIQUE,
          mcp_token TEXT UNIQUE, branch TEXT, year INTEGER, interests TEXT, portal_id TEXT);
        INSERT INTO students(name, mcp_token) VALUES ('Old', 'old-token');
    """)
    raw.close()
    db = Database(str(path))
    row = db.student(1)
    assert row["mcp_token"] is None and row["token_hash"] == token_hash("old-token")
    assert db.student_by_token("old-token")["id"] == 1


def test_lambda_reads_parameter_store_before_choosing_tmp(monkeypatch):
    from seventy5 import lambda_demo

    for name in ("DATABASE_URL", "PORTMAX_DATABASE_URL", "MAILFILTER_DATABASE_URL", "CACHE_DIR"):
        monkeypatch.setenv(name, "set so that the test's own values are undone after it")
        monkeypatch.delenv(name)

    class Ssm:
        def get_parameters_by_path(self, **_):
            return {"Parameters": [{"Name": "/p/DATABASE_URL",
                                    "Value": "postgresql://postgres.ref:pw@pooler:6543/postgres"}]}

    assert lambda_demo.load_settings("/p", Ssm()) == ["DATABASE_URL"]
    lambda_demo.use_tmp_unless_supabase()
    assert os.environ["DATABASE_URL"].startswith("postgresql://")
    assert "PORTMAX_DATABASE_URL" not in os.environ and os.environ["CACHE_DIR"] == "/tmp/cache"
    monkeypatch.delenv("DATABASE_URL")
    lambda_demo.use_tmp_unless_supabase()
    assert os.environ["DATABASE_URL"] == "/tmp/75.db"
    assert os.environ["PORTMAX_DATABASE_URL"] == "sqlite:////tmp/portmax.db"


def test_postgres_settings_are_pooler_safe():
    from seventy5.db import pg_options, sqlalchemy_url

    remote = pg_options("postgresql://postgres.ref:pw@aws-0-ap-south-1.pooler.supabase.com:6543/x")
    assert remote["prepare_threshold"] is None and remote["sslmode"] == "require"
    assert "sslmode" not in pg_options("postgresql://postgres:pw@127.0.0.1:5432/x")
    given = pg_options("postgresql://u:p@db.example.com:5432/x?sslmode=verify-full")
    assert "sslmode" not in given  # the URL's own choice stands
    assert sqlalchemy_url("postgres://u:p@h/db") == "postgresql+psycopg://u:p@h/db"
    assert sqlalchemy_url("sqlite:///x.db") == "sqlite:///x.db"


# --- on a real Postgres (PG_TEST_URL), the way Supabase runs it -------------------------------
PG = os.environ.get("PG_TEST_URL", "")
needs_pg = pytest.mark.skipif(not PG.startswith("postgres"), reason="set PG_TEST_URL")


@needs_pg
def test_supabase_tables_are_closed_to_its_data_api(make_app):
    import psycopg

    from mailfilter.store import metadata as mail_tables
    from portmax.store import metadata as portal_tables

    from seventy5.cloud import lock_down_all
    from seventy5.db import CORE_TABLES, lock_down, open_store

    from mailfilter.store import Store as MailStore
    from portmax.store import Store as PortalStore

    a, _ = make_app()
    open_store(PortalStore, PG, portal_tables)
    open_store(MailStore, PG, mail_tables)
    with psycopg.connect(PG, autocommit=True) as c:
        for role in ("anon", "authenticated"):
            c.execute(f"GRANT ALL ON ALL TABLES IN SCHEMA public TO {role}")
            c.execute(f"GRANT ALL ON ALL SEQUENCES IN SCHEMA public TO {role}")
    lock_down_all(a.db)
    everything = [*CORE_TABLES, *portal_tables.tables, *mail_tables.tables]
    with psycopg.connect(PG, autocommit=True) as c:
        rows = c.execute("SELECT relname, relrowsecurity FROM pg_class c JOIN pg_namespace n"
                         " ON n.oid=c.relnamespace WHERE n.nspname='public' AND relkind='r'"
                         " AND relname = ANY(%s)", ([*portal_tables.tables, *mail_tables.tables,
                                                     "students", "items", "events"],)).fetchall()
        assert len(rows) == len(portal_tables.tables) + len(mail_tables.tables) + 3
        assert all(rls for _, rls in rows)
        for name, _ in rows:
            for role in ("anon", "authenticated"):
                assert not c.execute("SELECT has_table_privilege(%s, %s, 'SELECT')",
                                     (role, f"public.{name}")).fetchone()[0], (role, name)
    assert lock_down(a.db.conn, everything) == []  # a second start has nothing to change
    with psycopg.connect(PG, autocommit=True) as c:
        assert not c.execute("SELECT has_sequence_privilege('anon', 'public.items_id_seq', 'USAGE')"
                             ).fetchone()[0]


@needs_pg
def test_a_connection_dropped_while_idle_is_replaced_before_use(make_app):
    import socket

    from seventy5 import db as db_module

    a, sid = make_app()
    old = a.db.conn.raw
    # The network drops the connection while nothing uses it (a frozen Lambda, the pooler).
    dropped = socket.socket(fileno=os.dup(old.fileno()))
    dropped.shutdown(socket.SHUT_RDWR)
    dropped.close()
    a.db.conn._used -= db_module.IDLE_CHECK_SECONDS + 1
    assert a.db.student(sid)["name"] == "Demo Student"
    assert a.db.conn.raw is not old and old.closed


@needs_pg
def test_the_portal_and_mail_stores_survive_a_transaction_pooler():
    from portmax.store import Store as PortalStore
    from portmax.store import metadata as portal_tables

    from seventy5.db import open_store

    one = open_store(PortalStore, PG, portal_tables)
    two = open_store(PortalStore, PG, portal_tables)
    now = clock.now()
    for i in range(12):  # two engines interleaving: prepared statements would collide here
        for store in (one, two):
            store.save_answers(f"pool-{i % 3}", "mockcollege", "1.0.0", now,
                               {"get_attendance": [], "get_timetable": []})
    assert one.engine.dialect.driver == "psycopg"


def test_a_new_student_gets_the_portal_subjects_without_typing_them(make_app, supa):
    from importlib.resources import files

    from seventy5 import tools

    a, client, me, sid = signed_in(make_app, supa, {"subjects": ["Operating Systems"]})
    assert tools.subjects(a.db, sid) == ["Operating Systems"]  # no portal yet
    golden = files("portmax.connectors.mockcollege") / "golden"
    answers = {tool: json.loads((golden / f"{tool}.json").read_text(encoding="utf-8"))
               for tool in ("get_attendance", "get_timetable")}
    tools.portal_store().save_answers(a.db.student(sid)["portal_id"], "mockcollege", "1.0.0",
                                      clock.now(), answers)
    merged = tools.subjects(a.db, sid)
    assert merged[0] == "Operating Systems" and set(demo.SUBJECTS) <= set(merged)
    assert len(merged) == len({m.lower() for m in merged})  # no subject twice
