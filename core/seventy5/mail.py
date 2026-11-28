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
and once at startup so the Inbox is never empty on a fresh demo. On Lambda a turn has about 20
seconds, so the 1 PM job checks whom it can and "mail-continue" takes the rest over the next
turns: every mailbox not checked since the latest 1 PM or 9 PM, one cut short, or one Claude or
Gmail could not serve (tried again RETRY_AFTER later), least recently checked first (due()).
A mailbox whose Google grant was refused waits for the student to reconnect.
One card per mail card, even with two instances: the database allows one per external id.
"""

from __future__ import annotations

import logging
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any, Callable

from mailfilter import tools as mail_tools
from mailfilter.config import Settings as MailSettings
from mailfilter.config import parse_times
from mailfilter.contract import Card
from mailfilter.errors import (CheckInProgress, MailFilterError, NeedsReconnect, NotConnected,
                               TooSoon)
from mailfilter.fake import FakeMailbox
from mailfilter.judge import ClaudeJudge, Judge, ScriptedJudge
from mailfilter.run import RunResult, check_mailbox
from mailfilter.store import Store

from . import clock, mail_demo
from .config import settings
from .db import Database

log = logging.getLogger(__name__)
DEMO_ADDRESS = "student@mockcollege.edu.in"
DATE_ONLY_HOUR = 9  # an exam notice that names a day but no time is shown at 9 AM, as the LLM does
# One mail, at worst: Gmail's fetch plus one Claude answer (JUDGE_TIMEOUT, no retry). A check only
# starts a mail while this much time is left before its deadline.
JUDGE_TIMEOUT = 9.0
MAIL_RESERVE = 12.0
# "Check now" answers within this, then the rest goes on in the background (mail-continue).
CHECK_NOW_SECONDS = 20.0
# A check stopped by these (Claude timing out, overloaded or rate limited; Gmail or Google's
# sign-in down) is tried again this long after it started, still in the same slot.
RETRY_ERRORS = frozenset({"judge_unavailable", "gmail_unavailable"})
RETRY_AFTER = timedelta(minutes=10)
_sync_lock = threading.Lock()


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
        from mailfilter.store import metadata

        from .db import open_store

        url = settings.mailfilter_database_url
        if url.startswith("sqlite:///"):  # a file beside the others: make its folder first
            from pathlib import Path

            Path(url.removeprefix("sqlite:///")).parent.mkdir(parents=True, exist_ok=True)
        _store = open_store(Store, url, metadata)
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
    """gmail: the student's own mailbox. demo: the invented one, only for a student with no
    account of their own (the demo student, a laptop's). none: a real account that has not
    connected Google: never invented mail."""
    from . import google

    if google.has_gmail(db, sid):
        return "gmail"
    student = db.student(sid)
    return "demo" if student is not None and not student["auth_user_id"] else "none"


def mailbox_key(sid: int, which: str) -> str:
    """The mail filter's id for this student's mailbox. Demo and Gmail never share cards."""
    return f"{which}-{sid}"


def live_judge() -> Judge | None:
    """Claude for real mail: Bedrock when the team configured it, else the Anthropic API. One
    try with a short timeout: a mail that times out is simply judged at the next check."""
    import anthropic

    if settings.bedrock_model_id:
        client: Any = anthropic.AnthropicBedrockMantle(aws_region=settings.bedrock_region,
                                                        timeout=JUDGE_TIMEOUT, max_retries=0)
        return ClaudeJudge(client, settings.mail_model)
    if settings.anthropic_api_key:
        client = anthropic.Anthropic(api_key=settings.anthropic_api_key, timeout=JUDGE_TIMEOUT,
                                     max_retries=0)
        return ClaudeJudge(client, settings.llm_model)
    return None


def _parts(db: Database, sid: int, now: datetime,
           check_now: bool = False) -> tuple[str, Any, Judge, bool]:
    """(mailbox key, mailbox, judge, whether this is the demo's first "Check now")."""
    which = mode(db, sid)
    key = mailbox_key(sid, which)
    if which == "none":
        raise MailUnavailable("Connect Google in Settings to read your college mail.", 409)
    if which == "demo":
        demo = _demo_box(sid, now)
        first = check_now and not demo.second_delivered
        if first:
            _deliver_second(demo, now)  # before the judge is made: it copies the answers
        if store().connection(key) is None:
            store().connect(key, DEMO_ADDRESS, now)
        return key, demo.box, ScriptedJudge(demo.answers), first
    from . import google

    if google.needs_reconnect(db, sid) is not None:
        raise MailUnavailable("Reconnect Google in Settings: Google stopped letting 7even5ive "
                              "read your mail.", 409)
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
          deadline: float | None = None) -> dict[str, Any]:
    """One check of this student's mailbox, then its cards copied into 7even5ive's items.

    trigger "check_now" is the app's button: refused within 5 minutes of the last check. A
    deadline (time.monotonic()) stops the check in time, one whole mail before it, so Lambda
    always answers within its limit; what is left goes on at the next turn (mail-continue)."""
    now = clock.now()
    key, mailbox, judge, first_demo_check = _parts(db, sid, now, trigger == "check_now")
    if first_demo_check:
        # The demo's first "Check now" always runs and finds the new mail, even right after
        # the startup check; from then on (and always for real Gmail) the cooldown holds.
        force = True
    if trigger == "check_now" and not force:
        # The mail filter's own check_now has this rule but no deadline, so it is applied here.
        connection = store().connection(key)
        last = connection.last_run_at if connection else None
        if last is not None and now - last < mail_settings().check_now_cooldown:
            raise MailUnavailable("Checked a moment ago: try again in a few minutes.", 429)
    # The mail filter stops when fewer than 60 seconds are left: shift our deadline into that.
    time_left: Callable[[], float] | None = (
        (lambda: 60.0 + deadline - MAIL_RESERVE - time.monotonic())
        if deadline is not None else None)
    try:
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


def _room(deadline: float | None) -> bool:
    return deadline is None or deadline - time.monotonic() >= MAIL_RESERVE


def _aware(value: datetime | None) -> datetime | None:
    """The mail filter writes UTC; SQLite gives it back without the zone."""
    if value is None:
        return None
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)


