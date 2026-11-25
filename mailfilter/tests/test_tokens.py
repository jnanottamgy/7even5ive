from __future__ import annotations

import base64
import hashlib
import stat
import threading
import urllib.request
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

import httpx
import pytest

from mailfilter.errors import GmailConfigError, GmailUnavailable, NeedsReconnect, NotConnected
from mailfilter.tokens import (
    REVOKE_URL,
    SCOPE,
    TOKEN_URL,
    FileRefreshTokenStore,
    GoogleTokens,
    MemoryRefreshTokenStore,
    authorization_url,
    exchange_code,
    pkce_pair,
    wait_for_redirect,
)


class Google:
    def __init__(self) -> None:
        self.responses: list[httpx.Response] = []
        self.requests: list[httpx.Request] = []

    def handler(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        return self.responses.pop(0)

    def client(self) -> httpx.Client:
        return httpx.Client(transport=httpx.MockTransport(self.handler))


def tokens(google: Google, now: list[float]) -> GoogleTokens:
    store = MemoryRefreshTokenStore()
    store.put("s1", "refresh-1")
    return GoogleTokens("client", "secret", store, google.client(), lambda: now[0])


def ok(token: str = "access-1", lifetime: int = 3600) -> httpx.Response:
    return httpx.Response(
        200,
        json={
            "access_token": token,
            "expires_in": lifetime,
            "scope": SCOPE,
            "token_type": "Bearer",
        },
    )


def test_access_tokens_are_refreshed_and_cached_until_near_expiry() -> None:
    google, now = Google(), [1000.0]
    google.responses = [ok("a1"), ok("a2")]
    source = tokens(google, now)
    assert source.access_token("s1") == "a1"
    now[0] += 3000
    assert source.access_token("s1") == "a1"  # cached
    now[0] += 560  # within a minute of expiry
    assert source.access_token("s1") == "a2"
    sent = parse_qs(google.requests[0].content.decode())
    assert sent["grant_type"] == ["refresh_token"] and sent["refresh_token"] == ["refresh-1"]
    assert str(google.requests[0].url) == TOKEN_URL


def test_force_refresh_skips_the_cache() -> None:
    google, now = Google(), [0.0]
    google.responses = [ok("a1"), ok("a2")]
    source = tokens(google, now)
    source.access_token("s1")
    assert source.access_token("s1", force_refresh=True) == "a2"


def test_a_revoked_or_expired_grant_needs_a_new_sign_in() -> None:
    google, now = Google(), [0.0]
    google.responses = [httpx.Response(400, json={"error": "invalid_grant"})]
    with pytest.raises(NeedsReconnect):
        tokens(google, now).access_token("s1")


def test_a_grant_without_gmail_needs_a_new_sign_in() -> None:
    google, now = Google(), [0.0]
    google.responses = [httpx.Response(200, json={"access_token": "a", "expires_in": 60,
                                                  "scope": "openid email"})]  # fmt: skip
    with pytest.raises(NeedsReconnect):
        tokens(google, now).access_token("s1")


def test_google_down_and_a_bad_client_are_told_apart() -> None:
    google, now = Google(), [0.0]
    google.responses = [httpx.Response(503), httpx.Response(401, json={"error": "invalid_client"})]
    source = tokens(google, now)
    with pytest.raises(GmailUnavailable):
        source.access_token("s1")
    with pytest.raises(GmailConfigError):
        source.access_token("s1")


def test_no_refresh_token_is_not_connected() -> None:
    google, now = Google(), [0.0]
    with pytest.raises(NotConnected):
        tokens(google, now).access_token("nobody")


def test_revoke_tells_google_and_tolerates_an_already_revoked_grant() -> None:
    google, now = Google(), [0.0]
    google.responses = [httpx.Response(400, json={"error": "invalid_token"})]
    source = tokens(google, now)
    assert source.revoke("s1")
    assert str(google.requests[0].url) == REVOKE_URL
    assert parse_qs(google.requests[0].content.decode()) == {"token": ["refresh-1"]}


def test_the_sign_in_link_asks_for_read_only_gmail_with_pkce() -> None:
    verifier, challenge = pkce_pair()
    digest = hashlib.sha256(verifier.encode()).digest()
    assert challenge == base64.urlsafe_b64encode(digest).decode().rstrip("=")
    assert 43 <= len(verifier) <= 128
    query = parse_qs(
        urlsplit(authorization_url("cid", "http://127.0.0.1:5000", "st", challenge)).query
    )
    assert query["scope"] == [SCOPE]
    assert query["code_challenge_method"] == ["S256"] and query["code_challenge"] == [challenge]
    assert query["access_type"] == ["offline"] and query["prompt"] == ["consent"]
    assert query["redirect_uri"] == ["http://127.0.0.1:5000"] and query["state"] == ["st"]


def test_a_sign_in_that_unticked_gmail_is_refused() -> None:
    google = Google()
    google.responses = [
        httpx.Response(200, json={"access_token": "a", "refresh_token": "r", "scope": "openid"}),
        httpx.Response(200, json={"access_token": "a", "refresh_token": "r2", "scope": SCOPE}),
    ]
    with google.client() as http:
        with pytest.raises(NeedsReconnect):
            exchange_code(http, "cid", "sec", "code", "verifier", "http://127.0.0.1:1")
        assert exchange_code(http, "cid", "sec", "code", "verifier", "http://127.0.0.1:1") == "r2"
    sent = parse_qs(google.requests[1].content.decode())
    assert sent["code_verifier"] == ["verifier"] and sent["grant_type"] == ["authorization_code"]


def _redirect(server: HTTPServer, query: str) -> None:
    port = server.server_address[1]
    urllib.request.urlopen(f"http://127.0.0.1:{port}/?{query}", timeout=5).read()


def test_the_loopback_redirect_returns_the_code_and_checks_the_state() -> None:
    server = HTTPServer(("127.0.0.1", 0), BaseHTTPRequestHandler)
    threading.Thread(target=_redirect, args=(server, "code=abc&state=xyz"), daemon=True).start()
    try:
        assert wait_for_redirect(server, "xyz", timeout=5) == "abc"
    finally:
        server.server_close()
    forged = HTTPServer(("127.0.0.1", 0), BaseHTTPRequestHandler)
    threading.Thread(target=_redirect, args=(forged, "code=abc&state=evil"), daemon=True).start()
    try:
        with pytest.raises(GmailConfigError):
            wait_for_redirect(forged, "xyz", timeout=5)
    finally:
        forged.server_close()


def test_the_dev_token_file_is_private_and_survives_reopening(tmp_path: Path) -> None:
    path = tmp_path / "tokens.json"
    store = FileRefreshTokenStore(path)
    store.put("s1", "r1")
    store.put("s2", "r2")
    store.delete("s1")
    assert FileRefreshTokenStore(path).get("s2") == "r2"
    assert FileRefreshTokenStore(path).get("s1") is None
    assert stat.S_IMODE(path.stat().st_mode) == 0o600
