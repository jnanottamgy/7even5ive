"""The contract between this server and the app: every answer the app reads, as the server really
sends it, kept with the app's tests (android/app/src/test/resources/contract/*.json).

The app's ContractTest serves these answers back to its own CoreApi. It checks that each request
it makes is the one recorded here, and that each answer decodes into its models with nothing it
reads missing. This test keeps the files honest. It replays the demo morning on the production
router (the one Lambda runs), on a fixed clock, makes every request again, and checks that every
field in the files is still sent with the same type. A new field is fine, because the app
ignores what it doesn't know. A field removed, renamed or retyped fails here, before it fails
on a phone.

When an answer changes on purpose, run UPDATE_CONTRACT=1 pytest tests/test_contract.py, then
run the app's tests (./gradlew testDebugUnitTest) and commit both.
"""

from __future__ import annotations

import json
import os
import sys
from dataclasses import replace
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlsplit

import httpx
import pytest
from conftest import at
from fastapi.testclient import TestClient
from test_accounts import ASHA, PUB, SECRET, URL, FakeSupabase
from test_mail_google import FakeGoogle

CONTRACT = (Path(__file__).resolve().parents[2]
            / "android" / "app" / "src" / "test" / "resources" / "contract")
UPDATE = os.environ.get("UPDATE_CONTRACT") == "1"
JSON = "application/json; charset=utf-8"  # what the app's Http sends its bodies as


# --- the shape of an answer -------------------------------------------------------------------
def shape(value: Any, path: str = "$", out: dict[str, set[str]] | None = None) -> dict[str, set[str]]:
    """Every key path in an answer with the JSON types seen there. A list's items share one
    path (`$.due_this_week[]`), so a field any item carries counts."""
    out = {} if out is None else out
    kind = ("null" if value is None else "boolean" if isinstance(value, bool)
            else "number" if isinstance(value, (int, float)) else "string" if isinstance(value, str)
            else "array" if isinstance(value, list) else "object")
    out.setdefault(path, set()).add(kind)
    if isinstance(value, dict):
        for key, child in value.items():
            shape(child, f"{path}.{key}", out)
    elif isinstance(value, list):
        for child in value:
            shape(child, f"{path}[]", out)
    return out


def drift(kept: Any, now: Any) -> list[str]:
    """What the app was tested against that the server no longer sends the same way. A field
    that is null on one side is fine (that is data); a field gone, or of another type, is not."""
    before, after = shape(kept), shape(now)
    problems = []
    for path, kinds in sorted(before.items()):
        if path not in after:
            problems.append(f"{path} is no longer sent")
            continue
        was, now_ = kinds - {"null"}, after[path] - {"null"}
        if was and now_ and not was & now_:
            problems.append(f"{path} was {'/'.join(sorted(was))}, is now {'/'.join(sorted(now_))}")
    return problems


def test_drift_sees_a_rename_and_a_retype_but_not_a_new_field_or_a_null():
    kept = {"items": [{"id": 1, "title": "A", "due_at": "2030-01-07"}], "count": 1}
    assert drift(kept, {"items": [{"id": 1, "title": "A", "due_at": None, "new": 2}],
                        "count": 1, "extra": True}) == []
    assert drift(kept, {"items": [{"id": "1", "name": "A", "due_at": "x"}], "count": 1}) == [
        "$.items[].id was number, is now string", "$.items[].title is no longer sent"]