def due(db: Database, now: datetime | None = None) -> list[int]:
    """The students whose mailbox the current slot has not finished, least recently checked
    first: not checked since the latest 1 PM or 9 PM (or never), cut short (the turn's time,
    the 200-mail cap), or stopped by Claude or Gmail being unreachable at least RETRY_AFTER ago.
    Left out: a mailbox Google cut off (it waits for the student to reconnect), and Gmail while
    this server has no Claude to read it. A few queries, whatever the number of students."""
    from sqlalchemy import select

    from mailfilter.store import connections, runs

    from . import google
    from .scheduler import latest_slot

    now = now or clock.now()
    slot = latest_slot(now, mail_settings().check_times)
    keys: dict[str, int] = {}
    claude: bool | None = None
    for row in db.mail_owners():  # mode() for everyone at once
        sid = int(row["id"])
        if google.GMAIL_SCOPE in str(row["scopes"] or "").split():
            if row["needs_reconnect_at"]:
                continue
            claude = live_judge() is not None if claude is None else claude
            if not claude:
                continue
            keys[mailbox_key(sid, "gmail")] = sid
        elif not row["auth_user_id"]:
            keys[mailbox_key(sid, "demo")] = sid
    boxes: dict[str, Any] = {}
    last_run: dict[str, Any] = {}
    names = list(keys)
    with store().engine.connect() as c:
        for start in range(0, len(names), 500):
            for r in c.execute(select(connections.c.student_id, connections.c.status,
                                      connections.c.last_run_at, connections.c.lease_until)
                               .where(connections.c.student_id.in_(names[start:start + 500]))):
                boxes[r.student_id] = r
        recent = [k for k, r in boxes.items() if r.last_run_at and _aware(r.last_run_at) >= slot]
        for start in range(0, len(recent), 500):
            for r in c.execute(select(runs.c.student_id, runs.c.started_at, runs.c.more,
                                      runs.c.error)
                               .where(runs.c.student_id.in_(recent[start:start + 500]),
                                      runs.c.started_at >= slot.astimezone(timezone.utc))
                               .order_by(runs.c.id)):
                last_run[r.student_id] = r  # the latest wins
    never = datetime.min.replace(tzinfo=timezone.utc)
    todo: list[tuple[datetime, int]] = []
    for key, sid in keys.items():
        box = boxes.get(key)
        if box is None:  # never checked (the mailbox is connected at its first check)
            todo.append((never, sid))
            continue
        last = _aware(box.last_run_at)
        if box.status != "connected":
            continue
        if last is None or last < slot:
            todo.append((last or never, sid))
            continue
        run = last_run.get(key)
        if run is None:
            # A check started since the slot and recorded nothing yet: still running, or it
            # was killed, and then it is due once its lease has run out.
            lease = _aware(box.lease_until)
            if lease is None or lease < now:
                todo.append((last, sid))
        elif run.more or (run.error in RETRY_ERRORS
                          and _aware(run.started_at) <= now - RETRY_AFTER):
            todo.append((last, sid))
    return [sid for _, sid in sorted(todo)]


def _sweep(db: Database, deadline: float | None, trigger: str) -> int:
    done = 0
    for sid in due(db):
        if not _room(deadline):
            break  # still due at the next turn, which carries on from here
        try:
            check(db, sid, trigger, deadline=deadline)
            done += 1
        except MailUnavailable as err:
            log.info("mail check skipped", extra={"student": sid, "status": err.status,
                                                  "trigger": trigger})
        except Exception as err:  # noqa: BLE001 - logged by type only; it may quote mail
            log.error("mail check crashed", extra={"student": sid, "error": type(err).__name__})
    return done


def check_all(db: Database, deadline: float | None = None) -> int:
    """The 1 PM and 9 PM job: every student's mailbox the slot has not finished (due()), as far
    as this turn's time goes; mail-continue takes the rest. One student's failure never stops
    the rest. Returns how many were checked."""
    return _sweep(db, deadline, "scheduled")


