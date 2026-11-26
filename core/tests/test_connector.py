"""The MCP connector (connector.py): Claude Code and Codex sign in as the student with OAuth,
in the browser, and get MCP and nothing else."""

from __future__ import annotations

import base64
import hashlib
import json
import secrets
from urllib.parse import parse_qs, urlparse

import pytest
from fastapi.testclient import TestClient

from seventy5 import connector
from seventy5.api import create
from seventy5.cloud import Router
from seventy5.connector import oauth_app
from seventy5.db import token_hash
from seventy5.mcp_server import http_app
from test_accounts import RAVI, bearer, signed_in, supa  # noqa: F401 (supa is a fixture)

BASE = "http://localhost"
REDIRECT = "http://127.0.0.1:53682/callback"
MCP_HEADERS = {"accept": "application/json, text/event-stream", "content-type": "application/json"}


@pytest.fixture
def setup(make_app, supa, monkeypatch):
    """(app, web client for every path, Asha's app headers, Asha's student id, router)."""
    a, _, me, sid = signed_in(make_app, supa)
    router = Router(core=create(a), portmax=None, portal=None)
    router.app = a
    router.mcp = http_app(lambda: router.app)
    router.connector = oauth_app(lambda: router.app)
    for limiter in (connector._registrations, connector._authorizations):
        monkeypatch.setattr(limiter, "_hits", {})
    web = TestClient(router, base_url=BASE, follow_redirects=False)
    return a, web, me, sid, router


def pkce() -> tuple[str, str]:
    verifier = secrets.token_urlsafe(48)
    digest = hashlib.sha256(verifier.encode()).digest()
    return verifier, base64.urlsafe_b64encode(digest).decode().rstrip("=")


def register(web, redirect: str = REDIRECT, **extra):
    return web.post("/oauth/register", json={
        "client_name": "Claude Code", "redirect_uris": [redirect],
        "token_endpoint_auth_method": "none", "grant_types": ["authorization_code", "refresh_token"],
        "response_types": ["code"]} | extra)


def start(web, client_id: str, challenge: str, resource: str = f"{BASE}/mcp"):
    return web.get("/oauth/authorize", params={
        "response_type": "code", "client_id": client_id, "redirect_uri": REDIRECT,
        "code_challenge": challenge, "code_challenge_method": "S256", "state": "st-1",
        "scope": "mcp", "resource": resource})


def request_id(location: str) -> str:
    return parse_qs(urlparse(location).query)["request"][0]


def sign_in(web, location: str, login: str = "asha.k", password: str = "correct horse",
            decision: str = "allow"):
    return web.post("/oauth/login", data={"request": request_id(location), "login": login,
                                          "password": password, "decision": decision})


def code_from(reply) -> str:
    assert reply.status_code == 302, reply.text
    back = parse_qs(urlparse(reply.headers["location"]).query)
    assert reply.headers["location"].startswith(REDIRECT) and back["state"] == ["st-1"]
    return back["code"][0]


def trade(web, client_id: str, code: str, verifier: str):
    return web.post("/oauth/token", data={
        "grant_type": "authorization_code", "code": code, "redirect_uri": REDIRECT,
        "client_id": client_id, "code_verifier": verifier, "resource": f"{BASE}/mcp"})


def connect(web) -> tuple[str, dict]:
    """The whole sign-in, as Claude Code or Codex does it. (client_id, tokens)."""
    client_id = register(web).json()["client_id"]
    verifier, challenge = pkce()
    location = start(web, client_id, challenge).headers["location"]
    tokens = trade(web, client_id, code_from(sign_in(web, location)), verifier)
    assert tokens.status_code == 200, tokens.text
    return client_id, tokens.json()


def rpc(web, token: str, method: str, params: dict | None = None):
    body = {"jsonrpc": "2.0", "id": 1, "method": method, "params": params or {}}
    return web.post("/mcp", content=json.dumps(body),
                    headers=MCP_HEADERS | {"authorization": f"Bearer {token}"})


