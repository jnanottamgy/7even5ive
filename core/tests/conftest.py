"""Shared test setup: a fresh database per test, the demo student seeded, PortMax isolated."""

from __future__ import annotations

import os
from datetime import datetime

import pytest

from seventy5 import clock, demo, tools
from seventy5.app import build
from seventy5.calls import LogCaller
from seventy5.jev import Picked, ScriptedDecider
from seventy5.llm import Proposal, ScriptedLLM
from seventy5.notify import LogSender

TABLES = ("audit, reminders, calendar, pending_approvals, used_approvals, notifications, devices,"
          " calls, jobs, google_accounts, connect_codes, items, events, subjects, students")


@pytest.fixture
def make_app(tmp_path, monkeypatch):
    """make_app(jev=..., llm=...) -> (app, student_id). Messages go to a LogSender and calls
    to a LogCaller unless the test passes its own."""
    from mailfilter.store import Store as MailStore
    from portmax.store import Store

    from seventy5 import google, mail

    monkeypatch.setattr(tools, "_portal", Store(f"sqlite:///{tmp_path.as_posix()}/pm.db"))
    monkeypatch.setattr(mail, "_store", MailStore(f"sqlite:///{tmp_path.as_posix()}/mail.db"))
    monkeypatch.setattr(mail, "_demo", {})
    monkeypatch.setattr(google, "_tokens", google._Tokens())
    url = os.environ.get("PG_TEST_URL") or str(tmp_path / "t.db")
    if url.startswith("postgres"):
        import psycopg

        with psycopg.connect(url, autocommit=True) as c:
            c.execute(f"DROP TABLE IF EXISTS {TABLES} CASCADE")

    def make(jev=None, llm=None, sender=None, caller=None):
        a = build(url, jev=jev or ScriptedDecider({}), llm=llm or ScriptedLLM({}),
                  caller=caller or LogCaller())
        a.sender = sender or LogSender()
        return a, demo.seed(a)

    yield make
    clock.freeze(None)


def file_item(a, sid, text="DBMS assignment due Fri", due="2030-01-04T23:59",
              subject="Database Management Systems", kind="deadline", title=None):
    """Files one dated item through the real cascade (Jev + LLM scripted). Returns its id."""
    from seventy5.ingress import accept

    a.cascade.jev = ScriptedDecider({"kind": Picked(kind, .95), "subject": Picked(subject, .9)})
    a.cascade.llm = ScriptedLLM({text: Proposal(kind, subject, title or text, due)})
    accept(a.db, a.queue, sid, "whatsapp", f"id-{text}-{due}", {"text": text})
    return a.work()[0].item_id


def at(year, month, day, hour=0, minute=0):
    return datetime(year, month, day, hour, minute, tzinfo=clock.IST)
