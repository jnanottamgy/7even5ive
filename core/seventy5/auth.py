"""Signing in: Supabase Auth issues the tokens, this service only checks them.

The app talks to Supabase Auth itself (sign up, the emailed code, log in, refresh, forgotten
password), with the project's publishable key, which is made to be shipped in apps. Why the app
and not this service: Supabase rate-limits sign-ins per IP address, and through one server every
student would share the server's address. The app then sends its access token (a JWT, valid
about an hour) with every request here, and this module checks it:

- ES256 / RS256 (Supabase's JWT signing keys, the default for new projects): against the public
  keys at <SUPABASE_URL>/auth/v1/.well-known/jwks.json, cached 10 minutes as Supabase advises.
- HS256 (a project still on the legacy JWT secret): with SUPABASE_JWT_SECRET when it is set;
  otherwise by asking Supabase (GET /auth/v1/user), remembered until the token expires.

Always checked: the signature, expiry (30 s of clock leeway), the issuer (this project), the
audience and role "authenticated", and that the user is not anonymous.
Not: sessions of our own. Supabase's refresh tokens rotate and are revoked by Supabase; a
token that fails here makes the app refresh once, then sign in again.
Logs: never a token, never an email; a user id at most.
"""

from __future__ import annotations

import base64
import hashlib
import json
import logging
import threading
import time
from collections import deque
from dataclasses import dataclass
from typing import Any, Callable

import httpx

from .config import settings

log = logging.getLogger(__name__)

JWKS_TTL_SECONDS = 600.0  # Supabase's edge caches the key set for 10 minutes; so do we
JWKS_RETRY_SECONDS = 30.0  # an unknown key id refetches the set at most this often
LEEWAY_SECONDS = 30
HTTP_TIMEOUT = 6.0


class AuthError(Exception):
    """The token is not a valid session. status 401 (sign in again) or 503 (Supabase can't be
    reached to check it: try again)."""

    def __init__(self, message: str, status: int = 401, code: str = "session_expired") -> None:
        super().__init__(message)
        self.status = status
        self.code = code


@dataclass(frozen=True)
class Identity:
    user_id: str
    email: str | None
    expires_at: int


def _client() -> httpx.Client:
    """The HTTP client for Supabase (a function, so tests can answer for Supabase)."""
    return httpx.Client(timeout=HTTP_TIMEOUT)


def configured() -> bool:
    """Sign-in is on: the app can reach Supabase Auth and this service can check its tokens."""
    return bool(settings.supabase_url and settings.supabase_publishable_key)


def looks_like_jwt(token: str) -> bool:
    """A Supabase access token, as opposed to a personal token (which has no dots)."""
    return token.count(".") == 2 and token.startswith("eyJ")


def _claims_unverified(token: str) -> dict[str, Any]:
    try:
        payload = token.split(".")[1]
        return dict(json.loads(base64.urlsafe_b64decode(payload + "=" * (-len(payload) % 4))))
    except (IndexError, ValueError, TypeError) as err:
        raise AuthError("Not a valid sign-in token.") from err


