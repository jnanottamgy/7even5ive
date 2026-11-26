"""Storage: SQLite locally, Supabase Postgres when deployed, behind named functions.

Why: callers only ever see these functions, and the same SQL runs on both engines; the only
differences (placeholders, id columns, transactions) live in _Conn and _schema below.
Every query takes student_id, so one student can never read another's rows.
Why one lock around every statement: the background loop (reminders, calls, mail) and the
request threads share one connection, and two threads' transactions on one connection would
interleave. Results are fetched while the lock is held, so no cursor outlives it.
Not: an ORM -- a dozen small queries are clearer as SQL. Not: Postgres in the default test
run -- SQLite needs no server; set PG_TEST_URL to run the same tests on Postgres.
"""

from __future__ import annotations

import json
import sqlite3
import threading
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator

from . import clock
from .config import settings

SCHEMA = """
-- call_consent_at: when the student turned the urgent call on (NULL = off).
-- quiet_start/quiet_end: their own quiet hours for calls, HH:MM India time (NULL = defaults).
CREATE TABLE IF NOT EXISTS students (
  id {pk}, name TEXT NOT NULL, wa_phone TEXT UNIQUE, mcp_token TEXT UNIQUE,
  branch TEXT, year INTEGER, interests TEXT,
  portal_id TEXT,  -- the student's id in PortMax
  call_consent_at TEXT, quiet_start TEXT, quiet_end TEXT
);
CREATE TABLE IF NOT EXISTS subjects (
  id {pk}, student_id BIGINT NOT NULL REFERENCES students(id),
  name TEXT NOT NULL, UNIQUE(student_id, name)
);
-- Every source (bot, Gmail, Classroom, portal) becomes one row here, once.
-- Why UNIQUE(idempotency_key): queues and webhooks redeliver, and the constraint is the dedupe.
CREATE TABLE IF NOT EXISTS events (
  id {pk}, student_id BIGINT NOT NULL, idempotency_key TEXT NOT NULL UNIQUE,
  source TEXT NOT NULL, payload TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'queued',
  attempts INTEGER NOT NULL DEFAULT 0, last_error TEXT, created_at TEXT NOT NULL
);
-- A card: what the student sees. route records which layer decided it (classroom/jev/llm).
-- Times are ISO strings in IST, so string order is time order on both engines.
CREATE TABLE IF NOT EXISTS items (
  id {pk}, student_id BIGINT NOT NULL, event_id BIGINT REFERENCES events(id),
  kind TEXT NOT NULL, subject TEXT NOT NULL, title TEXT NOT NULL, due_at TEXT,
  status TEXT NOT NULL DEFAULT 'filed', route TEXT NOT NULL, source TEXT NOT NULL,
  relevance REAL, created_at TEXT NOT NULL
);
-- Why a table of used nonces: an approval token works once, even inside its expiry.
CREATE TABLE IF NOT EXISTS used_approvals (nonce TEXT PRIMARY KEY, used_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS pending_approvals (
  nonce TEXT PRIMARY KEY, student_id BIGINT NOT NULL, action TEXT NOT NULL,
  args TEXT NOT NULL, token TEXT NOT NULL, created_at TEXT NOT NULL
);
-- Stand-in for Google Calendar. event_key is fixed per item, so a retried write
-- updates the same event instead of creating a duplicate.
CREATE TABLE IF NOT EXISTS calendar (
  event_key TEXT PRIMARY KEY, student_id BIGINT NOT NULL, title TEXT NOT NULL,
  starts_at TEXT NOT NULL
);
-- Opt-in reminders 7even5ive noted and will fire. UNIQUE(item_id, fire_at): asking twice
-- for the same reminder stores it once.
-- channel: push (a notification) or call (the opt-in urgent call). status: pending, sent,
-- cancelled, or skipped (the item was done, gone or past when it came due).
CREATE TABLE IF NOT EXISTS reminders (
  id {pk}, student_id BIGINT NOT NULL, item_id BIGINT NOT NULL REFERENCES items(id),
  fire_at TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'pending', sent_at TEXT,
  channel TEXT NOT NULL DEFAULT 'push',
  UNIQUE(item_id, fire_at)
);
-- Every gateway decision, allowed or not. Ids and names only, never the student's words.
CREATE TABLE IF NOT EXISTS audit (
  id {pk}, student_id BIGINT, tool TEXT NOT NULL, decision TEXT NOT NULL,
  reason TEXT, at TEXT NOT NULL
);
-- The outbox: every message 7even5ive sends the student (a reminder, a missed call). The
-- phone pulls it; a push only wakes the phone up and carries nothing.
CREATE TABLE IF NOT EXISTS notifications (
  id {pk}, student_id BIGINT NOT NULL, kind TEXT NOT NULL, title TEXT NOT NULL,
  body TEXT NOT NULL, item_id BIGINT, created_at TEXT NOT NULL
);
-- Phones that asked to be woken by Firebase when the outbox gets something.
CREATE TABLE IF NOT EXISTS devices (
  token TEXT PRIMARY KEY, student_id BIGINT NOT NULL, platform TEXT NOT NULL,
  created_at TEXT NOT NULL
);
-- Every urgent call: placed, answered, missed, voicemail, failed, or refused (with the rule
-- that refused it). Ids and codes only: no number, no words spoken.
CREATE TABLE IF NOT EXISTS calls (
  id {pk}, student_id BIGINT NOT NULL, item_id BIGINT, reminder_id BIGINT,
  status TEXT NOT NULL, reason TEXT, provider TEXT NOT NULL, provider_id TEXT,
  created_at TEXT NOT NULL, ended_at TEXT, duration_seconds INTEGER,
  fallback_sent INTEGER NOT NULL DEFAULT 0
);
-- When each background job last ran, so a restart does not run the 1 PM check twice.
CREATE TABLE IF NOT EXISTS jobs (
  name TEXT PRIMARY KEY, last_run_at TEXT NOT NULL, last_ok_at TEXT, last_error TEXT
);
"""

