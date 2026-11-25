"""Storage: one SQLite file locally, behind named repository functions.

Why: the production database is not decided yet, so callers only ever see these
functions; swapping the engine touches this file alone. Every query takes student_id,
so one student can never read another's rows.
Not: an ORM -- ten small queries are clearer as SQL, and SQLite needs no server for the demo.
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
  id INTEGER PRIMARY KEY, name TEXT NOT NULL, wa_phone TEXT UNIQUE, mcp_token TEXT UNIQUE,
  branch TEXT, year INTEGER, interests TEXT,
  portal_id TEXT  -- the student's id in PortMax
);
CREATE TABLE IF NOT EXISTS subjects (
  id INTEGER PRIMARY KEY, student_id INTEGER NOT NULL REFERENCES students(id),
  name TEXT NOT NULL, UNIQUE(student_id, name)
);
-- Every source (bot, Gmail, Classroom, portal) becomes one row here, once.
-- Why UNIQUE(idempotency_key): queues and webhooks redeliver; the constraint is the dedupe.
CREATE TABLE IF NOT EXISTS events (
  id INTEGER PRIMARY KEY, student_id INTEGER NOT NULL, idempotency_key TEXT NOT NULL UNIQUE,
  source TEXT NOT NULL, payload TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'queued',
  attempts INTEGER NOT NULL DEFAULT 0, last_error TEXT, created_at TEXT NOT NULL
);
-- A card: what the student sees. route records which layer decided it (classroom/jev/llm).
CREATE TABLE IF NOT EXISTS items (
  id INTEGER PRIMARY KEY, student_id INTEGER NOT NULL, event_id INTEGER REFERENCES events(id),
  kind TEXT NOT NULL, subject TEXT NOT NULL, title TEXT NOT NULL, due_at TEXT,
  status TEXT NOT NULL DEFAULT 'filed', route TEXT NOT NULL, source TEXT NOT NULL,
  relevance REAL, created_at TEXT NOT NULL
);
-- Why a table of used nonces: an approval token works once, even inside its expiry.
CREATE TABLE IF NOT EXISTS used_approvals (nonce TEXT PRIMARY KEY, used_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS pending_approvals (
  nonce TEXT PRIMARY KEY, student_id INTEGER NOT NULL, action TEXT NOT NULL,
  args TEXT NOT NULL, token TEXT NOT NULL, created_at TEXT NOT NULL
);
-- Stand-in for Google Calendar. event_key is fixed per item, so a retried write
-- updates the same event instead of creating a duplicate.
CREATE TABLE IF NOT EXISTS calendar (
  event_key TEXT PRIMARY KEY, student_id INTEGER NOT NULL, title TEXT NOT NULL,
  starts_at TEXT NOT NULL
);
-- Every gateway decision, allowed or not. Ids and names only, never the student's words.
CREATE TABLE IF NOT EXISTS audit (
  id INTEGER PRIMARY KEY, student_id INTEGER, tool TEXT NOT NULL, decision TEXT NOT NULL,
  reason TEXT, at TEXT NOT NULL
);
"""


def _connect(path: str) -> sqlite3.Connection:
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


class Database:
    def __init__(self, path: str | None = None) -> None:
        self.conn = _connect(path or settings.db_path)
        self.conn.executescript(SCHEMA)

    @contextmanager
    def tx(self) -> Iterator[sqlite3.Connection]:
        with self.conn:
            yield self.conn

    # --- students -------------------------------------------------------------------
    def student_by_phone(self, phone: str) -> sqlite3.Row | None:
        return self.conn.execute("SELECT * FROM students WHERE wa_phone=?", (phone,)).fetchone()

    def student_by_token(self, token: str) -> sqlite3.Row | None:
        return self.conn.execute("SELECT * FROM students WHERE mcp_token=?", (token,)).fetchone()

    def student(self, student_id: int) -> sqlite3.Row:
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
                cur = c.execute(
                    "INSERT INTO events(student_id, idempotency_key, source, payload, created_at)"
                    " VALUES (?,?,?,?,?)",
                    (student_id, key, source, json.dumps(payload), now),
                )
                return cur.lastrowid
        except sqlite3.IntegrityError:
            return None

    def event(self, event_id: int) -> sqlite3.Row:
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
            cur = c.execute(f"INSERT INTO items({cols}) VALUES ({marks})", tuple(row.values()))
            return int(cur.lastrowid or 0)

    def item(self, student_id: int, item_id: int) -> sqlite3.Row | None:
        return self.conn.execute(
            "SELECT * FROM items WHERE id=? AND student_id=?", (item_id, student_id)
        ).fetchone()

    def items(self, student_id: int, *, kinds: tuple[str, ...] | None = None,
              due_from: str | None = None, due_to: str | None = None,
              subject: str | None = None, status: str | None = "filed") -> list[sqlite3.Row]:
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

    def all_cards(self, student_id: int) -> list[sqlite3.Row]:
        return self.conn.execute(
            "SELECT * FROM items WHERE student_id=? ORDER BY id DESC LIMIT 100", (student_id,)
        ).fetchall()

    # --- approvals, calendar, audit ---------------------------------------------------
    def add_pending(self, nonce: str, student_id: int, action: str, args: dict[str, Any],
                    token: str, now: str) -> None:
        with self.tx() as c:
            c.execute("INSERT INTO pending_approvals VALUES (?,?,?,?,?,?)",
                      (nonce, student_id, action, json.dumps(args), token, now))

    def pending(self, student_id: int) -> list[sqlite3.Row]:
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
        except sqlite3.IntegrityError:
            return False

    def upsert_calendar(self, key: str, student_id: int, title: str, starts_at: str) -> None:
        with self.tx() as c:
            c.execute(
                "INSERT INTO calendar VALUES (?,?,?,?) ON CONFLICT(event_key) DO UPDATE"
                " SET title=excluded.title, starts_at=excluded.starts_at",
                (key, student_id, title, starts_at),
            )

    def calendar(self, student_id: int) -> list[sqlite3.Row]:
        return self.conn.execute(
            "SELECT * FROM calendar WHERE student_id=? ORDER BY starts_at", (student_id,)
        ).fetchall()

    def audit(self, student_id: int | None, tool: str, decision: str, reason: str,
              now: str) -> None:
        with self.tx() as c:
            c.execute("INSERT INTO audit(student_id, tool, decision, reason, at)"
                      " VALUES (?,?,?,?,?)", (student_id, tool, decision, reason, now))

    def audit_log(self, student_id: int) -> list[sqlite3.Row]:
        return self.conn.execute(
            "SELECT * FROM audit WHERE student_id=? ORDER BY id DESC LIMIT 50", (student_id,)
        ).fetchall()