class Verifier:
    """Checks one project's access tokens. One per process (verifier()); thread-safe."""

    def __init__(self, url: str, publishable_key: str, jwt_secret: str = "",
                 http: httpx.Client | None = None,
                 clock: Callable[[], float] = time.time) -> None:
        self.base = url.rstrip("/")
        self.issuer = f"{self.base}/auth/v1"
        self.publishable_key = publishable_key
        self.jwt_secret = jwt_secret
        self.http = http or _client()
        self.clock = clock
        self._lock = threading.Lock()
        self._keys: dict[str, Any] = {}
        self._keys_at = -1e9
        self._asked: dict[str, Identity] = {}  # HS256 without the secret: SHA-256(token) -> who

    # --- the key set ------------------------------------------------------------------------
    def _fetch_keys(self) -> None:
        import jwt

        try:
            response = self.http.get(f"{self.issuer}/.well-known/jwks.json",
                                     headers={"apikey": self.publishable_key})
            response.raise_for_status()
            found = response.json().get("keys", [])
        except (httpx.HTTPError, ValueError) as err:
            log.warning("jwks fetch failed", extra={"error": type(err).__name__})
            raise AuthError("Can't check your sign-in right now. Try again in a moment.", 503,
                            "auth_unavailable") from err
        keys: dict[str, Any] = {}
        for jwk in found:
            try:
                keys[str(jwk.get("kid"))] = jwt.PyJWK(jwk).key
            except (jwt.PyJWKError, jwt.InvalidKeyError, ValueError, TypeError):
                continue  # a key type this build can't use: skip it, keep the others
        self._keys, self._keys_at = keys, self.clock()

    def _key(self, kid: str | None) -> Any:
        with self._lock:
            age = self.clock() - self._keys_at
            if age > JWKS_TTL_SECONDS or (str(kid) not in self._keys and age > JWKS_RETRY_SECONDS):
                self._fetch_keys()
            key = self._keys.get(str(kid))
        if key is None:
            raise AuthError("This sign-in was made with a key this server doesn't trust.")
        return key

    # --- checking a token -------------------------------------------------------------------
    def verify(self, token: str) -> Identity:
        import jwt

        try:
            header = jwt.get_unverified_header(token)
        except jwt.PyJWTError as err:
            raise AuthError("Not a valid sign-in token.") from err
        alg = header.get("alg")
        if alg in ("ES256", "RS256"):
            key: Any = self._key(header.get("kid"))
        elif alg == "HS256" and self.jwt_secret:
            key = self.jwt_secret
        elif alg == "HS256":
            return self._ask(token)
        else:
            raise AuthError("Not a valid sign-in token.")
        try:
            claims = jwt.decode(token, key, algorithms=[alg], audience="authenticated",
                                issuer=self.issuer, leeway=LEEWAY_SECONDS,
                                options={"require": ["exp", "sub", "aud", "iss"]})
        except jwt.ExpiredSignatureError as err:
            raise AuthError("Your session expired. Sign in again.") from err
        except jwt.PyJWTError as err:
            raise AuthError("Not a valid sign-in token.") from err
        return self._identity(claims)

    def _identity(self, claims: dict[str, Any]) -> Identity:
        if claims.get("role") != "authenticated" or claims.get("is_anonymous"):
            raise AuthError("Sign in with your account.")
        sub = str(claims.get("sub") or "")
        if not sub:
            raise AuthError("Not a valid sign-in token.")
        email = claims.get("email")
        return Identity(sub, str(email).lower() if email else None, int(claims.get("exp") or 0))

    def _ask(self, token: str) -> Identity:
        """HS256 with no secret here: Supabase itself says whether the token is good (its own
        advice for shared-secret projects). Remembered until the token expires, at most 5
        minutes, so one session costs Supabase one call per 5 minutes, not one per request."""
        claims = _claims_unverified(token)
        now = self.clock()
        exp = int(claims.get("exp") or 0)
        if exp and exp + LEEWAY_SECONDS < now:
            raise AuthError("Your session expired. Sign in again.")
        if claims.get("iss") != self.issuer:
            raise AuthError("Not a valid sign-in token.")
        digest = hashlib.sha256(token.encode()).hexdigest()
        with self._lock:
            known = self._asked.get(digest)
            if known is not None and min(known.expires_at, now + 300) > now:
                return known
        try:
            response = self.http.get(f"{self.issuer}/user",
                                     headers={"apikey": self.publishable_key,
                                              "Authorization": f"Bearer {token}"})
        except httpx.HTTPError as err:
            raise AuthError("Can't check your sign-in right now. Try again in a moment.", 503,
                            "auth_unavailable") from err
        if response.status_code in (401, 403):
            raise AuthError("Your session expired. Sign in again.")
        if response.status_code != 200:
            raise AuthError("Can't check your sign-in right now. Try again in a moment.", 503,
                            "auth_unavailable")
        user = response.json()
        identity = self._identity({**claims, "sub": user.get("id"),
                                   "email": user.get("email") or claims.get("email"),
                                   "is_anonymous": user.get("is_anonymous", False)})
        with self._lock:
            if len(self._asked) > 5000:
                self._asked.clear()
            self._asked[digest] = Identity(identity.user_id, identity.email,
                                           min(exp or int(now) + 300, int(now) + 300))
        return identity


