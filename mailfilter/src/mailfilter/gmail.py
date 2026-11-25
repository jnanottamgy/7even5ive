"""Gmail over its REST API, read-only, for one student.

Only three calls exist: list message ids since a moment, get one message (`format=raw`, so
Python's own mail parser reads it) and read the account's address. Nothing here can send,
label, move or delete mail: the client holds a `gmail.readonly` token and no such method.

Errors follow Google's guide: 401 refreshes the token once; 403 rate limits, 429 and 5xx are
retried with exponential backoff (honouring Retry-After); a 403 `domainPolicy` means the
college's admin blocks the app; a missing scope means the student must sign in again.
"""

from __future__ import annotations

import base64
import random
import re
import time
from collections import deque
from collections.abc import Callable
from datetime import datetime
from typing import Any, Protocol

import httpx

from mailfilter.errors import (
    CollegeBlocked,
    GmailConfigError,
    GmailUnavailable,
    MailUnreadable,
    NeedsReconnect,
)
from mailfilter.mail import MailMessage
from mailfilter.mime import parse_raw
from mailfilter.timekit import epoch_seconds, from_epoch_ms

API = "https://gmail.googleapis.com/gmail/v1/users/me"
# Quota units per call, from Google's usage-limits page.
COST_LIST = 5
COST_GET_RAW = 60
COST_PROFILE = 1
COST_HISTORY = 2
# A week of a student's college mail is far below this; past it, a check stops rather than
# cut the list.
MAX_LISTED = 20_000
# Google allows 6,000 units per user per minute; stay below it.
UNITS_PER_MINUTE = 5_000
PAGE_SIZE = 500
_ID = re.compile(r"[A-Za-z0-9_-]{1,64}")
Params = dict[str, str | int | list[str]]
_RATE_LIMITED = {"rateLimitExceeded", "userRateLimitExceeded", "RATE_LIMIT_EXCEEDED"}
_SCOPE_MISSING = {"insufficientPermissions", "ACCESS_TOKEN_SCOPE_INSUFFICIENT"}


class Mailbox(Protocol):
    def list_ids(self, after: datetime) -> list[str]:
        """Ids of every mail received after `after`, newest first."""
        ...

    def history_id(self) -> str:
        """Where the mailbox's change history stands now."""
        ...

    def changed_since(self, history_id: str) -> list[str] | None:
        """Mail added, or moved out of spam or trash, since `history_id`; None once Google no
        longer keeps that history (after about a week, sometimes sooner)."""
        ...

    def get(self, message_id: str) -> MailMessage | None:
        """One mail, or None when it was deleted after it was listed."""
        ...

    def email_address(self) -> str: ...


class _Retry(Exception):
    def __init__(self, reason: str, after: float | None = None) -> None:
        super().__init__(reason)
        self.reason = reason
        self.after = after


def _reasons(response: httpx.Response) -> set[str]:
    try:
        body = response.json()
    except ValueError:
        return set()
    error = body.get("error") if isinstance(body, dict) else None
    if not isinstance(error, dict):
        return set()
    found: set[str] = set()
    for key in ("errors", "details"):
        for item in error.get(key) or []:
            if isinstance(item, dict) and item.get("reason"):
                found.add(str(item["reason"]))
    if error.get("status"):
        found.add(str(error["status"]))
    return found


def _retry_after(response: httpx.Response) -> float | None:
    value = response.headers.get("Retry-After", "")
    return float(value) if value.isdigit() else None


def decode_raw(raw: str) -> bytes:
    return base64.urlsafe_b64decode(raw + "=" * (-len(raw) % 4))