# --- finding the way in --------------------------------------------------------------------------
def test_mcp_tells_an_app_where_to_sign_in(setup):
    _, web, _, _, _ = setup
    refused = web.post("/mcp", content="{}", headers=MCP_HEADERS)
    assert refused.status_code == 401
    challenge = refused.headers["www-authenticate"]
    assert challenge.startswith("Bearer ") and 'scope="mcp"' in challenge
    assert f'resource_metadata="{BASE}/.well-known/oauth-protected-resource/mcp"' in challenge
    assert "invalid_token" not in challenge  # no token was sent
    assert 'error="invalid_token"' in rpc(web, "75a_nope", "tools/list").headers["www-authenticate"]

    for path in ("/.well-known/oauth-protected-resource/mcp", "/.well-known/oauth-protected-resource"):
        resource = web.get(path).json()
        assert resource["resource"] == f"{BASE}/mcp" and resource["authorization_servers"] == [BASE]
    meta = web.get("/.well-known/oauth-authorization-server").json()
    assert meta["issuer"] == BASE  # exactly what the resource metadata names
    assert meta["authorization_endpoint"] == f"{BASE}/oauth/authorize"
    assert meta["token_endpoint"] == f"{BASE}/oauth/token"
    assert meta["registration_endpoint"] == f"{BASE}/oauth/register"
    assert meta["code_challenge_methods_supported"] == ["S256"]
    assert "none" in meta["token_endpoint_auth_methods_supported"]


# --- connecting ------------------------------------------------------------------------------------
def test_a_student_connects_claude_code_by_signing_in(setup):
    a, web, me, sid, _ = setup
    client_id = register(web).json()["client_id"]
    verifier, challenge = pkce()
    location = start(web, client_id, challenge).headers["location"]
    assert location.startswith(f"{BASE}/oauth/login?request=")
    shown = web.get(location)
    assert shown.status_code == 200
    assert "Claude Code" in shown.text and "this computer (127.0.0.1:53682)" in shown.text
    tokens = trade(web, client_id, code_from(sign_in(web, location)), verifier).json()
    assert tokens["token_type"] == "Bearer" and tokens["expires_in"] == 3600
    assert tokens["access_token"].startswith("75a_") and tokens["refresh_token"].startswith("75r_")

    # Only hashes are kept.
    rows = a.db.conn.execute("SELECT * FROM oauth_grants").fetchall()
    assert len(rows) == 1 and rows[0]["student_id"] == sid
    assert rows[0]["access_hash"] == token_hash(tokens["access_token"])
    assert tokens["access_token"] not in json.dumps([dict(r) for r in rows])

    listed = rpc(web, tokens["access_token"], "tools/list")
    assert listed.status_code == 200 and "due_this_week" in listed.text
    answer = rpc(web, tokens["access_token"], "tools/call",
                 {"name": "list_reminders", "arguments": {}})
    assert answer.status_code == 200 and '"status": "ok"' in answer.json()["result"]["content"][0]["text"]

    shown = web.get("/api/me/connections", headers=me).json()
    assert shown["mcp_url"] == f"{BASE}/mcp"
    [app] = shown["connections"]
    assert app["name"] == "Claude Code" and app["connected_at"] and app["last_used_at"]


def test_a_student_can_sign_in_with_their_email_in_any_case(setup):
    _, web, _, _, _ = setup
    client_id = register(web).json()["client_id"]
    verifier, challenge = pkce()
    location = start(web, client_id, challenge).headers["location"]
    code = code_from(sign_in(web, location, login="Asha@Example.com"))
    assert trade(web, client_id, code, verifier).status_code == 200


def test_connector_tokens_reach_mcp_and_nothing_else(setup):
    _, web, _, _, _ = setup
    _, tokens = connect(web)
    for path in ("/api/cards", "/api/me", "/api/settings"):
        refused = web.get(path, headers=bearer(tokens["access_token"]))
        assert refused.status_code == 401, path
    assert web.get("/api/me", headers=bearer(tokens["refresh_token"])).status_code == 401