# --- the server, as it runs online ------------------------------------------------------------
@pytest.fixture
def online(tmp_path, monkeypatch):
    """The production router on a fixed Monday morning, with Supabase, Google and ElevenLabs
    faked at their edges, and every module reading the same settings."""
    from mailfilter.store import Store as MailStore
    from portmax.store import Store

    from seventy5 import api as api_module
    from seventy5 import auth, clock, cloud, config, google, mail, tools

    clock.freeze(at(2030, 1, 7, 8, 30))
    original = config.settings
    on = replace(original, supabase_url=URL, supabase_publishable_key=PUB,
                 supabase_secret_key=SECRET, bot_whatsapp_number="919900000075",
                 bot_secret="the-bots-own-secret",
                 portmax_database_url=f"sqlite:///{tmp_path.as_posix()}/pm-api.db",
                 elevenlabs_api_key="xi", elevenlabs_assistant_agent_id="agent_va",
                 elevenlabs_api="https://api.elevenlabs.io",
                 demo_student_phone="919812345678",  # invented; calls are only logged here
                 google_client_id="cid.apps.googleusercontent.com",
                 google_client_secret="secret", token_encryption_key="", public_url="")
    monkeypatch.setattr(config, "settings", on)
    for name, module in list(sys.modules.items()):
        if name.startswith("seventy5.") and getattr(module, "settings", None) is original:
            monkeypatch.setattr(module, "settings", on)

    supabase = FakeSupabase()
    monkeypatch.setattr(auth, "_client", supabase.client)
    monkeypatch.setattr(auth, "_verifier", None)
    monkeypatch.setattr(google, "_http", FakeGoogle().client)
    monkeypatch.setattr(google, "_tokens", google._Tokens())
    monkeypatch.setattr(tools, "_portal", Store(f"sqlite:///{tmp_path.as_posix()}/pm.db"))
    monkeypatch.setattr(mail, "_store", MailStore(f"sqlite:///{tmp_path.as_posix()}/mail.db"))
    monkeypatch.setattr(mail, "_demo", {})
    for name in ("_ask_by_student", "_share_by_student", "_demo_ask_by_ip", "_demo_share_by_ip",
                 "_demo_voice_by_ip", "_demo_audio_by_ip", "_username_checks", "_login_by_ip",
                 "_login_by_name"):
        monkeypatch.setattr(getattr(api_module, name), "_hits", {})
    router = cloud.build_router(str(tmp_path / "75.db"))
    yield router, TestClient(router), supabase
    clock.freeze(None)


class Recorder:
    """Makes each request the way the app makes it, and keeps what came back."""

    def __init__(self, client: TestClient, account: dict[str, str]) -> None:
        from seventy5 import demo

        self.client = client
        self.headers = {"none": {}, "demo": {"authorization": f"Bearer {demo.TOKEN}"},
                        "account": account}
        self.answers: dict[str, dict[str, Any]] = {}

    def __call__(self, name: str, method: str, path: str, body: Any = None, who: str = "demo",
                 status: int = 200) -> Any:
        headers = self.headers[who] | ({} if body is None else {"content-type": JSON})
        r = self.client.request(method, path, headers=headers,
                                content=None if body is None else json.dumps(body))
        assert r.status_code == status, f"{name}: {r.status_code} {r.text[:400]}"
        request: dict[str, Any] = {"method": method, "path": path, "auth": who}
        if body is not None:
            request["body"] = body
        answer = r.json()
        self.answers[name] = {"request": request, "status": r.status_code, "response": answer}
        return answer


