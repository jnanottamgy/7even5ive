"""Google sign-in: read-only Gmail access for one student, and turning it into access tokens.

Production keeps refresh tokens in AgentCore Identity (KMS-encrypted), never in our database.
Development and the demo keep them in a local file (`FileRefreshTokenStore`, mode 0600) filled
by `mailfilter connect`, which runs Google's installed-app flow on a loopback address with PKCE.

Google ends a refresh token when the student revokes access, and after 7 days for apps in
Testing mode; both arrive as `invalid_grant` and become `NeedsReconnect`.
"""

from __future__ import annotations

import base64
import hashlib
import json
import os
import secrets
import tempfile
import threading
from collections.abc import Callable
from dataclasses import dataclass
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from typing import Protocol
from urllib.parse import parse_qs, urlencode, urlsplit

import httpx

from mailfilter.errors import GmailConfigError, GmailUnavailable, NeedsReconnect, NotConnected

SCOPE = "https://www.googleapis.com/auth/gmail.readonly"
AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
TOKEN_URL = "https://oauth2.googleapis.com/token"
REVOKE_URL = "https://oauth2.googleapis.com/revoke"
# Refresh an access token this long before Google says it expires.
EARLY = 60.0


class RefreshTokenStore(Protocol):
    def get(self, student_id: str) -> str | None: ...

    def put(self, student_id: str, refresh_token: str) -> None: ...

    def delete(self, student_id: str) -> None: ...


class MemoryRefreshTokenStore:
    def __init__(self) -> None:
        self._tokens: dict[str, str] = {}

    def get(self, student_id: str) -> str | None:
        return self._tokens.get(student_id)

    def put(self, student_id: str, refresh_token: str) -> None:
        self._tokens[student_id] = refresh_token

    def delete(self, student_id: str) -> None:
        self._tokens.pop(student_id, None)


