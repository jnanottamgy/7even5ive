"""Firebase Cloud Messaging: wakes the student's phone when the outbox gets something.

The push carries no title and no text -- only {"type": "sync"} -- and the phone then pulls its
outbox over our own API. So nothing about a deadline passes through Google's push service, and
a phone that missed a push still gets the message on its next pull.
Why no Firebase Admin SDK: one HTTPS call and a signed JWT are all this needs; the SDK would
pull in gRPC and a dozen packages.
Stand-in: with no service account configured there is no wake-up. The phone's foreground poll
and its 15-minute background pull still deliver everything, only later.
"""

from __future__ import annotations

import base64
import json
import logging
import os
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from typing import Any, Callable

import httpx

from .config import settings
from .db import Database

log = logging.getLogger(__name__)

SCOPE = "https://www.googleapis.com/auth/firebase.messaging"
SEND_URL = "https://fcm.googleapis.com/v1/projects/{project}/messages:send"
# FCM's answer for a token that no longer reaches an app (uninstalled, data cleared).
GONE = {"UNREGISTERED", "INVALID_ARGUMENT", "NOT_FOUND"}


@dataclass(frozen=True)
class ServiceAccount:
    project_id: str
    client_email: str
    private_key: str
    private_key_id: str
    token_uri: str = "https://oauth2.googleapis.com/token"

    @classmethod
    def from_json(cls, raw: str) -> ServiceAccount:
        data = json.loads(raw)
        return cls(project_id=data["project_id"], client_email=data["client_email"],
                   private_key=data["private_key"], private_key_id=data.get("private_key_id", ""),
                   token_uri=data.get("token_uri") or "https://oauth2.googleapis.com/token")


def _b64(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).decode().rstrip("=")


def signed_assertion(account: ServiceAccount, now: float) -> str:
    """The JWT Google's token endpoint swaps for an access token (RS256, one hour)."""
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import padding

    header = {"alg": "RS256", "typ": "JWT", "kid": account.private_key_id}
    claims = {"iss": account.client_email, "scope": SCOPE, "aud": account.token_uri,
              "iat": int(now), "exp": int(now) + 3600}
    signing_input = (_b64(json.dumps(header, separators=(",", ":")).encode()) + "."
                     + _b64(json.dumps(claims, separators=(",", ":")).encode()))
    key = serialization.load_pem_private_key(account.private_key.encode(), password=None)
    signature = key.sign(signing_input.encode(), padding.PKCS1v15(), hashes.SHA256())  # type: ignore[call-arg,union-attr]
    return f"{signing_input}.{_b64(signature)}"


class FcmWaker:
    """Callable(student_id): sends {"type": "sync"} to every phone the student registered.

    On a long-running server, sends happen on a small background pool, so the reminder loop
    never waits on Google. On Lambda they happen before the request or tick returns: Lambda
    freezes the instance as soon as it has answered, and a thread left with a wake-up would sit
    until the next invocation (or meet a dead connection then).
    """

    def __init__(self, db: Database, account: ServiceAccount, http: httpx.Client | None = None,
                 clock: Callable[[], float] = time.time, background: bool | None = None) -> None:
        if background is None:
            background = not os.environ.get("AWS_LAMBDA_FUNCTION_NAME")
        self.db, self.account, self.clock = db, account, clock
        self.http = http or httpx.Client(timeout=5.0)
        self._token: tuple[str, float] | None = None
        self._lock = threading.Lock()
        self._pool = ThreadPoolExecutor(max_workers=2, thread_name_prefix="fcm") if background else None

    def access_token(self) -> str:
        with self._lock:
            if self._token and self._token[1] - 60 > self.clock():
                return self._token[0]
            resp = self.http.post(self.account.token_uri, data={
                "grant_type": "urn:ietf:params:oauth:grant-type:jwt-bearer",
                "assertion": signed_assertion(self.account, self.clock()),
            })
            resp.raise_for_status()
            body = resp.json()
            self._token = (str(body["access_token"]),
                           self.clock() + float(body.get("expires_in", 3600)))
            return self._token[0]

    def push(self, token: str) -> bool:
        """One wake-up. Removes a token FCM says is gone. True when FCM accepted it."""
        try:
            resp = self.http.post(
                SEND_URL.format(project=self.account.project_id),
                headers={"Authorization": f"Bearer {self.access_token()}"},
                json={"message": {"token": token, "data": {"type": "sync"},
                                  "android": {"priority": "high", "ttl": "3600s"}}},
            )
        except httpx.HTTPError as err:
            log.warning("fcm unreachable", extra={"error": type(err).__name__})
            return False
        if resp.status_code == 200:
            return True
        if _error_code(resp) in GONE or resp.status_code == 404:
            self.db.remove_device(token)
            log.info("fcm token removed", extra={"status": resp.status_code})
        else:
            log.warning("fcm refused", extra={"status": resp.status_code})
        return False

    def wake(self, student_id: int) -> None:
        for token in self.db.device_tokens(student_id):
            self.push(token)

    def __call__(self, student_id: int) -> None:
        if self._pool is None:
            self._safe_wake(student_id)
        else:
            self._pool.submit(self._safe_wake, student_id)

    def _safe_wake(self, student_id: int) -> None:
        try:
            self.wake(student_id)
        except Exception as err:  # noqa: BLE001 - the outbox row is saved either way
            log.warning("fcm wake failed", extra={"error": type(err).__name__})


def _error_code(resp: httpx.Response) -> str | None:
    """FCM puts its own code in error.details[].errorCode; the HTTP status alone is ambiguous."""
    try:
        error: Any = resp.json().get("error", {})
    except ValueError:
        return None
    for detail in error.get("details", []) if isinstance(error, dict) else []:
        if isinstance(detail, dict) and detail.get("errorCode"):
            return str(detail["errorCode"])
    status = error.get("status") if isinstance(error, dict) else None
    return str(status) if status else None


def load_account() -> ServiceAccount | None:
    raw = settings.fcm_service_account_json
    if not raw and settings.fcm_service_account_file:
        try:
            with open(settings.fcm_service_account_file, encoding="utf-8") as f:
                raw = f.read()
        except OSError:
            log.warning("fcm service account file unreadable")
            return None
    if not raw:
        return None
    try:
        return ServiceAccount.from_json(raw)
    except (ValueError, KeyError):
        log.warning("fcm service account is not valid JSON")
        return None


def get_waker(db: Database) -> Callable[[int], None] | None:
    account = load_account()
    return FcmWaker(db, account) if account else None