def record_everything(router: Any, client: TestClient, supabase: FakeSupabase) -> dict[str, Any]:
    from seventy5 import clock, demo, notify, voice

    rec = Recorder(client, {"authorization": f"Bearer {supabase.token()}"})

    # What every screen reads, as the demo student.
    rec("auth_config", "GET", "/api/auth/config", who="none")
    cards = rec("cards", "GET", "/api/cards")
    rec("briefing", "GET", "/api/briefing")
    rec("settings", "GET", "/api/settings")
    tree = rec("tool_list_library", "POST", "/api/tools/list_library", {"args": {}})
    subject, shelf = next((s, shelf) for s in tree["result"]["subjects"]
                          for shelf in s["shelves"] if shelf["files"])
    page = rec("tool_list_library_files", "POST", "/api/tools/list_library_files",
               {"args": {"subject_id": subject["id"], "shelf": shelf["shelf"], "offset": 0}})
    rec("tool_open_file", "POST", "/api/tools/open_file",
        {"args": {"file_id": page["result"]["files"][0]["id"]}})
    note = next(f for s in tree["result"]["subjects"] for shelf in s["shelves"] if shelf["files"]
                for f in client.post("/api/tools/list_library_files", headers=rec.headers["demo"],
                                     json={"args": {"subject_id": s["id"], "shelf": shelf["shelf"],
                                                    "offset": 0}}).json()["result"]["files"]
                if f["kind"] == "note")
    rec("tool_open_note", "POST", "/api/tools/open_file", {"args": {"file_id": note["id"]}})
    rec("ask", "POST", "/api/ask", {"question": "What's due this week?"})

    real = httpx.Client
    signed = {"signed_url": "wss://api.elevenlabs.io/v1/convai/conversation?conversation_signature=s1"}
    voice_http = pytest.MonkeyPatch()
    voice_http.setattr(voice.httpx, "Client", lambda **kw: real(
        transport=httpx.MockTransport(lambda r: httpx.Response(200, json=signed))))
    try:
        rec("voice_session", "GET", "/api/voice/session")
    finally:
        voice_http.undo()
    no_voice = pytest.MonkeyPatch()  # a server without ElevenLabs says why
    no_voice.setattr(voice, "settings", replace(voice.settings, elevenlabs_api_key=""))
    try:
        rec("voice_unavailable", "GET", "/api/voice/session")
    finally:
        no_voice.undo()

    # What a tap changes.
    item = max(cards["due_this_week"], key=lambda c: c["due_at"] or "")["id"]  # the furthest out
    reminder = rec("tool_set_reminder", "POST", "/api/tools/set_reminder",
                   {"args": {"item_id": item, "before_minutes": 60, "channel": "push"}})
    rec("tool_mark_done", "POST", "/api/tools/mark_done", {"args": {"item_id": item}})
    rec("tool_reopen", "POST", "/api/tools/reopen", {"args": {"item_id": item}})
    rec("tool_add_to_calendar", "POST", "/api/tools/add_to_calendar", {"args": {"item_id": item}})
    rec("share", "POST", "/api/share",
        {"text": "DBMS assignment 4, due Friday 11:59 pm", "kind": "deadline",
         "subject": "Database Management Systems", "title": "DBMS assignment 4",
         "due_at": "2030-01-11T23:59+05:30"})
    rec("share_unsorted", "POST", "/api/share", {"text": "Notice: the library closes early today"})
    rec("call_settings", "POST", "/api/settings/calls", {"enabled": True})
    rec("call_test", "POST", "/api/calls/test", {})
    rec("call_quiet", "POST", "/api/settings/calls", {"quiet_start": "08:00", "quiet_end": "09:00"})
    rec("call_test_refused", "POST", "/api/calls/test", {})
    rec("calls", "GET", "/api/calls")
    clock.freeze(at(2030, 1, 7, 8, 45))  # "Check now" waits five minutes after the last check
    rec("mail_check", "POST", "/api/mail/check", {})
    rec("demo_forward", "POST", "/demo/forward/quiz", {})
    # The same screens once the student has done things: a reminder set, an approval waiting,
    # something to sort, the AI log, what 7even5ive has sent.
    rec("cards_busy", "GET", "/api/cards")
    rec("tool_cancel_reminder", "POST", "/api/tools/cancel_reminder",
        {"args": {"reminder_id": reminder["result"]["reminder_id"]}})
    # A reminder that fires: the reminders job writes it to the outbox the phone pulls.
    soon = sorted(cards["due_this_week"], key=lambda c: c["due_at"] or "")[-2]["id"]
    fires = client.post("/api/tools/set_reminder", headers=rec.headers["demo"],
                        json={"args": {"item_id": soon, "before_minutes": 60}}).json()
    clock.freeze(datetime.fromisoformat(fires["result"]["fires_at"]) + timedelta(minutes=1))
    assert notify.fire_due(router.app.db, router.app.sender, router.app.caller) == 1
    rec("notifications", "GET", "/api/notifications?after=0")

    # Errors the app acts on: the detail said as it is, the code telling it what to do.
    rec("error_demo_account", "POST", "/api/me", {"name": "Not the demo"}, status=403)
    rec("error_demo_google", "POST", "/api/google/start", {}, status=403)

    # A signed-in student's own account.
    rec("username_check", "GET", "/api/auth/username?u=asha.k", who="none")
    profile = {"username": "asha.k", "name": "Asha K", "branch": "CSE", "year": 3,
               "subjects": ["Operating Systems", "Computer Networks"]}
    rec("me_save", "POST", "/api/me", profile, who="account")
    rec("me", "GET", "/api/me", who="account")
    rec("me_token", "POST", "/api/me/token", {}, who="account")
    sid = int(router.app.db.student_by_auth(ASHA)["id"])
    with router.app.db.tx() as c:  # an AI app that signed in through the MCP connector
        c.execute("INSERT INTO oauth_grants(student_id, client_id, client_name, access_hash,"
                  " access_expires_at, refresh_hash, refresh_expires_at, scopes, resource,"
                  " created_at, last_used_at) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                  (sid, "client-1", "Claude Code", "a" * 64, 0, "r" * 64, 0, "mcp", None,
                   clock.iso(clock.now()), clock.iso(clock.now())))
    connected = rec("me_connections", "GET", "/api/me/connections", who="account")
    rec("me_disconnect", "POST", f"/api/me/connections/{connected['connections'][0]['id']}/delete",
        {}, who="account")
    rec("me_whatsapp", "POST", "/api/me/whatsapp", {}, who="account")
    rec("me_whatsapp_delete", "POST", "/api/me/whatsapp/delete", {}, who="account")
    # Files come from the WhatsApp bot: without it, the Files tab says why (and nothing breaks).
    rec("tool_list_library_unavailable", "POST", "/api/tools/list_library", {"args": {}},
        who="account")
    rec("tool_list_library_files_unavailable", "POST", "/api/tools/list_library_files",
        {"args": {"subject_id": 1, "shelf": "material", "offset": 0}}, who="account")
    rec("tool_open_file_unavailable", "POST", "/api/tools/open_file", {"args": {"file_id": 101}},
        who="account")

    # Google, for a student's own account: the consent page, the app finishing with the code
    # Google's page handed back, then disconnecting.
    start = rec("google_start", "POST", "/api/google/start", {}, who="account")
    state = parse_qs(urlsplit(start["url"]).query)["state"][0]
    assert client.get(f"/api/google/callback?code=4/abc&state={state}").status_code == 200
    rec("google_finish", "POST", "/api/google/finish", {"code": "4/abc", "state": state},
        who="account")
    rec("google_disconnect", "POST", "/api/google/disconnect", {}, who="account")
    assert demo.is_demo(router.app.db, demo.student_id(router.app.db))
    return rec.answers


