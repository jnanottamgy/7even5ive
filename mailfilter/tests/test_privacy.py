"""What the filter keeps and logs: ids and counts, never mail content beyond the cards."""

from __future__ import annotations

import logging

import pytest

from mailfilter.config import Settings
from mailfilter.contract import OTHER
from mailfilter.errors import JudgeUnavailable
from mailfilter.fake import STUDENT_ADDRESS, FakeMailbox
from mailfilter.judge import ScriptedJudge
from mailfilter.run import check_mailbox
from mailfilter.samples import BY_KEY, SAMPLES, fake_mails, golden_judge
from mailfilter.store import Store
from tests.conftest import MONDAY, STUDENT, Clock

NEVER_KEPT = [
    "bro do you have the DBMS unit 3 notes",  # a friend's mail
    "Crack product interviews",  # a webinar
    "Ignore all previous instructions",  # the injection
    "robotics team's win",  # the newsletter
    "CTC: 8 LPA",  # body text of a kept mail that is not a card field
    "Regards,",
    "Mr. José",
]


def everything_logged(caplog: pytest.LogCaptureFixture) -> str:
    return "\n".join(f"{record.getMessage()} {record.__dict__}" for record in caplog.records)


def test_logs_carry_ids_and_counts_only(
    store: Store, settings: Settings, clock: Clock, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.DEBUG, logger="mailfilter")
    store.connect(STUDENT, STUDENT_ADDRESS, MONDAY)
    mailbox = FakeMailbox(fake_mails(), now=clock)
    answers = {s.marker: s.golden for s in SAMPLES}
    judge = ScriptedJudge({**answers, BY_KEY["results"].marker: ValueError("Results of the SEE")})
    check_mailbox(store, mailbox, judge, STUDENT, settings, now=clock)
    outage = ScriptedJudge({BY_KEY["results"].marker: JudgeUnavailable("RateLimitError")})
    clock.advance(hours=12)
    check_mailbox(store, mailbox, outage, STUDENT, settings, now=clock)
    logged = everything_logged(caplog)
    assert "check finished" in logged and "check stopped" in logged and "mail failed" in logged
    for sample in SAMPLES:
        assert sample.subject not in logged, sample.key
        assert sample.sender.split("<")[-1].rstrip(">") not in logged, sample.key
    for text in NEVER_KEPT + ["Results of the SEE", STUDENT_ADDRESS]:
        assert text not in logged


def test_the_database_holds_cards_not_mail(store: Store, settings: Settings, clock: Clock) -> None:
    store.connect(STUDENT, STUDENT_ADDRESS, MONDAY)
    check_mailbox(store, FakeMailbox(fake_mails(), now=clock), golden_judge(), STUDENT, settings,
                  now=clock)  # fmt: skip
    with store.engine.connect() as db:
        dumped = "\n".join(db.connection.iterdump())  # type: ignore[attr-defined]
    for text in NEVER_KEPT:
        assert text not in dumped, text
    assert "Eligibility: CGPA 7.0 and above" in dumped  # a checked card field is kept


def test_disconnecting_deletes_everything(store: Store, settings: Settings, clock: Clock) -> None:
    store.connect(STUDENT, STUDENT_ADDRESS, MONDAY)
    check_mailbox(store, FakeMailbox(fake_mails(), now=clock), ScriptedJudge({"": OTHER}),
                  STUDENT, settings, now=clock)  # fmt: skip
    store.forget(STUDENT)
    with store.engine.connect() as db:
        dumped = "\n".join(db.connection.iterdump())  # type: ignore[attr-defined]
    assert STUDENT not in dumped and STUDENT_ADDRESS not in dumped
