from __future__ import annotations

import base64
import json
import re
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

import httpx
import pytest

from mailfilter.config import Settings
from mailfilter.fake import STUDENT_ADDRESS, FakeMail
from mailfilter.store import Store
from mailfilter.timekit import IST

STUDENT = "student-asha"
MONDAY = datetime(2026, 11, 30, 0, 0, tzinfo=IST)


class Clock:
    """Time moved by hand: `now()` for the code under test, `advance()` for the test."""

    def __init__(self, start: datetime) -> None:
        self.current = start

    def __call__(self) -> datetime:
        return self.current

    def advance(self, **delta: float) -> None:
        self.current += timedelta(**delta)

    def set(self, value: datetime) -> None:
        self.current = value


@pytest.fixture
def clock() -> Clock:
    return Clock(datetime(2026, 12, 4, 1, 0, tzinfo=IST))


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    return Settings(database_url=f"sqlite:///{tmp_path / 'mailfilter.db'}")


@pytest.fixture
def store(settings: Settings) -> Store:
    return Store(settings.database_url)


@dataclass
class GmailFake:
    """Gmail's REST API for a list of mails: list (paged, `after:` in seconds), get raw, profile.

    `fail` maps a path fragment to queued responses (status, json body, headers) served before
    the real answer, to test retries and named errors.
    """

    mails: list[FakeMail]
    page_size: int = 500
    address: str = STUDENT_ADDRESS
    fail: dict[str, list[tuple[int, dict[str, Any], dict[str, str]]]] = field(default_factory=dict)
    requests: list[httpx.Request] = field(default_factory=list)
    tokens_seen: list[str] = field(default_factory=list)

    def queue(self, fragment: str, status: int, body: dict[str, Any] | None = None,
              headers: dict[str, str] | None = None) -> None:  # fmt: skip
        self.fail.setdefault(fragment, []).append((status, body or {}, headers or {}))

    def handler(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        self.tokens_seen.append(request.headers.get("Authorization", ""))
        path = request.url.path
        for fragment, queued in self.fail.items():
            if fragment in path and queued:
                status, body, headers = queued.pop(0)
                return httpx.Response(status, json=body, headers=headers)
        if path.endswith("/profile"):
            return httpx.Response(200, json={"emailAddress": self.address, "messagesTotal": 1})
        if path.endswith("/messages"):
            query = request.url.params.get("q", "")
            match = re.fullmatch(r"after:(\d+)", query)
            assert match, f"unexpected query {query!r}"
            after = int(match.group(1))
            listed = sorted(
                (m for m in self.mails if m.received_at.timestamp() > after
                 and not m.labels & {"SPAM", "TRASH"}),
                key=lambda m: m.received_at, reverse=True,
            )  # fmt: skip
            start = int(request.url.params.get("pageToken", "0") or 0)
            size = min(self.page_size, int(request.url.params.get("maxResults", "100")))
            page = listed[start : start + size]
            body: dict[str, Any] = {"resultSizeEstimate": len(listed)}
            if page:
                body["messages"] = [{"id": m.id, "threadId": m.thread_id} for m in page]
            if start + size < len(listed):
                body["nextPageToken"] = str(start + size)
            return httpx.Response(200, json=body)
        message_id = path.rsplit("/", 1)[-1]
        assert request.url.params.get("format") == "raw"
        for mail in self.mails:
            if mail.id == message_id:
                raw = base64.urlsafe_b64encode(mail.raw).decode("ascii").rstrip("=")
                return httpx.Response(
                    200,
                    json={
                        "id": mail.id,
                        "threadId": mail.thread_id,
                        "labelIds": sorted(mail.labels),
                        "internalDate": str(int(mail.received_at.timestamp() * 1000)),
                        "sizeEstimate": len(mail.raw),
                        "raw": raw,
                    },
                )
        return httpx.Response(404, json={"error": {"code": 404, "message": "Not Found"}})

    def client(self) -> httpx.Client:
        return httpx.Client(transport=httpx.MockTransport(self.handler))


def google_error(code: int, reason: str, status: str = "") -> dict[str, Any]:
    return {
        "error": {
            "code": code,
            "message": reason,
            "errors": [{"domain": "global", "reason": reason, "message": reason}],
            "status": status,
        }
    }


@dataclass
class SleepRecorder:
    slept: list[float] = field(default_factory=list)
    clock: list[float] = field(default_factory=lambda: [0.0])

    def sleep(self, seconds: float) -> None:
        self.slept.append(seconds)
        self.clock[0] += seconds

    def monotonic(self) -> float:
        return self.clock[0]


def as_json(response: httpx.Response) -> Any:
    return json.loads(response.content)


TokenFn = Callable[[bool], str]