# Columns added after the first release. A fresh database gets them from SCHEMA above only if
# they are listed there too; an older database gets them here, once.
COLUMNS: dict[str, dict[str, str]] = {
    "reminders": {"channel": "TEXT NOT NULL DEFAULT 'push'"},
    "students": {"call_consent_at": "TEXT", "quiet_start": "TEXT", "quiet_end": "TEXT"},
}

INDEXES = """
CREATE INDEX IF NOT EXISTS notifications_student ON notifications(student_id, id);
CREATE INDEX IF NOT EXISTS reminders_due ON reminders(status, fire_at);
CREATE INDEX IF NOT EXISTS calls_provider ON calls(provider_id);
CREATE INDEX IF NOT EXISTS calls_student ON calls(student_id, created_at);
"""

try:  # psycopg is only needed against Postgres
    import psycopg
    from psycopg.rows import dict_row

    INTEGRITY: tuple[type[Exception], ...] = (sqlite3.IntegrityError, psycopg.IntegrityError)
except ImportError:  # pragma: no cover
    psycopg = None  # type: ignore[assignment]
    INTEGRITY = (sqlite3.IntegrityError,)


def _ist(value: str | None) -> str | None:
    """Any ISO time as the IST minutes string every column holds (naive means IST)."""
    from datetime import datetime

    if value is None:
        return None
    at = datetime.fromisoformat(value)
    return clock.iso(at if at.tzinfo else at.replace(tzinfo=clock.IST))


def _is_pg(url: str) -> bool:
    return url.startswith(("postgres://", "postgresql://"))


class _Result:
    """A statement's rows, fetched while the lock was held. Same surface as a cursor's
    fetchone/fetchall/rowcount, so callers do not change."""

    __slots__ = ("_rows", "rowcount")

    def __init__(self, rows: list[Any], rowcount: int) -> None:
        self._rows = rows
        self.rowcount = rowcount

    def fetchone(self) -> Any | None:
        return self._rows[0] if self._rows else None

    def fetchall(self) -> list[Any]:
        return list(self._rows)


