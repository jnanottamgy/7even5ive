from __future__ import annotations

from datetime import datetime

import httpx
import pytest

from mailfilter.errors import (
    CollegeBlocked,
    GmailConfigError,
    GmailUnavailable,
    MailUnreadable,
    NeedsReconnect,
)
from mailfilter.gmail import COST_GET_RAW, UNITS_PER_MINUTE, GmailMailbox
from mailfilter.samples import BY_KEY, fake_mails
from mailfilter.timekit import IST
from tests.conftest import GmailFake, SleepRecorder, google_error

MONDAY = datetime(2026, 11, 30, 0, 0, tzinfo=IST)


def mailbox(
    fake: GmailFake, sleeper: SleepRecorder | None = None
) -> tuple[GmailMailbox, list[bool]]:
    asked: list[bool] = []

    def token(fresh: bool) -> str:
        asked.append(fresh)
        return "fresh-token" if fresh else "cached-token"

    sleeper = sleeper or SleepRecorder()
    box = GmailMailbox(
        token, fake.client(), 15_000, sleep=sleeper.sleep, monotonic=sleeper.monotonic,
        jitter=lambda: 0.0,
    )  # fmt: skip
    return box, asked


def test_listing_pages_through_everything_newest_first() -> None:
    fake = GmailFake(fake_mails(), page_size=7)
    box, _ = mailbox(fake)
    ids, capped = box.list_ids(MONDAY, 2000)
    assert not capped
    assert len(ids) == 30
    received = {m.id: m.received_at for m in fake.mails}
    assert [received[i] for i in ids] == sorted(received.values(), reverse=True)
    query = fake.requests[0].url.params
    assert query["q"] == f"after:{int(MONDAY.timestamp())}"  # seconds: exact, not Pacific days


def test_listing_stops_at_the_limit_and_says_so() -> None:
    box, _ = mailbox(GmailFake(fake_mails(), page_size=7))
    ids, capped = box.list_ids(MONDAY, 10)
    assert len(ids) == 10 and capped


def test_a_mail_comes_back_parsed_with_its_labels_and_time() -> None:
    sample = BY_KEY["html_only_drive"]
    box, _ = mailbox(GmailFake(fake_mails()))
    mail = box.get(sample.mail.id)
    assert mail is not None
    assert mail.received_at == sample.mail.received_at
    assert mail.labels == frozenset({"INBOX"})
    assert "https://forms.gle/DeccanPool27" in mail.content.links
    sent = box.get(BY_KEY["sent_by_student"].mail.id)
    assert sent is not None and sent.skipped


def test_a_mail_deleted_after_listing_is_none() -> None:
    box, _ = mailbox(GmailFake(fake_mails()))
    assert box.get("00000000deadbeef") is None


def test_an_expired_token_is_refreshed_once() -> None:
    fake = GmailFake(fake_mails())
    fake.queue("/profile", 401, google_error(401, "authError"))
    box, asked = mailbox(fake)
    assert box.email_address() == "student@mockcollege.edu.in"
    assert asked == [False, True]
    assert fake.tokens_seen == ["Bearer cached-token", "Bearer fresh-token"]


def test_a_token_google_keeps_refusing_needs_a_new_sign_in() -> None:
    fake = GmailFake(fake_mails())
    fake.queue("/profile", 401, google_error(401, "authError"))
    fake.queue("/profile", 401, google_error(401, "authError"))
    box, _ = mailbox(fake)
    with pytest.raises(NeedsReconnect):
        box.email_address()


@pytest.mark.parametrize(
    ("status", "body", "headers"),
    [
        (403, google_error(403, "userRateLimitExceeded"), {}),
        (403, google_error(403, "rateLimitExceeded"), {}),
        (429, google_error(429, "rateLimitExceeded"), {"Retry-After": "7"}),
        (500, google_error(500, "backendError"), {}),
        (503, {}, {}),
    ],
)
def test_busy_answers_are_retried_with_backoff(
    status: int, body: dict[str, object], headers: dict[str, str]
) -> None:
    fake = GmailFake(fake_mails())
    fake.queue("/profile", status, body, headers)
    fake.queue("/profile", status, body, headers)
    sleeper = SleepRecorder()
    box, _ = mailbox(fake, sleeper)
    assert box.email_address() == "student@mockcollege.edu.in"
    expected_first = 7.0 if "Retry-After" in headers else 1.0
    assert sleeper.slept[:2] == [expected_first, 7.0 if headers else 2.0]


def test_retries_run_out_as_unavailable() -> None:
    fake = GmailFake(fake_mails())
    for _ in range(5):
        fake.queue("/profile", 503)
    box, _ = mailbox(fake)
    with pytest.raises(GmailUnavailable) as raised:
        box.email_address()
    assert raised.value.detail == "http_503"


def test_network_failures_are_retried() -> None:
    calls = {"n": 0}

    def flaky(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        if calls["n"] < 3:
            raise httpx.ConnectError("down", request=request)
        return httpx.Response(200, json={"emailAddress": "a@b.c"})

    box = GmailMailbox(
        lambda fresh: "t", httpx.Client(transport=httpx.MockTransport(flaky)), 100,
        sleep=lambda s: None, jitter=lambda: 0.0,
    )  # fmt: skip
    assert box.email_address() == "a@b.c"
    assert calls["n"] == 3


@pytest.mark.parametrize(
    ("reason", "error"),
    [
        ("domainPolicy", CollegeBlocked),
        ("insufficientPermissions", NeedsReconnect),
        ("ACCESS_TOKEN_SCOPE_INSUFFICIENT", NeedsReconnect),
        ("dailyLimitExceeded", GmailUnavailable),
        ("accessNotConfigured", GmailConfigError),
    ],
)
def test_forbidden_answers_are_named(reason: str, error: type[Exception]) -> None:
    fake = GmailFake(fake_mails())
    fake.queue("/messages", 403, google_error(403, reason))
    box, _ = mailbox(fake)
    with pytest.raises(error):
        box.list_ids(MONDAY, 100)


def test_one_broken_mail_is_unreadable_not_an_outage() -> None:
    def broken(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"id": "abc", "raw": "!!!", "internalDate": "x"})

    box = GmailMailbox(lambda fresh: "t", httpx.Client(transport=httpx.MockTransport(broken)), 100)
    with pytest.raises(MailUnreadable):
        box.get("0000000000000abc")
    with pytest.raises(MailUnreadable):
        box.get("../../profile")  # never becomes a path


def test_quota_pacing_waits_instead_of_tripping_googles_limit() -> None:
    sleeper = SleepRecorder()
    fake = GmailFake(fake_mails())
    box, _ = mailbox(fake, sleeper)
    gets = UNITS_PER_MINUTE // COST_GET_RAW + 3
    ids = [m.id for m in fake.mails]
    for index in range(gets):
        box.get(ids[index % len(ids)])
    assert sleeper.slept and 59 < sleeper.slept[0] <= 60.01


def test_the_client_has_no_way_to_change_mail() -> None:
    public = {name for name in dir(GmailMailbox) if not name.startswith("_")}
    assert public == {"list_ids", "get", "email_address"}
    fake = GmailFake(fake_mails())
    box, _ = mailbox(fake)
    box.list_ids(MONDAY, 50)
    box.get(fake.mails[0].id)
    box.email_address()
    assert {request.method for request in fake.requests} == {"GET"}