class FileRefreshTokenStore:
    """Development only: a JSON file readable by its owner alone, replaced atomically."""

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self._lock = threading.Lock()

    def _read(self) -> dict[str, str]:
        if not self.path.exists():
            return {}
        data = json.loads(self.path.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            raise GmailConfigError("token_file_corrupt")
        return {str(k): str(v) for k, v in data.items()}

    def _write(self, data: dict[str, str]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        handle, temporary = tempfile.mkstemp(dir=self.path.parent, prefix=".tokens-")
        try:
            os.fchmod(handle, 0o600)
            with os.fdopen(handle, "w", encoding="utf-8") as file:
                json.dump(data, file)
            os.replace(temporary, self.path)
        except BaseException:
            Path(temporary).unlink(missing_ok=True)
            raise

    def get(self, student_id: str) -> str | None:
        with self._lock:
            return self._read().get(student_id)

    def put(self, student_id: str, refresh_token: str) -> None:
        with self._lock:
            data = self._read()
            data[student_id] = refresh_token
            self._write(data)

    def delete(self, student_id: str) -> None:
        with self._lock:
            data = self._read()
            if data.pop(student_id, None) is not None:
                self._write(data)


@dataclass
class _Cached:
    token: str
    expires_at: float


def _oauth_error(response: httpx.Response) -> str:
    try:
        body = response.json()
    except ValueError:
        return ""
    return str(body.get("error", "")) if isinstance(body, dict) else ""


def _granted(scopes: object) -> bool:
    return isinstance(scopes, str) and SCOPE in scopes.split()


class GoogleTokens:
    """Access tokens for each student from their refresh token, cached until near expiry."""

    def __init__(
        self,
        client_id: str,
        client_secret: str,
        store: RefreshTokenStore,
        http: httpx.Client,
        clock: Callable[[], float],
    ) -> None:
        if not client_id:
            raise GmailConfigError("google_client_missing")
        self.client_id = client_id
        self._secret = client_secret
        self.store = store
        self._http = http
        self._clock = clock
        self._cache: dict[str, _Cached] = {}

    def access_token(self, student_id: str, *, force_refresh: bool = False) -> str:
        cached = self._cache.get(student_id)
        if cached and not force_refresh and cached.expires_at - EARLY > self._clock():
            return cached.token
        refresh = self.store.get(student_id)
        if refresh is None:
            raise NotConnected("no_refresh_token")
        try:
            response = self._http.post(
                TOKEN_URL,
                data={
                    "client_id": self.client_id,
                    "client_secret": self._secret,
                    "refresh_token": refresh,
                    "grant_type": "refresh_token",
                },
            )
        except httpx.HTTPError:
            raise GmailUnavailable("token_network") from None
        if response.status_code >= 500:
            raise GmailUnavailable(f"token_http_{response.status_code}")
        if response.status_code != 200:
            error = _oauth_error(response)
            if error == "invalid_grant":
                self._cache.pop(student_id, None)
                raise NeedsReconnect("invalid_grant")
            raise GmailConfigError(error or f"token_http_{response.status_code}")
        try:
            body = response.json()
            token = str(body["access_token"])
            lifetime = float(body.get("expires_in", 3600))
        except (ValueError, KeyError, TypeError):
            raise GmailUnavailable("token_bad_response") from None
        if "scope" in body and not _granted(body["scope"]):
            raise NeedsReconnect("scope_not_granted")
        self._cache[student_id] = _Cached(token=token, expires_at=self._clock() + lifetime)
        return token

    def revoke(self, student_id: str) -> bool:
        """Ask Google to end the grant. True when Google confirms, or it was already gone."""
        self._cache.pop(student_id, None)
        refresh = self.store.get(student_id)
        if refresh is None:
            return True
        try:
            response = self._http.post(
                REVOKE_URL,
                data={"token": refresh},
                headers={"Content-Type": "application/x-www-form-urlencoded"},
            )
        except httpx.HTTPError:
            return False
        return response.status_code == 200 or _oauth_error(response) == "invalid_token"


def pkce_pair() -> tuple[str, str]:
    verifier = secrets.token_urlsafe(64)[:96]
    digest = hashlib.sha256(verifier.encode("ascii")).digest()
    challenge = base64.urlsafe_b64encode(digest).decode("ascii").rstrip("=")
    return verifier, challenge


def authorization_url(client_id: str, redirect_uri: str, state: str, challenge: str) -> str:
    query = urlencode(
        {
            "client_id": client_id,
            "redirect_uri": redirect_uri,
            "response_type": "code",
            "scope": SCOPE,
            "state": state,
            "code_challenge": challenge,
            "code_challenge_method": "S256",
            "access_type": "offline",
            # Always ask, so Google always returns a refresh token, even on a second sign-in.
            "prompt": "consent",
        }
    )
    return f"{AUTH_URL}?{query}"


def exchange_code(
    http: httpx.Client,
    client_id: str,
    client_secret: str,
    code: str,
    verifier: str,
    redirect_uri: str,
) -> str:
    """The authorisation code for a refresh token, refusing a sign-in without Gmail access."""
    try:
        response = http.post(
            TOKEN_URL,
            data={
                "client_id": client_id,
                "client_secret": client_secret,
                "code": code,
                "code_verifier": verifier,
                "grant_type": "authorization_code",
                "redirect_uri": redirect_uri,
            },
        )
    except httpx.HTTPError:
        raise GmailUnavailable("token_network") from None
    if response.status_code != 200:
        raise GmailConfigError(_oauth_error(response) or f"token_http_{response.status_code}")
    body = response.json()
    if not _granted(body.get("scope")):
        # Google lets people untick a permission on the consent screen.
        raise NeedsReconnect("scope_not_granted")
    refresh = body.get("refresh_token")
    if not isinstance(refresh, str) or not refresh:
        raise GmailConfigError("no_refresh_token_returned")
    return refresh


@dataclass
class LoopbackResult:
    code: str | None = None
    state: str | None = None
    error: str | None = None


def wait_for_redirect(server: HTTPServer, expected_state: str, timeout: float = 300.0) -> str:
    """Serve one redirect on the loopback address and return its code, checking the state."""
    result = LoopbackResult()

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:  # noqa: N802 - the http.server hook name
            query = parse_qs(urlsplit(self.path).query)

            def first(name: str) -> str | None:
                values = query.get(name)
                return values[0] if values else None

            result.code = first("code")
            result.state = first("state")
            result.error = first("error")
            body = b"Done. You can close this tab and go back to the terminal."
            self.send_response(200)
            self.send_header("Content-Type", "text/plain; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, format: str, *args: object) -> None:  # noqa: A002
            return  # the redirect carries the code: never print it

    server.RequestHandlerClass = Handler
    server.timeout = timeout
    server.handle_request()
    if result.code is None and result.error is None and result.state is None:
        raise GmailConfigError("sign_in_timed_out")
    if result.error:
        raise NeedsReconnect(f"consent_{result.error}"[:40])
    if result.state != expected_state:
        raise GmailConfigError("state_mismatch")
    if not result.code:
        raise GmailConfigError("no_code")
    return result.code