_verifier: Verifier | None = None


def verifier() -> Verifier:
    global _verifier
    if _verifier is None:
        if not configured():
            raise AuthError("Sign-in isn't set up on this server.", 503, "auth_unavailable")
        _verifier = Verifier(settings.supabase_url, settings.supabase_publishable_key,
                             settings.supabase_jwt_secret)
    return _verifier


def verify(token: str) -> Identity:
    return verifier().verify(token)


# --- Supabase's admin API (the secret key) ------------------------------------------------------
def _server_headers() -> dict[str, str]:
    key = settings.supabase_secret_key
    # New secret keys (sb_secret_...) go only in the apikey header; a legacy service_role key is
    # a JWT and also goes in Authorization, as Supabase expects for it.
    headers = {"apikey": key}
    if key.startswith("eyJ"):
        headers["Authorization"] = f"Bearer {key}"
    return headers


def can_delete_users() -> bool:
    return configured() and bool(settings.supabase_secret_key)


def delete_user(user_id: str, http: httpx.Client | None = None) -> None:
    """Removes the login itself. A user already gone counts as removed."""
    client = http or _client()
    try:
        response = client.delete(f"{settings.supabase_url}/auth/v1/admin/users/{user_id}",
                                 headers=_server_headers())
    except httpx.HTTPError as err:
        raise AuthError("Couldn't reach Supabase to remove your login. Try again.", 503,
                        "auth_unavailable") from err
    if response.status_code not in (200, 204, 404):
        log.warning("auth user delete failed", extra={"status": response.status_code})
        raise AuthError("Couldn't remove your login right now. Try again.", 502, "auth_failed")


def password_login(email: str, password: str, client_ip: str | None,
                   http: httpx.Client | None = None) -> httpx.Response:
    """A password sign-in on the student's behalf (a username instead of an email). With the
    secret key, Supabase is told the student's own address (Sb-Forwarded-For), so its per-IP
    limits apply to them, not to this server, once IP forwarding is on in the project."""
    client = http or _client()
    headers = {"apikey": settings.supabase_publishable_key}
    if settings.supabase_secret_key and client_ip:
        headers = {**_server_headers(), "Sb-Forwarded-For": client_ip}
    try:
        return client.post(f"{settings.supabase_url}/auth/v1/token",
                           params={"grant_type": "password"},
                           json={"email": email, "password": password}, headers=headers)
    except httpx.HTTPError as err:
        raise AuthError("Couldn't reach the sign-in service. Try again.", 503,
                        "auth_unavailable") from err


# --- a small limiter for the endpoints anyone can call ---------------------------------------
class Limiter:
    """At most `limit` calls per `window` seconds per key, in this process. Lambda is pinned to
    one instance, so this holds; elsewhere it is per instance, a best effort."""

    def __init__(self, limit: int, window: float, clock: Callable[[], float] = time.monotonic):
        self.limit, self.window, self.clock = limit, window, clock
        self._hits: dict[str, deque[float]] = {}
        self._lock = threading.Lock()

    def allow(self, key: str) -> bool:
        now = self.clock()
        with self._lock:
            if len(self._hits) > 20000:
                self._hits.clear()
            hits = self._hits.setdefault(key, deque())
            while hits and now - hits[0] > self.window:
                hits.popleft()
            if len(hits) >= self.limit:
                return False
            hits.append(now)
            return True