class GmailMailbox:
    def __init__(
        self,
        token: Callable[[bool], str],
        http: httpx.Client,
        max_text_chars: int,
        *,
        sleep: Callable[[float], None] = time.sleep,
        monotonic: Callable[[], float] = time.monotonic,
        jitter: Callable[[], float] = random.random,
        max_attempts: int = 5,
    ) -> None:
        self._token = token
        self._http = http
        self._max_text_chars = max_text_chars
        self._sleep = sleep
        self._monotonic = monotonic
        self._jitter = jitter
        self._max_attempts = max_attempts
        self._spent: deque[tuple[float, int]] = deque()

    def list_ids(self, after: datetime) -> list[str]:
        params: Params = {"q": f"after:{epoch_seconds(after)}", "maxResults": PAGE_SIZE}
        ids: dict[str, None] = {}
        pages: set[str] = set()
        while True:
            body = self._call(f"{API}/messages", params, COST_LIST)
            if body is None:  # only `get` and `history` may answer "not found"
                raise GmailUnavailable("not_found")
            for item in body.get("messages") or []:
                message_id = str(item.get("id", "")) if isinstance(item, dict) else ""
                if _ID.fullmatch(message_id):
                    ids[message_id] = None
            if len(ids) > MAX_LISTED:
                # Never cut the list (the oldest mail would be lost); stop loudly instead.
                raise GmailUnavailable("listing_too_large")
            page = body.get("nextPageToken")
            if not page:
                return list(ids)
            if str(page) in pages:
                raise GmailUnavailable("listing_loops")
            pages.add(str(page))
            params = {**params, "pageToken": str(page)}

    def history_id(self) -> str:
        body = self._call(f"{API}/profile", None, COST_PROFILE)
        if body is None or not str(body.get("historyId", "")).isdigit():
            raise GmailUnavailable("bad_profile")
        return str(body["historyId"])

    def changed_since(self, history_id: str) -> list[str] | None:
        params: Params = {
            "startHistoryId": history_id,
            "historyTypes": ["messageAdded", "labelRemoved"],
            "maxResults": PAGE_SIZE,
        }
        ids: dict[str, None] = {}
        pages: set[str] = set()
        while True:
            body = self._call(f"{API}/history", params, COST_HISTORY, missing_ok=True)
            if body is None:
                return None  # history expired: the date window still covers recent mail
            for record in body.get("history") or []:
                if not isinstance(record, dict):
                    continue
                for added in record.get("messagesAdded") or []:
                    self._take(ids, added)
                for removed in record.get("labelsRemoved") or []:
                    if isinstance(removed, dict) and {"SPAM", "TRASH"} & set(
                        removed.get("labelIds") or []
                    ):
                        self._take(ids, removed)
            page = body.get("nextPageToken")
            if not page:
                return list(ids)
            if str(page) in pages or len(ids) > MAX_LISTED:
                raise GmailUnavailable("history_too_large")
            pages.add(str(page))
            params = {**params, "pageToken": str(page)}

    @staticmethod
    def _take(ids: dict[str, None], item: object) -> None:
        message = item.get("message") if isinstance(item, dict) else None
        message_id = str(message.get("id", "")) if isinstance(message, dict) else ""
        if _ID.fullmatch(message_id):
            ids[message_id] = None

    def get(self, message_id: str) -> MailMessage | None:
        if not _ID.fullmatch(message_id):
            raise MailUnreadable("bad_message_id")
        body = self._call(
            f"{API}/messages/{message_id}", {"format": "raw"}, COST_GET_RAW, missing_ok=True
        )
        if body is None:
            return None
        try:
            raw = decode_raw(str(body["raw"]))
            received = from_epoch_ms(int(body["internalDate"]))
        except (KeyError, ValueError, TypeError):
            raise MailUnreadable("bad_message") from None
        try:
            content = parse_raw(raw, self._max_text_chars)
        except Exception as error:  # noqa: BLE001 - one unparseable mail must not stop a check
            raise MailUnreadable(f"parse_{type(error).__name__}"[:40]) from None
        return MailMessage(
            id=message_id,
            thread_id=str(body.get("threadId") or message_id),
            received_at=received,
            labels=frozenset(str(label) for label in body.get("labelIds") or []),
            content=content,
        )

    def email_address(self) -> str:
        body = self._call(f"{API}/profile", None, COST_PROFILE)
        if body is None:
            raise GmailUnavailable("not_found")
        address = body.get("emailAddress")
        if not isinstance(address, str) or "@" not in address:
            raise GmailUnavailable("bad_profile")
        return address

    def _pace(self, cost: int) -> None:
        while True:
            now = self._monotonic()
            while self._spent and now - self._spent[0][0] >= 60.0:
                self._spent.popleft()
            if sum(units for _, units in self._spent) + cost <= UNITS_PER_MINUTE:
                self._spent.append((now, cost))
                return
            self._sleep(60.0 - (now - self._spent[0][0]) + 0.01)

    def _call(
        self,
        url: str,
        params: Params | None,
        cost: int,
        missing_ok: bool = False,
    ) -> dict[str, Any] | None:
        refreshed = False
        attempt = 0
        while True:
            self._pace(cost)
            try:
                return self._once(url, params, refreshed, missing_ok)
            except _Retry as retry:
                if retry.reason == "refresh":
                    if refreshed:
                        raise NeedsReconnect("gmail_401") from None
                    refreshed = True
                    continue
                attempt += 1
                if attempt >= self._max_attempts:
                    raise GmailUnavailable(retry.reason) from None
                wait = min(32.0, 2.0 ** (attempt - 1)) + self._jitter()
                if retry.after is not None:
                    wait = max(wait, min(retry.after, 60.0))
                self._sleep(wait)

    def _once(
        self,
        url: str,
        params: Params | None,
        fresh_token: bool,
        missing_ok: bool,
    ) -> dict[str, Any] | None:
        token = self._token(fresh_token)
        try:
            response = self._http.get(
                url, params=params, headers={"Authorization": f"Bearer {token}"}
            )
        except httpx.HTTPError:
            raise _Retry("network") from None
        status = response.status_code
        if status == 200:
            try:
                body = response.json()
            except ValueError:
                raise _Retry("bad_json") from None
            if not isinstance(body, dict):
                raise _Retry("bad_json")
            return body
        if status == 404 and missing_ok:
            return None
        reasons = _reasons(response)
        if status == 401:
            raise _Retry("refresh")
        if status == 403:
            if reasons & _RATE_LIMITED:
                raise _Retry("rate_limited", _retry_after(response))
            if "domainPolicy" in reasons:
                raise CollegeBlocked("domain_policy")
            if reasons & _SCOPE_MISSING:
                raise NeedsReconnect("scope_missing")
            if "dailyLimitExceeded" in reasons:
                raise GmailUnavailable("daily_limit")
            raise GmailConfigError(sorted(reasons)[0][:40] if reasons else "forbidden")
        if status == 429 or status >= 500:
            raise _Retry(f"http_{status}", _retry_after(response))
        if status == 400:
            raise GmailConfigError("bad_request")
        raise GmailUnavailable(f"http_{status}")