def unfinished(sid_key: str) -> bool:
    """True when this mailbox's last check stopped before the end: its time budget, the
    200-mail cap, or Claude or Gmail unreachable (RETRY_ERRORS)."""
    from sqlalchemy import select

    from mailfilter.store import runs

    with store().engine.connect() as c:
        last = c.execute(select(runs.c.more, runs.c.error).where(runs.c.student_id == sid_key)
                         .order_by(runs.c.id.desc()).limit(1)).first()
    return bool(last is not None and (last.more or last.error in RETRY_ERRORS))


def continue_unfinished(db: Database, deadline: float | None = None) -> int:
    """Every turn after a slot: the mailboxes it has not finished (due()), so a 1 PM check that
    ran out of time, or found Claude down, finishes long before 9 PM. On Lambda each turn has
    about 20 seconds, so a big first Gmail check finishes over a few minutes."""
    return _sweep(db, deadline, "continue")


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
            "event_at": event if card.deadline is not None else None, "details": card.details}


def sync_cards(db: Database, sid: int) -> int:
    """Copies this student's current mailbox's cards into items. Returns how many it holds.
    One copy at a time: a check and a sign-in finishing together never insert a card twice."""
    with _sync_lock:
        return _sync_cards(db, sid)


def _sync_cards(db: Database, sid: int) -> int:
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
            event_id = int(db.conn.execute("SELECT id FROM events WHERE student_id=? AND"
                                           " idempotency_key=?", (sid, external)).fetchone()["id"])
        db.mark_event(event_id, "done")
        # _sync_lock only covers this process: another instance copying the same card at the
        # same moment is stopped by the database (one card per external id).
        if db.insert_item_once(student_id=sid, event_id=event_id, source="gmail", route="mail",
                               relevance=None, created_at=clock.iso(now), external_id=external,
                               status="filed", **fields) is not None:
            return
        item = db.item_by_external(sid, external)  # theirs: brought up to date below
        if item is None:  # and already gone again (the student disconnected Gmail meanwhile)
            return
    changed = {k: v for k, v in fields.items() if item[k] != v}
    if item["status"] == "cancelled":
        # Retired when the student switched mailboxes, and current again (switched back).
        changed["status"] = "filed"
    if not changed:
        return
    if "due_at" in changed:
        # Reminders keep their distance from the new date (and a passed one is skipped).
        db.move_item_due(sid, item["id"], changed.pop("due_at"), clock.iso(now))
    if changed:
        db.update_item(sid, item["id"], **changed)  # done stays done; only retired comes back


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
    """Disconnecting Gmail removes everything read from it: the mail filter's records and the
    cards copied from them, with their reminders. The demo mailbox's cards come back."""
    key = mailbox_key(sid, "gmail")
    store().forget(key)
    prefix = f"mail:{key}:"
    with _sync_lock, db.tx() as c:
        rows = c.execute("SELECT id, external_id FROM items WHERE student_id=? AND route='mail'",
                         (sid,)).fetchall()
        for row in rows:
            if str(row["external_id"] or "").startswith(prefix):
                c.execute("DELETE FROM reminders WHERE item_id=?", (row["id"],))
                c.execute("DELETE FROM items WHERE id=?", (row["id"],))
                c.execute("DELETE FROM events WHERE idempotency_key=? AND student_id=?",
                          (row["external_id"], sid))
    sync_cards(db, sid)


# --- what the app shows -------------------------------------------------------------------------
def status(db: Database, sid: int) -> dict[str, Any]:
    from sqlalchemy import func, select

    from mailfilter.schedule import next_check
    from mailfilter.store import seen

    from . import google

    now = clock.now()
    which = mode(db, sid)
    key = mailbox_key(sid, which)
    connection = store().connection(key)
    with store().engine.connect() as c:
        left_out = int(c.execute(select(func.count()).select_from(seen).where(
            seen.c.student_id == key, seen.c.outcome.in_(("dropped", "skipped")))).scalar() or 0)
    last_run = connection.last_run_at if connection else None
    cooldown = mail_settings().check_now_cooldown
    box = connection.status if connection else "not_connected"
    # Google refused the grant (found by Classroom or Calendar as often as by Gmail): the
    # mailbox waits for the student to reconnect, whatever the mail filter last saw.
    if which == "gmail" and google.needs_reconnect(db, sid) is not None:
        box = "needs_reconnect"
    return {
        "mode": which,
        "connected": box == "connected",
        "status": box,
        "needs_reconnect": box == "needs_reconnect",
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
        return check(db, sid, "check_now", deadline=time.monotonic() + CHECK_NOW_SECONDS)
    except MailUnavailable as err:
        raise ValueError(str(err)) from err


def startup(db: Database, sid: int) -> list[str]:
    """Fills the Inbox on a fresh start (the demo morning). Log lines, counts only."""
    try:
        out = check(db, sid, "startup", deadline=time.monotonic() + CHECK_NOW_SECONDS)
    except MailUnavailable as err:
        return [f"mail      startup check skipped: {err}"]
    return [f"mail      {out['mode']} mailbox: {out['cards']} cards, {out['left_out']} left out"]