class _Conn:
    """One small surface over both drivers: execute, executemany, transaction.

    Why autocommit plus explicit transactions: a single statement commits on its own, and
    tx() groups several, on both engines, with the same rollback-on-error behaviour.
    Why an RLock: a transaction holds it from BEGIN to COMMIT, so another thread's statement
    waits instead of landing inside it; re-entrant, so statements inside the transaction pass.
    """

    def __init__(self, url: str) -> None:
        self.lock = threading.RLock()
        self.pg = _is_pg(url)
        if self.pg:
            if psycopg is None:
                raise RuntimeError("DATABASE_URL is Postgres but psycopg is not installed")
            # prepare_threshold=None: Supabase's transaction pooler cannot keep prepared
            # statements between calls.
            self.raw: Any = psycopg.connect(url, autocommit=True, row_factory=dict_row,
                                            prepare_threshold=None)
        else:
            Path(url).parent.mkdir(parents=True, exist_ok=True)
            self.raw = sqlite3.connect(url, check_same_thread=False, isolation_level=None)
            self.raw.row_factory = sqlite3.Row
            self.raw.execute("PRAGMA foreign_keys = ON")

    def _sql(self, sql: str) -> str:
        return sql.replace("?", "%s") if self.pg else sql

    def execute(self, sql: str, args: Any = ()) -> _Result:
        with self.lock:
            cur = self.raw.execute(self._sql(sql), args)
            # Only statements that return rows have a description (SELECT, ... RETURNING).
            rows = cur.fetchall() if cur.description is not None else []
            return _Result(rows, cur.rowcount)

    def executemany(self, sql: str, rows: list[Any]) -> None:
        with self.lock:
            if self.pg:
                with self.raw.cursor() as cur:
                    cur.executemany(self._sql(sql), rows)
            else:
                self.raw.executemany(sql, rows)

    @contextmanager
    def transaction(self) -> Iterator[_Conn]:
        with self.lock:
            if self.pg:
                with self.raw.transaction():
                    yield self
                return
            self.raw.execute("BEGIN")
            try:
                yield self
            except BaseException:
                self.raw.execute("ROLLBACK")
                raise
            self.raw.execute("COMMIT")

    def script(self, sql: str) -> None:
        # Postgres runs a multi-statement string in one call when it has no parameters.
        with self.lock:
            if self.pg:
                self.raw.execute(sql)
            else:
                self.raw.executescript(sql)

    def columns(self, table: str) -> set[str]:
        if self.pg:
            rows = self.execute("SELECT column_name FROM information_schema.columns"
                                " WHERE table_name=?", (table,)).fetchall()
            return {r["column_name"] for r in rows}
        return {r["name"] for r in self.execute(f"PRAGMA table_info({table})").fetchall()}


def _schema(pg: bool) -> str:
    pk = "BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY" if pg else "INTEGER PRIMARY KEY"
    return SCHEMA.replace("{pk}", pk)


