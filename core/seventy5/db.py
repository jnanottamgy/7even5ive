"""Storage: SQLite locally, Supabase Postgres when deployed, behind named functions.

Why: callers only ever see these functions, and the same SQL runs on both engines; the only
differences (placeholders, id columns, transactions) live in _Conn and _schema below.
Every query takes student_id, so one student can never read another's rows.
Not: an ORM -- a dozen small queries are clearer as SQL. Not: Postgres in the default test
run -- SQLite needs no server; set PG_TEST_URL to run the same tests on Postgres.
"""

from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator

from .config import settings

SCHEMA = """
CREATE TABLE IF NOT EXISTS students (
  id {pk}, name TEXT NOT NULL, wa_phone TEXT UNIQUE, mcp_token TEXT UNIQUE,
  branch TEXT, year INTEGER, interests TEXT,
  portal_id TEXT  -- the student's id in PortMax
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
CREATE TABLE IF NOT EXISTS reminders (
  id {pk}, student_id BIGINT NOT NULL, item_id BIGINT NOT NULL REFERENCES items(id),
  fire_at TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'pending', sent_at TEXT,
  UNIQUE(item_id, fire_at)
);
-- Every gateway decision, allowed or not. Ids and names only, never the student's words.
CREATE TABLE IF NOT EXISTS audit (
  id {pk}, student_id BIGINT, tool TEXT NOT NULL, decision TEXT NOT NULL,
  reason TEXT, at TEXT NOT NULL
);
"""

try:  # psycopg is only needed against Postgres
    import psycopg
    from psycopg.rows import dict_row

    INTEGRITY: tuple[type[Exception], ...] = (sqlite3.IntegrityError, psycopg.IntegrityError)
except ImportError:  # pragma: no cover
    psycopg = None  # type: ignore[assignment]
    INTEGRITY = (sqlite3.IntegrityError,)


def _is_pg(url: str) -> bool:
    return url.startswith(("postgres://", "postgresql://"))


class _Conn:
    """One small surface over both drivers: execute, executemany, transaction.

    Why autocommit plus explicit transactions: a single statement commits on its own, and
    tx() groups several, on both engines, with the same rollback-on-error behaviour.
    """

    def __init__(self, url: str) -> None:
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

    def execute(self, sql: str, args: Any = ()) -> Any:
        return self.raw.execute(self._sql(sql), args)

    def executemany(self, sql: str, rows: list[Any]) -> None:
        if self.pg:
            with self.raw.cursor() as cur:
                cur.executemany(self._sql(sql), rows)
        else:
            self.raw.executemany(sql, rows)

    @contextmanager
    def transaction(self) -> Iterator[_Conn]:
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
        if self.pg:
            self.raw.execute(sql)
        else:
            self.raw.executescript(sql)


def _schema(pg: bool) -> str:
    pk = "BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY" if pg else "INTEGER PRIMARY KEY"
    return SCHEMA.replace("{pk}", pk)


class Database:
    def __init__(self, url: str | None = None) -> None:
        self.conn = _Conn(url or settings.database_url)
        self.conn.script(_schema(self.conn.pg))

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
    def add_reminder(self, student_id: int, item_id: int, fire_at: str) -> int:
        with self.tx() as c:
            c.execute("INSERT INTO reminders(student_id, item_id, fire_at) VALUES (?,?,?)"
                      " ON CONFLICT(item_id, fire_at) DO NOTHING", (student_id, item_id, fire_at))
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

    def audit(self, student_id: int | None, tool: str, decision: str, reason: str,
              now: str) -> None:
        with self.tx() as c:
            c.execute("INSERT INTO audit(student_id, tool, decision, reason, at)"
                      " VALUES (?,?,?,?,?)", (student_id, tool, decision, reason, now))

    def audit_log(self, student_id: int) -> list[Any]:
        return self.conn.execute(
            "SELECT * FROM audit WHERE student_id=? ORDER BY id DESC LIMIT 50", (student_id,)
        ).fetchall()