def test_a_wrong_password_and_an_unknown_name_read_the_same(setup):
    a, web, _, _, _ = setup
    client_id = register(web).json()["client_id"]
    _, challenge = pkce()
    location = start(web, client_id, challenge).headers["location"]
    for login, password in (("asha.k", "wrong"), ("nobody.here", "correct horse"),
                            ("asha.k", "x" * 5000)):
        reply = sign_in(web, location, login=login, password=password)
        assert reply.status_code == 400 and "Wrong email, username or password." in reply.text
    assert a.db.conn.execute("SELECT COUNT(*) AS n FROM oauth_codes").fetchone()["n"] == 0


def test_a_profile_is_needed_before_an_app_can_connect(setup, supa):
    _, web, _, _, _ = setup
    supa.passwords["ravi@example.com"] = "pw for ravi"
    supa.token = lambda **kw: type(supa).token(supa, sub=RAVI, email="ravi@example.com")
    client_id = register(web).json()["client_id"]
    _, challenge = pkce()
    location = start(web, client_id, challenge).headers["location"]
    reply = sign_in(web, location, login="ravi@example.com", password="pw for ravi")
    assert reply.status_code == 400 and "Finish setting up your account" in reply.text


def test_cancel_sends_the_app_away_with_nothing(setup):
    _, web, _, _, _ = setup
    client_id = register(web).json()["client_id"]
    _, challenge = pkce()
    location = start(web, client_id, challenge).headers["location"]
    reply = sign_in(web, location, password="", decision="cancel")
    back = parse_qs(urlparse(reply.headers["location"]).query)
    assert reply.status_code == 302 and back["error"] == ["access_denied"]
    assert back["state"] == ["st-1"] and "code" not in back
    assert sign_in(web, location).status_code == 400  # the request is spent


# --- codes and tokens ------------------------------------------------------------------------------
def test_a_code_works_once_and_only_with_its_verifier(setup):
    _, web, _, _, _ = setup
    client_id = register(web).json()["client_id"]
    verifier, challenge = pkce()
    code = code_from(sign_in(web, start(web, client_id, challenge).headers["location"]))
    assert trade(web, client_id, code, "not-the-verifier-" + "x" * 30).status_code == 400
    assert trade(web, client_id, code, verifier).status_code == 200
    again = trade(web, client_id, code, verifier)
    assert again.status_code == 400 and again.json()["error"] == "invalid_grant"

    other = register(web).json()["client_id"]  # another app can't spend this app's code
    verifier, challenge = pkce()
    code = code_from(sign_in(web, start(web, client_id, challenge).headers["location"]))
    assert trade(web, other, code, verifier).status_code in (400, 401)


def test_a_sign_in_request_is_spent_by_its_first_use(setup):
    _, web, _, _, _ = setup
    client_id = register(web).json()["client_id"]
    _, challenge = pkce()
    location = start(web, client_id, challenge).headers["location"]
    code_from(sign_in(web, location))
    second = sign_in(web, location)
    assert second.status_code == 400 and "expired" in second.text
    assert web.get(location).status_code == 400


def test_refreshing_replaces_both_tokens(setup):
    _, web, _, _, _ = setup
    client_id, tokens = connect(web)
    fresh = web.post("/oauth/token", data={"grant_type": "refresh_token", "client_id": client_id,
                                           "refresh_token": tokens["refresh_token"]})
    assert fresh.status_code == 200, fresh.text
    new = fresh.json()
    assert new["access_token"] != tokens["access_token"]
    assert new["refresh_token"] != tokens["refresh_token"]
    assert rpc(web, tokens["access_token"], "tools/list").status_code == 401
    assert rpc(web, new["access_token"], "tools/list").status_code == 200
    reuse = web.post("/oauth/token", data={"grant_type": "refresh_token", "client_id": client_id,
                                           "refresh_token": tokens["refresh_token"]})
    assert reuse.status_code == 400 and reuse.json()["error"] == "invalid_grant"


