"""College mail in the prototype: the mail filter's checks, and its cards as 7even5ive's cards.

Two mailboxes, one path:
- demo: no Google account connected. Invented mail from today (mail_demo.py), judged by the
  answers a correct judge gives. The first "Check now" delivers one more mail.
- gmail: the student connected Google with Gmail read-only (google.py). Their real college mail,
  judged by Claude Haiku 5.5 (Bedrock, or the Anthropic API), with the mail filter's code checks
  on every quote, date and link (decision 52).
Either way the mail filter decides what is a placement, an internship or an exam notice; this
module never reads a mail itself and never stores one (decision 56).

Why copy the cards into items (decision P2): one table drives "due this week", reminders, the
urgent call, the calendar and the briefing. A card is copied by its id (external_id
mail:<mailbox>:<card id>), updated in place when a newer mail changes it, and its reminders move
with a moved deadline. A card the student marked done stays done.
When: at 1 PM and 9 PM India time (scheduler job "mail"), on "Check now" (5-minute cooldown),
and once at startup so the Inbox is never empty on a fresh demo.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any, Callable

from mailfilter import tools as mail_tools
from mailfilter.config import Settings as MailSettings
from mailfilter.config import parse_times
from mailfilter.contract import Card
from mailfilter.errors import (CheckInProgress, MailFilterError, NeedsReconnect, NotConnected,
                               TooSoon)
from mailfilter.fake import FakeMailbox
from mailfilter.judge import ClaudeJudge, Judge, ScriptedJudge
from mailfilter.run import RunResult, check_mailbox, check_now
from mailfilter.store import Store

from . import clock, mail_demo
from .config import settings
from .db import Database

log = logging.getLogger(__name__)
DEMO_ADDRESS = "student@mockcollege.edu.in"
DATE_ONLY_HOUR = 9  # an exam notice that names a day but no time is shown at 9 AM, as the LLM does


class MailUnavailable(RuntimeError):
    """A check could not run. The message is said to the student as it is."""

    def __init__(self, message: str, status: int = 409) -> None:
        super().__init__(message)
        self.status = status


def mail_settings() -> MailSettings:
    return MailSettings(database_url=settings.mailfilter_database_url, model=settings.mail_model,
                        aws_region=settings.bedrock_region,
                        check_times=parse_times(settings.mail_check_times))


_store: Store | None = None


def store() -> Store:
    global _store
    if _store is None:
        url = settings.mailfilter_database_url
        if url.startswith("sqlite:///"):  # a file beside the others: make its folder first
            from pathlib import Path

            Path(url.removeprefix("sqlite:///")).parent.mkdir(parents=True, exist_ok=True)
        _store = Store(url)
    return _store


@dataclass
class _DemoBox:
    box: FakeMailbox
    answers: dict[str, Any] = field(default_factory=dict)
    second_delivered: bool = False


_demo: dict[int, _DemoBox] = {}


def _demo_box(sid: int, now: datetime) -> _DemoBox:
    found = _demo.get(sid)
    if found is None:
        mails = mail_demo.first_batch(now)
        found = _DemoBox(FakeMailbox([m.mail for m in mails], address=DEMO_ADDRESS,
                                     now=clock.now),
                         {m.marker: m.answer for m in mails})
        _demo[sid] = found
    return found


def _deliver_second(demo: _DemoBox, now: datetime) -> None:
    if demo.second_delivered:
        return
    for m in mail_demo.second_batch(now):
        demo.box.arrive(m.mail)
        demo.answers[m.marker] = m.answer
    demo.second_delivered = True


# --- which mailbox, which judge -----------------------------------------------------------------
def mode(db: Database, sid: int) -> str:
    from . import google

    return "gmail" if google.has_gmail(db, sid) else "demo"


def mailbox_key(sid: int, which: str) -> str:
    """The mail filter's id for this student's mailbox. Demo and Gmail never share cards."""
    return f"{which}-{sid}"


def live_judge() -> Judge | None:
    """Claude for real mail: Bedrock when the team configured it, else the Anthropic API."""
    if settings.bedrock_model_id:
        return ClaudeJudge.from_settings(mail_settings())
    if settings.anthropic_api_key:
        import anthropic

        client = anthropic.Anthropic(api_key=settings.anthropic_api_key, timeout=30.0,
                                     max_retries=2)
        return ClaudeJudge(client, settings.llm_model)  # type: ignore[arg-type]
    return None


def _parts(db: Database, sid: int, now: datetime,
           check_now: bool = False) -> tuple[str, Any, Judge, bool]:
    """(mailbox key, mailbox, judge, whether this is the demo's first "Check now")."""
    which = mode(db, sid)
    key = mailbox_key(sid, which)
    if which == "demo":
        demo = _demo_box(sid, now)
        first = check_now and not demo.second_delivered
        if first:
            _deliver_second(demo, now)  # before the judge is made: it copies the answers
        if store().connection(key) is None:
            store().connect(key, DEMO_ADDRESS, now)
        return key, demo.box, ScriptedJudge(demo.answers), first
    from . import google

    judge = live_judge()
    if judge is None:
        raise MailUnavailable("Reading real mail needs Claude: set BEDROCK_MODEL_ID or "
                              "ANTHROPIC_API_KEY on the server.", 503)
    email = google.account_email(db, sid)
    if store().connection(key) is None:
        store().connect(key, email, now)
    return key, google.gmail_mailbox(db, sid), judge, False


# --- checks ------------------------------------------------------------------------------------
def check(db: Database, sid: int, trigger: str = "scheduled", *, force: bool = False,
          budget_seconds: float | None = None) -> dict[str, Any]:
    """One check of this student's mailbox, then its cards copied into 7even5ive's items.

    trigger "check_now" is the app's button: refused within 5 minutes of the last check. A
    budget stops the check in time (Lambda answers within 30 s); the rest waits for the next."""
    now = clock.now()
    key, mailbox, judge, first_demo_check = _parts(db, sid, now, trigger == "check_now")
    if first_demo_check:
        # The demo's first "Check now" always runs and finds the new mail, even right after
        # the startup check; from then on (and always for real Gmail) the cooldown holds.
        force = True
    deadline = time.monotonic() + budget_seconds if budget_seconds else None
    # The mail filter stops when fewer than 60 seconds are left; give it our budget on top.
    time_left: Callable[[], float] | None = (
        (lambda: 60.0 + deadline - time.monotonic()) if deadline is not None else None)
    try:
        if trigger == "check_now":
            run = check_now(store(), mailbox, judge, key, mail_settings(), now=clock.now,
                            force=force)
        else:
            run = check_mailbox(store(), mailbox, judge, key, mail_settings(), trigger=trigger,
                                now=clock.now, time_left=time_left)
    except TooSoon as err:
        raise MailUnavailable("Checked a moment ago: try again in a few minutes.", 429) from err
    except CheckInProgress as err:
        raise MailUnavailable("A check is already running.", 409) from err
    except (NotConnected, NeedsReconnect) as err:
        raise MailUnavailable("College mail needs reconnecting: connect Google again in "
                              "Settings.", 409) from err
    except MailFilterError as err:
        log.warning("mail check failed", extra={"student": sid, "code": err.code})
        raise MailUnavailable("College mail can't be checked right now.", 503) from err
    copied = sync_cards(db, sid)
    return _summary(run, which=key.split("-", 1)[0], copied=copied)


def _summary(run: RunResult, which: str, copied: int) -> dict[str, Any]:
    return {"mode": which, "listed": run.listed, "judged": run.judged,
            "new": run.carded, "updated": run.updated, "left_out": run.dropped + run.skipped,
            "more": run.more, "error": run.error, "status": run.status, "cards": copied}


def check_all(db: Database, budget_seconds: float | None = None) -> int:
    """The 1 PM and 9 PM job: every student's mailbox. One student's failure never stops the
    rest. Returns how many were checked."""
    done = 0
    rows = db.conn.execute("SELECT id FROM students ORDER BY id").fetchall()
    for row in rows:
        try:
            check(db, int(row["id"]), "scheduled", budget_seconds=budget_seconds)
            done += 1
        except MailUnavailable as err:
            log.info("mail check skipped", extra={"student": row["id"], "status": err.status})
        except Exception as err:  # noqa: BLE001 - logged by type only; it may quote mail
            log.error("mail check crashed", extra={"student": row["id"],
                                                   "error": type(err).__name__})
    return done


# --- cards into items -----------------------------------------------------------------------------
def _iso(at: datetime | None, has_time: bool = True) -> str | None:
    if at is None:
        return None
    local = at.astimezone(clock.IST)
    if not has_time:
        local = local.replace(hour=DATE_ONLY_HOUR, minute=0)
    return clock.iso(local)


def item_fields(card: Card) -> dict[str, Any]:
    """A mail card as an item. Its due date is the deadline to register or apply when there is
    one, else the day of the drive, test or exam; the event's own date is kept beside it."""
    event = _iso(card.event_date, card.event_has_time)
    due = _iso(card.deadline) if card.deadline else event
    if card.deadline is not None:
        kind = "deadline"
    elif card.kind == "exam_notice" and event:
        kind = "exam"
    elif event:
        kind = "event"
    else:
        kind = "notice"
    return {"kind": kind, "subject": "Miscellaneous", "title": card.title, "due_at": due,
            "category": card.kind, "organisation": card.organisation, "role": card.role,
            "link": card.form_link, "mail_link": card.gmail_link, "summary": card.summary,
            "event_at": event if card.deadline is not None else None}


def sync_cards(db: Database, sid: int) -> int:
    """Copies this student's current mailbox's cards into items. Returns how many it holds."""
    now = clock.now()
    key = mailbox_key(sid, mode(db, sid))
    connection = store().connection(key)
    current: set[str] = set()
    if connection is not None:
        for row in store().cards(key):
            card = mail_tools.to_card(row, connection.email)
            external = f"mail:{key}:{card.id}"
            current.add(external)
            _upsert(db, sid, external, item_fields(card), now)
    _retire_others(db, sid, current, now)
    return len(current)


def _upsert(db: Database, sid: int, external: str, fields: dict[str, Any], now: datetime) -> None:
    item = db.item_by_external(sid, external)
    if item is None:
        # A row in events gives the card the provenance every write checks (gateway): it came
        # from a real mail. The payload holds ids only, never the mail's words.
        event_id = db.insert_event(sid, external, "gmail", {"mail_card": external},
                                   clock.iso(now))
        if event_id is None:  # the event exists from an earlier, interrupted copy
            event_id = int(db.conn.execute("SELECT id FROM events WHERE idempotency_key=?",
                                           (external,)).fetchone()["id"])
        db.mark_event(event_id, "done")
        db.insert_item(student_id=sid, event_id=event_id, source="gmail", route="mail",
                       relevance=None, created_at=clock.iso(now), external_id=external,
                       status="filed", **fields)
        return
    changed = {k: v for k, v in fields.items() if item[k] != v}
    if not changed:
        return
    if "due_at" in changed:
        # Reminders keep their distance from the new date (and a passed one is skipped).
        db.move_item_due(sid, item["id"], changed.pop("due_at"), clock.iso(now))
    if changed:
        db.update_item(sid, item["id"], **changed)  # status is never touched: done stays done


def _retire_others(db: Database, sid: int, keep: set[str], now: datetime) -> None:
    """Cards from a mailbox the student no longer uses (demo -> Gmail, or disconnected)."""
    rows = db.conn.execute("SELECT id, external_id FROM items WHERE student_id=? AND"
                           " route='mail' AND status IN ('filed', 'done')", (sid,)).fetchall()
    for row in rows:
        if row["external_id"] not in keep:
            db.move_item_due(sid, row["id"], None, clock.iso(now))  # skips its reminders
            db.update_item(sid, row["id"], status="cancelled")


def reset_demo(sid: int) -> None:
    """A fresh demo: the invented mailbox back to this morning. A real Gmail mailbox is kept."""
    store().forget(mailbox_key(sid, "demo"))
    _demo.pop(sid, None)


def forget(db: Database, sid: int) -> None:
    """Disconnecting Gmail removes everything the mail filter kept for that mailbox."""
    store().forget(mailbox_key(sid, "gmail"))
    sync_cards(db, sid)


# --- what the app shows -------------------------------------------------------------------------
def status(db: Database, sid: int) -> dict[str, Any]:
    from sqlalchemy import func, select

    from mailfilter.schedule import next_check
    from mailfilter.store import seen

    now = clock.now()
    which = mode(db, sid)
    key = mailbox_key(sid, which)
    connection = store().connection(key)
    with store().engine.connect() as c:
        left_out = int(c.execute(select(func.count()).select_from(seen).where(
            seen.c.student_id == key, seen.c.outcome.in_(("dropped", "skipped")))).scalar() or 0)
    last_run = connection.last_run_at if connection else None
    cooldown = mail_settings().check_now_cooldown
    return {
        "mode": which,
        "connected": connection is not None and connection.status == "connected",
        "status": connection.status if connection else "not_connected",
        "address": connection.email if connection and which == "gmail" else None,
        "checked_at": clock.iso(connection.last_ok_at) if connection and connection.last_ok_at
        else None,
        "next_check_at": clock.iso(next_check(now, mail_settings().check_times)),
        "check_now_after": clock.iso(last_run + cooldown)
        if last_run and now - last_run < cooldown else None,
        "left_out": left_out,
        "live_model": live_judge() is not None if which == "gmail" else False,
    }


def check_mail_now(db: Database, sid: int) -> dict[str, Any]:
    """The gateway tool: "check my mail now" from the app, Claude or the voice assistant."""
    try:
        return check(db, sid, "check_now", budget_seconds=20)
    except MailUnavailable as err:
        raise ValueError(str(err)) from err


def startup(db: Database, sid: int) -> list[str]:
    """Fills the Inbox on a fresh start (the demo morning). Log lines, counts only."""
    try:
        out = check(db, sid, "startup", budget_seconds=20)
    except MailUnavailable as err:
        return [f"mail      startup check skipped: {err}"]
    return [f"mail      {out['mode']} mailbox: {out['cards']} cards, {out['left_out']} left out"]