class Database:
    def __init__(self, url: str | None = None) -> None:
        self.conn = _Conn(url or settings.database_url)
        self.conn.script(_schema(self.conn.pg))
        self._migrate()
        self.conn.script(INDEXES)

    def _migrate(self) -> None:
        """Adds columns a database made by an older version lacks. Idempotent."""
        for table, wanted in COLUMNS.items():
            have = self.conn.columns(table)
            for name, decl in wanted.items():
                if name not in have:
                    self.conn.execute(f"ALTER TABLE {table} ADD COLUMN {name} {decl}")

    @contextmanager
    def tx(self) -> Iterator[_Conn]:
        with self.conn.transaction() as c:
            yield c

    # --- students -------------------------------------------------------------------
    def student_by_phone(self, phone: str) -> Any | None:
        return self.conn.execute("SELECT * FROM students WHERE wa_phone=?", (phone,)).fetchone()

    def student_by_token(self, token: str) -> Any | None:
        return self.conn.execute("SELECT * FROM students WHERE mcp_token=?", (token,)).fetchone()

    def student(self, student_id: int) -> Any:
        return self.conn.execute("SELECT * FROM students WHERE id=?", (student_id,)).fetchone()

    def subjects(self, student_id: int) -> list[str]:
        rows = self.conn.execute(
            "SELECT name FROM subjects WHERE student_id=? ORDER BY id", (student_id,)
        ).fetchall()
        return [r["name"] for r in rows]

    # --- events (the queue's durable record) ------------------------------------------
    def insert_event(self, student_id: int, key: str, source: str, payload: dict[str, Any],
                     now: str) -> int | None:
        """Returns the new id, or None for a redelivery we have already seen."""
        try:
            with self.tx() as c:
                row = c.execute(
                    "INSERT INTO events(student_id, idempotency_key, source, payload, created_at)"
                    " VALUES (?,?,?,?,?) RETURNING id",
                    (student_id, key, source, json.dumps(payload), now),
                ).fetchone()
                return int(row["id"])
        except INTEGRITY:
            return None

    def event(self, event_id: int) -> Any:
        return self.conn.execute("SELECT * FROM events WHERE id=?", (event_id,)).fetchone()

    def mark_event(self, event_id: int, status: str, error: str | None = None) -> None:
        with self.tx() as c:
            c.execute(
                "UPDATE events SET status=?, attempts=attempts+1, last_error=? WHERE id=?",
                (status, error, event_id),
            )

    # --- items ----------------------------------------------------------------------
    def insert_item(self, **row: Any) -> int:
        cols = ", ".join(row)
        marks = ", ".join("?" for _ in row)
        with self.tx() as c:
            new = c.execute(f"INSERT INTO items({cols}) VALUES ({marks}) RETURNING id",
                            tuple(row.values())).fetchone()
            return int(new["id"])

    def item_for_event(self, student_id: int, event_id: int) -> Any | None:
        return self.conn.execute(
            "SELECT * FROM items WHERE event_id=? AND student_id=?", (event_id, student_id)
        ).fetchone()

    def item(self, student_id: int, item_id: int) -> Any | None:
        return self.conn.execute(
            "SELECT * FROM items WHERE id=? AND student_id=?", (item_id, student_id)
        ).fetchone()

    def items(self, student_id: int, *, kinds: tuple[str, ...] | None = None,
              due_from: str | None = None, due_to: str | None = None,
              subject: str | None = None, status: str | None = "filed") -> list[Any]:
        sql = "SELECT * FROM items WHERE student_id=?"
        args: list[Any] = [student_id]
        if status:
            sql += " AND status=?"
            args.append(status)
        if kinds:
            sql += f" AND kind IN ({','.join('?' for _ in kinds)})"
            args.extend(kinds)
        if subject:
            sql += " AND subject=?"
            args.append(subject)
        if due_from:
            sql += " AND due_at >= ?"
            args.append(due_from)
        if due_to:
            sql += " AND due_at < ?"
            args.append(due_to)
        sql += " ORDER BY COALESCE(due_at, created_at), id"
        return self.conn.execute(sql, args).fetchall()

    def all_cards(self, student_id: int) -> list[Any]:
        return self.conn.execute(
            "SELECT * FROM items WHERE student_id=? ORDER BY id DESC LIMIT 100", (student_id,)
        ).fetchall()

    # --- approvals, calendar, audit ---------------------------------------------------
    def add_pending(self, nonce: str, student_id: int, action: str, args: dict[str, Any],
                    token: str, now: str) -> None:
        with self.tx() as c:
            c.execute("INSERT INTO pending_approvals VALUES (?,?,?,?,?,?)",
                      (nonce, student_id, action, json.dumps(args), token, now))

    def pending(self, student_id: int) -> list[Any]:
        return self.conn.execute(
            "SELECT * FROM pending_approvals WHERE student_id=? ORDER BY created_at",
            (student_id,),
        ).fetchall()

    def spend_nonce(self, nonce: str, now: str) -> bool:
        """True the first time only. The PRIMARY KEY makes a double spend impossible."""
        try:
            with self.tx() as c:
                c.execute("INSERT INTO used_approvals VALUES (?,?)", (nonce, now))
                c.execute("DELETE FROM pending_approvals WHERE nonce=?", (nonce,))
            return True
        except INTEGRITY:
            return False

    def upsert_calendar(self, key: str, student_id: int, title: str, starts_at: str) -> None:
        with self.tx() as c:
            c.execute(
                "INSERT INTO calendar VALUES (?,?,?,?) ON CONFLICT(event_key) DO UPDATE"
                " SET title=excluded.title, starts_at=excluded.starts_at",
                (key, student_id, title, starts_at),
            )

    def calendar(self, student_id: int) -> list[Any]:
        return self.conn.execute(
            "SELECT * FROM calendar WHERE student_id=? ORDER BY starts_at", (student_id,)
        ).fetchall()

    # --- reminders -------------------------------------------------------------------
    def add_reminder(self, student_id: int, item_id: int, fire_at: str,
                     channel: str = "push") -> int:
        # Asking again for the same moment keeps one row: the latest channel wins, and one that
        # was cancelled or skipped comes back. One already sent stays sent.
        with self.tx() as c:
            c.execute("INSERT INTO reminders(student_id, item_id, fire_at, channel)"
                      " VALUES (?,?,?,?) ON CONFLICT(item_id, fire_at) DO UPDATE SET"
                      " channel=excluded.channel,"
                      " status=CASE WHEN reminders.status='sent' THEN 'sent' ELSE 'pending' END,"
                      " sent_at=CASE WHEN reminders.status='sent' THEN reminders.sent_at"
                      " ELSE NULL END", (student_id, item_id, fire_at, channel))
            row = c.execute("SELECT id FROM reminders WHERE item_id=? AND fire_at=?",
                            (item_id, fire_at)).fetchone()
            return int(row["id"])

    def reminders(self, student_id: int) -> list[Any]:
        return self.conn.execute(
            "SELECT r.*, i.title, i.subject, i.due_at FROM reminders r JOIN items i ON i.id=r.item_id"
            " WHERE r.student_id=? AND r.status='pending' ORDER BY r.fire_at", (student_id,)
        ).fetchall()

    def cancel_reminder(self, student_id: int, reminder_id: int) -> bool:
        with self.tx() as c:
            cur = c.execute("UPDATE reminders SET status='cancelled' WHERE id=? AND student_id=?"
                            " AND status='pending'", (reminder_id, student_id))
            return cur.rowcount == 1

    def due_reminders(self, now: str) -> list[Any]:
        return self.conn.execute(
            "SELECT r.*, i.title, i.subject, i.due_at FROM reminders r JOIN items i ON i.id=r.item_id"
            " WHERE r.status='pending' AND r.fire_at <= ? ORDER BY r.fire_at", (now,)
        ).fetchall()

    def claim_reminder(self, reminder_id: int, now: str) -> bool:
        """True for exactly one caller, so two overlapping runs never fire it twice."""
        with self.tx() as c:
            cur = c.execute("UPDATE reminders SET status='sent', sent_at=? WHERE id=?"
                            " AND status='pending'", (now, reminder_id))
            return cur.rowcount == 1

    def skip_reminder(self, reminder_id: int, now: str) -> bool:
        """A reminder whose item is done, gone or already past: never sent, kept as skipped."""
        with self.tx() as c:
            cur = c.execute("UPDATE reminders SET status='skipped', sent_at=? WHERE id=?"
                            " AND status='pending'", (now, reminder_id))
            return cur.rowcount == 1

    # --- item status and dates ------------------------------------------------------------
    def set_item_status(self, student_id: int, item_id: int, was: str, now_status: str) -> bool:
        """Moves one of this student's items from one status to another; False if it was not
        in `was` (so a double tap or a stale screen changes nothing)."""
        with self.tx() as c:
            cur = c.execute("UPDATE items SET status=? WHERE id=? AND student_id=? AND status=?",
                            (now_status, item_id, student_id, was))
            return cur.rowcount == 1

    def move_item_due(self, student_id: int, item_id: int, new_due: str | None,
                      now: str, title: str | None = None) -> bool:
        """A card's date changed (an extension, a corrected mail, Classroom): pending reminders
        move by the same amount. One that would now be in the past fires at once; when the
        new date itself has passed, or the card lost its date, they are skipped.
        Returns False when the item is not this student's."""
        from datetime import datetime

        new_due = _ist(new_due)
        now = _ist(now) or now
        with self.tx() as c:
            row = c.execute("SELECT due_at FROM items WHERE id=? AND student_id=?",
                            (item_id, student_id)).fetchone()
            if row is None:
                return False
            old_due = row["due_at"]
            if title is None:
                c.execute("UPDATE items SET due_at=? WHERE id=?", (new_due, item_id))
            else:
                c.execute("UPDATE items SET due_at=?, title=? WHERE id=?",
                          (new_due, title, item_id))
            if old_due == new_due:
                return True
            pending = c.execute("SELECT id, fire_at FROM reminders WHERE item_id=? AND"
                                " status='pending' ORDER BY fire_at", (item_id,)).fetchall()
            if not pending:
                return True
            if new_due is None or old_due is None or new_due <= now:
                for r in pending:
                    c.execute("UPDATE reminders SET status='skipped', sent_at=? WHERE id=?",
                              (now, r["id"]))
                return True
            shift = datetime.fromisoformat(new_due) - datetime.fromisoformat(old_due)
            taken: set[str] = set()
            for r in pending:
                fire_at = clock.iso(datetime.fromisoformat(r["fire_at"]) + shift)
                fire_at = max(fire_at, now)  # same zone and format, so text order is time order
                if fire_at in taken:  # two reminders landed on the same minute: keep one
                    c.execute("UPDATE reminders SET status='skipped', sent_at=? WHERE id=?",
                              (now, r["id"]))
                    continue
                taken.add(fire_at)
                c.execute("UPDATE reminders SET fire_at=? WHERE id=?", (fire_at, r["id"]))
            return True

    # --- the outbox and the phones it wakes ---------------------------------------------
    def add_notification(self, student_id: int, kind: str, title: str, body: str,
                         item_id: int | None, now: str) -> int:
        with self.tx() as c:
            row = c.execute("INSERT INTO notifications(student_id, kind, title, body, item_id,"
                            " created_at) VALUES (?,?,?,?,?,?) RETURNING id",
                            (student_id, kind, title, body, item_id, now)).fetchone()
            return int(row["id"])

    def notifications(self, student_id: int, after: int, limit: int = 50) -> list[Any]:
        return self.conn.execute(
            "SELECT * FROM notifications WHERE student_id=? AND id>? ORDER BY id LIMIT ?",
            (student_id, after, limit)).fetchall()

    def latest_notification_id(self, student_id: int) -> int:
        row = self.conn.execute("SELECT MAX(id) AS m FROM notifications WHERE student_id=?",
                                (student_id,)).fetchone()
        return int(row["m"] or 0)

    def add_device(self, token: str, student_id: int, platform: str, now: str) -> None:
        # A token belongs to one phone; if it moved to another student, it moves with it.
        with self.tx() as c:
            c.execute("INSERT INTO devices(token, student_id, platform, created_at)"
                      " VALUES (?,?,?,?) ON CONFLICT(token) DO UPDATE SET"
                      " student_id=excluded.student_id, platform=excluded.platform",
                      (token, student_id, platform, now))

    def remove_device(self, token: str, student_id: int | None = None) -> bool:
        with self.tx() as c:
            if student_id is None:
                cur = c.execute("DELETE FROM devices WHERE token=?", (token,))
            else:
                cur = c.execute("DELETE FROM devices WHERE token=? AND student_id=?",
                                (token, student_id))
            return cur.rowcount == 1

    def device_tokens(self, student_id: int) -> list[str]:
        rows = self.conn.execute("SELECT token FROM devices WHERE student_id=? ORDER BY"
                                 " created_at", (student_id,)).fetchall()
        return [r["token"] for r in rows]

    # --- background jobs ---------------------------------------------------------------
    def job(self, name: str) -> Any | None:
        return self.conn.execute("SELECT * FROM jobs WHERE name=?", (name,)).fetchone()

    def job_ran(self, name: str, started: str, error: str | None) -> None:
        with self.tx() as c:
            c.execute("INSERT INTO jobs(name, last_run_at, last_ok_at, last_error) VALUES"
                      " (?,?,?,?) ON CONFLICT(name) DO UPDATE SET last_run_at=excluded.last_run_at,"
                      " last_ok_at=COALESCE(excluded.last_ok_at, jobs.last_ok_at),"
                      " last_error=excluded.last_error",
                      (name, started, None if error else started, error))

    def audit(self, student_id: int | None, tool: str, decision: str, reason: str,
              now: str) -> None:
        with self.tx() as c:
            c.execute("INSERT INTO audit(student_id, tool, decision, reason, at)"
                      " VALUES (?,?,?,?,?)", (student_id, tool, decision, reason, now))

    def audit_log(self, student_id: int) -> list[Any]:
        return self.conn.execute(
            "SELECT * FROM audit WHERE student_id=? ORDER BY id DESC LIMIT 50", (student_id,)
        ).fetchall()