def test_an_app_can_sign_itself_out(setup):
    _, web, _, _, _ = setup
    client_id, tokens = connect(web)
    # The SDK's handler wants client_secret present, empty for an app that has none.
    out = web.post("/oauth/revoke", data={"token": tokens["refresh_token"], "client_id": client_id,
                                          "client_secret": ""})
    assert out.status_code == 200
    assert rpc(web, tokens["access_token"], "tools/list").status_code == 401


def test_disconnecting_in_the_app_ends_that_apps_access(setup, make_app, supa):
    a, web, me, sid, _ = setup
    client_id, tokens = connect(web)
    [app] = web.get("/api/me/connections", headers=me).json()["connections"]
    assert web.post(f"/api/me/connections/{app['id']}/delete", headers=me).json() == {"deleted": True}
    assert rpc(web, tokens["access_token"], "tools/list").status_code == 401
    refresh = web.post("/oauth/token", data={"grant_type": "refresh_token", "client_id": client_id,
                                             "refresh_token": tokens["refresh_token"]})
    assert refresh.status_code == 400
    assert web.post(f"/api/me/connections/{app['id']}/delete", headers=me).status_code == 404
    assert web.get("/api/me/connections", headers=me).json()["connections"] == []
    assert web.get("/api/me/connections",
                   headers=bearer("demo-student-token")).json()["connections"] == []


def test_one_student_cannot_disconnect_anothers_app(setup, supa):
    a, web, me, sid, _ = setup
    connect(web)
    [app] = web.get("/api/me/connections", headers=me).json()["connections"]
    demo = bearer("demo-student-token")
    assert web.post(f"/api/me/connections/{app['id']}/delete", headers=demo).status_code == 404
    assert len(web.get("/api/me/connections", headers=me).json()["connections"]) == 1


def test_deleting_the_account_disconnects_every_app(setup):
    a, web, me, sid, _ = setup
    _, tokens = connect(web)
    assert web.post("/api/me/delete", headers=me, json={"confirm": "DELETE"}).status_code == 200
    assert rpc(web, tokens["access_token"], "tools/list").status_code == 401
    assert a.db.conn.execute("SELECT COUNT(*) AS n FROM oauth_grants").fetchone()["n"] == 0


# --- what an app may ask for -----------------------------------------------------------------------
@pytest.mark.parametrize("redirect, ok", [
    ("http://127.0.0.1:53682/callback", True),
    ("http://localhost:8976/callback", True),
    ("http://[::1]:8976/callback", True),
    ("https://claude.ai/api/mcp/auth_callback", True),
    ("cursor://anysphere.cursor-retrieval/oauth/callback", True),
    ("http://evil.example/callback", False),
    ("https://evil.example/callback#frag", False),
    ("javascript:alert(1)", False),
    ("data:text/html,hi", False),
])
def test_only_safe_redirects_can_register(setup, redirect, ok):
    _, web, _, _, _ = setup
    reply = register(web, redirect=redirect)
    assert (reply.status_code == 201) is ok, reply.text
    if not ok:
        assert reply.json()["error"] in ("invalid_redirect_uri", "invalid_client_metadata")


def test_a_token_for_another_server_is_refused(setup):
    _, web, _, _, _ = setup
    client_id = register(web).json()["client_id"]
    _, challenge = pkce()
    reply = start(web, client_id, challenge, resource="https://other.example/mcp")
    back = parse_qs(urlparse(reply.headers.get("location", "")).query)
    assert reply.status_code in (302, 400) and back.get("error", ["invalid_target"]) == ["invalid_target"]
    assert "request" not in back


def test_the_sign_in_page_is_safe_to_show(setup):
    _, web, _, _, _ = setup
    client_id = register(web, client_name='<script>alert("x")</script>').json()["client_id"]
    _, challenge = pkce()
    shown = web.get(start(web, client_id, challenge).headers["location"])
    assert "<script>alert" not in shown.text and "&lt;script&gt;" in shown.text
    assert shown.headers["x-frame-options"] == "DENY"
    assert "frame-ancestors 'none'" in shown.headers["content-security-policy"]
    assert shown.headers["cache-control"] == "no-store"