def scrub(answers: dict[str, Any]) -> dict[str, Any]:
    """The random values (tokens, the OAuth state and challenge, the WhatsApp code) as fixed
    stand-ins, so the files change only when an answer does, and nothing in them looks like a
    live secret."""
    consent = parse_qs(urlsplit(answers["google_start"]["response"]["url"]).query)
    swaps = {answers["me_token"]["response"]["token"]: "75p_contract-test-token",
             consent["state"][0]: "contract-test-state",
             consent["code_challenge"][0]: "contract-test-challenge",
             answers["me_whatsapp"]["response"]["code"]: "75-TEST01"}
    for i, approval in enumerate(answers["cards_busy"]["response"]["approvals"], 1):
        swaps[approval["token"]] = f"approval-token-{i}"
    text = json.dumps(answers, ensure_ascii=False)
    for real, stand_in in swaps.items():
        text = text.replace(real, stand_in)
    return json.loads(text)


def test_the_app_reads_what_the_server_sends(online):
    router, client, supabase = online
    answers = scrub(record_everything(router, client, supabase))
    if UPDATE:
        CONTRACT.mkdir(parents=True, exist_ok=True)
        for stale in {p.stem for p in CONTRACT.glob("*.json")} - set(answers):
            (CONTRACT / f"{stale}.json").unlink()
        for name, answer in answers.items():
            (CONTRACT / f"{name}.json").write_text(
                json.dumps(answer, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        return
    if not CONTRACT.is_dir():
        pytest.skip("the app isn't checked out next to the core")
    kept = {p.stem: json.loads(p.read_text(encoding="utf-8")) for p in CONTRACT.glob("*.json")}
    assert sorted(kept) == sorted(answers), \
        "the recorded answers and the files differ: run with UPDATE_CONTRACT=1"
    problems = []
    for name, answer in answers.items():
        was = kept[name]
        if (was["request"]["method"], was["status"]) != (answer["request"]["method"], answer["status"]):
            problems.append(f"{name}: was {was['request']['method']} -> {was['status']},"
                            f" is now {answer['request']['method']} -> {answer['status']}")
        problems += [f"{name} request: {p}" for p in drift(was["request"], answer["request"])]
        problems += [f"{name}: {p}" for p in drift(was["response"], answer["response"])]
    assert not problems, "the server no longer sends what the app reads:\n" + "\n".join(problems)