def test_unregistered_apps_and_floods_are_turned_away(setup):
    _, web, _, _, _ = setup
    _, challenge = pkce()
    assert start(web, "no-such-client", challenge).status_code == 400
    codes = [register(web).status_code for _ in range(25)]
    assert codes.count(201) == 20 and codes[-1] == 429


def test_odd_input_on_the_sign_in_page_is_a_plain_no(setup):
    _, web, _, _, _ = setup
    client_id = register(web).json()["client_id"]
    _, challenge = pkce()
    location = start(web, client_id, challenge).headers["location"]
    for login in ("a\x00b", "x" * 300):  # (a browser can't send half a character in a form)
        reply = sign_in(web, location, login=login)
        assert reply.status_code == 400, login
    assert web.post("/oauth/login", data={"request": "\x00"}).status_code == 400


# --- the MCP SDK's own OAuth client, as Claude Code and Codex use the same steps -------------------
def test_the_mcp_sdks_oauth_client_connects_end_to_end(setup):
    import anyio
    import httpx2
    from mcp.client.auth import OAuthClientProvider, TokenStorage
    from mcp.client.auth.oauth2 import AuthorizationCodeResult
    from mcp.client.session import ClientSession
    from mcp.client.streamable_http import streamable_http_client
    from mcp.shared.auth import OAuthClientInformationFull, OAuthClientMetadata, OAuthToken

    _, _, _, sid, router = setup

    class Memory(TokenStorage):
        def __init__(self) -> None:
            self.tokens: OAuthToken | None = None
            self.client: OAuthClientInformationFull | None = None

        async def get_tokens(self) -> OAuthToken | None:
            return self.tokens

        async def set_tokens(self, tokens: OAuthToken) -> None:
            self.tokens = tokens

        async def get_client_info(self) -> OAuthClientInformationFull | None:
            return self.client

        async def set_client_info(self, client_info: OAuthClientInformationFull) -> None:
            self.client = client_info

    landed: dict[str, str] = {}

    async def main() -> list[str]:
        transport = httpx2.ASGITransport(app=router)

        async def browser(url: str) -> None:
            """The student's browser: open the sign-in page, sign in, follow back."""
            async with httpx2.AsyncClient(transport=transport, base_url=BASE) as b:
                page = await b.get(url)
                login = page.headers["location"]
                assert login.startswith(f"{BASE}/oauth/login")
                done = await b.post("/oauth/login", data={
                    "request": request_id(login), "login": "asha.k",
                    "password": "correct horse", "decision": "allow"})
                back = parse_qs(urlparse(done.headers["location"]).query)
                landed.update(code=back["code"][0], state=back["state"][0])

        async def callback() -> AuthorizationCodeResult:
            return AuthorizationCodeResult(code=landed["code"], state=landed["state"])

        storage = Memory()
        oauth = OAuthClientProvider(
            server_url=f"{BASE}/mcp",
            client_metadata=OAuthClientMetadata(
                client_name="Codex", redirect_uris=[REDIRECT], grant_types=[
                    "authorization_code", "refresh_token"], response_types=["code"],
                token_endpoint_auth_method="none"),
            storage=storage, redirect_handler=browser, callback_handler=callback)
        async with httpx2.AsyncClient(transport=transport, base_url=BASE, auth=oauth) as http:
            async with streamable_http_client(f"{BASE}/mcp", http_client=http) as (read, write):
                async with ClientSession(read, write) as session:
                    await session.initialize()
                    tools = await session.list_tools()
        assert storage.tokens is not None and storage.tokens.access_token.startswith("75a_")
        return [t.name for t in tools.tools]

    names = anyio.run(main)
    assert "due_this_week" in names and "add_to_calendar" in names
