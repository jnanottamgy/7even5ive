"""Storage: SQLite locally, Supabase Postgres when deployed, behind named functions.

Why: callers only ever see these functions, and the same SQL runs on both engines; the only
differences (placeholders, id columns, transactions) live in _Conn and _schema below.
Every query takes student_id, so one student can never read another's rows.
Why one lock around every statement: the background loop (reminders, calls, mail) and the
request threads share one connection, and two threads' transactions on one connection would
interleave. Results are fetched while the lock is held, so no cursor outlives it.
Why Supabase's pooler needs care (decision P21 in plan.md): Lambda reaches Supabase only over
IPv4, so through its shared pooler, in transaction mode. That pooler hands each transaction to
any server connection, so no prepared statements (prepare_threshold=None) and no pipelines; and
a connection idle while Lambda was frozen may be dead, so one idle for a while is checked with
a cheap SELECT 1 before use and replaced if it fails.
Why lock_down: Supabase publishes every table in `public` through its Data API, and the app
ships Supabase's publishable key. Row level security with no policies, and no grants for the
anon and authenticated roles, keep that API out of every table; this service connects as the
database owner, which bypasses row level security.
Not: an ORM -- a dozen small queries are clearer as SQL. Not: Postgres in the default test
run -- SQLite needs no server; set PG_TEST_URL to run the same tests on Postgres.
"""

from __future__ import annotations

import hashlib
import json
import re
import sqlite3
import threading
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterable, Iterator

from . import clock
from .config import settings

SCHEMA = """
-- call_consent_at: when the student turned the urgent call on (NULL = off).
-- quiet_start/quiet_end: their own quiet hours for calls, HH:MM India time (NULL = defaults).
-- auth_user_id: the Supabase Auth user (the access token's `sub`); NULL for the demo student.
-- username: unique, lowercase. token_hash: SHA-256 of the student's personal token (MCP), never
-- the token itself. mcp_token: unused, kept so databases made before accounts still open.
CREATE TABLE IF NOT EXISTS students (
  id {pk}, name TEXT NOT NULL, wa_phone TEXT UNIQUE, mcp_token TEXT UNIQUE,
  branch TEXT, year INTEGER, interests TEXT,
  portal_id TEXT,  -- the student's id in PortMax
  call_consent_at TEXT, quiet_start TEXT, quiet_end TEXT,
  auth_user_id TEXT, username TEXT, email TEXT, college TEXT, token_hash TEXT,
  token_created_at TEXT, created_at TEXT
);
CREATE TABLE IF NOT EXISTS subjects (
  id {pk}, student_id BIGINT NOT NULL REFERENCES students(id),
  name TEXT NOT NULL, UNIQUE(student_id, name)
);
-- Every source (bot, Gmail, Classroom, portal) becomes one row here, once per student.
-- Why UNIQUE(student_id, idempotency_key): queues and webhooks redeliver, and the constraint is
-- the dedupe; per student, because two classmates share a Classroom coursework id.
CREATE TABLE IF NOT EXISTS events (
  id {pk}, student_id BIGINT NOT NULL, idempotency_key TEXT NOT NULL,
  source TEXT NOT NULL, payload TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'queued',
  attempts INTEGER NOT NULL DEFAULT 0, last_error TEXT, created_at TEXT NOT NULL,
  UNIQUE(student_id, idempotency_key)
);
-- A card: what the student sees. route records which layer decided it (classroom/jev/llm).
-- Times are ISO strings in IST, so string order is time order on both engines.
CREATE TABLE IF NOT EXISTS items (
  id {pk}, student_id BIGINT NOT NULL, event_id BIGINT REFERENCES events(id),
  kind TEXT NOT NULL, subject TEXT NOT NULL, title TEXT NOT NULL, due_at TEXT,
  status TEXT NOT NULL DEFAULT 'filed', route TEXT NOT NULL, source TEXT NOT NULL,
  relevance REAL, created_at TEXT NOT NULL,
  -- Where a linked library's row came from ("bot:deadline:12") and the version last
  -- applied, so a change lands on the same card and an older one never wins.
  external_id TEXT, external_version BIGINT,
  -- College mail cards (mail.py): placement, internship or exam_notice; who and what; the
  -- form and the mail itself; one plain sentence; and the event's own date when the card's
  -- due_at is the deadline to register.
  category TEXT, organisation TEXT, role TEXT, link TEXT, mail_link TEXT, summary TEXT,
  event_at TEXT
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
-- One Google account per student (google.py): the refresh token encrypted at rest, the
-- scopes Google actually granted, and the address it belongs to. The phone never holds it.
-- needs_reconnect_at: when Google refused the grant for good (revoked, or a Testing-mode week
-- passed), and why; Gmail, Classroom and Calendar wait until the student connects again.
-- classroom_*: the Classroom job's progress through the current mail slot: its last complete
-- sync, its last attempt, and why that attempt failed (NULL when it did not).
CREATE TABLE IF NOT EXISTS google_accounts (
  student_id BIGINT PRIMARY KEY, email TEXT, scopes TEXT NOT NULL,
  refresh_token TEXT NOT NULL, connected_at TEXT NOT NULL,
  needs_reconnect_at TEXT, reconnect_reason TEXT,
  classroom_synced_at TEXT, classroom_tried_at TEXT, classroom_error TEXT
);
-- A sign-in in progress: the one-time `state` Google hands back, the PKCE verifier and where
-- Google must return to. Spent on first use; worthless after expires_at.
CREATE TABLE IF NOT EXISTS connect_codes (
  code TEXT PRIMARY KEY, student_id BIGINT NOT NULL, verifier TEXT NOT NULL,
  redirect_uri TEXT NOT NULL, expires_at TEXT NOT NULL
);
-- Linking WhatsApp (accounts.py): a short code the student sends to the bot. The bot's signed
-- webhook proves the number is theirs. One live code per student; spent on first use.
CREATE TABLE IF NOT EXISTS wa_link_codes (
  code TEXT PRIMARY KEY, student_id BIGINT NOT NULL, expires_at TEXT NOT NULL
);
-- Supabase users whose account was deleted: their access token stays valid for up to an hour,
-- and must not make a new profile in that time. Ids only.
CREATE TABLE IF NOT EXISTS deleted_accounts (
  auth_user_id TEXT PRIMARY KEY, deleted_at TEXT NOT NULL
);
-- The MCP connector (connector.py): AI apps (Claude Code, Codex) signing in as a student with
-- OAuth. Times are Unix seconds. Codes and tokens are kept only as their SHA-256.
-- oauth_clients: apps that registered themselves (RFC 7591), as the app described itself.
CREATE TABLE IF NOT EXISTS oauth_clients (
  client_id TEXT PRIMARY KEY, info TEXT NOT NULL, created_at BIGINT NOT NULL
);
-- oauth_requests: a sign-in page in progress, until the student signs in or 10 minutes pass.
CREATE TABLE IF NOT EXISTS oauth_requests (
  id TEXT PRIMARY KEY, client_id TEXT NOT NULL, params TEXT NOT NULL, expires_at BIGINT NOT NULL
);
-- oauth_codes: what the signed-in student's browser hands the app; spent once, 5 minutes.
CREATE TABLE IF NOT EXISTS oauth_codes (
  code_hash TEXT PRIMARY KEY, client_id TEXT NOT NULL, student_id BIGINT NOT NULL,
  params TEXT NOT NULL, expires_at BIGINT NOT NULL
);
-- oauth_grants: one connected app of one student (what Settings lists). Its access token (an
-- hour) and refresh token (90 days) are both replaced at every refresh; disconnecting deletes it.
CREATE TABLE IF NOT EXISTS oauth_grants (
  id {pk}, student_id BIGINT NOT NULL, client_id TEXT NOT NULL, client_name TEXT,
  access_hash TEXT NOT NULL, access_expires_at BIGINT NOT NULL,
  refresh_hash TEXT NOT NULL, refresh_expires_at BIGINT NOT NULL,
  scopes TEXT NOT NULL, resource TEXT, created_at TEXT NOT NULL, last_used_at TEXT
);
"""

# Every table above, in the order a student's rows are deleted (children before parents).
STUDENT_TABLES = ("audit", "calendar", "pending_approvals", "notifications", "devices", "calls",
                  "reminders", "items", "events", "subjects", "google_accounts", "connect_codes",
                  "wa_link_codes", "oauth_codes", "oauth_grants")
CORE_TABLES = (*STUDENT_TABLES, "students", "used_approvals", "jobs", "deleted_accounts",
               "oauth_clients", "oauth_requests")

# The connector's lookups: every token and code is found by its hash.
CONNECTOR_INDEXES = """
CREATE UNIQUE INDEX IF NOT EXISTS oauth_grants_access ON oauth_grants(access_hash);
CREATE UNIQUE INDEX IF NOT EXISTS oauth_grants_refresh ON oauth_grants(refresh_hash);
CREATE INDEX IF NOT EXISTS oauth_grants_student ON oauth_grants(student_id, id);
"""

# Columns added after the first release. A fresh database gets them from SCHEMA above only if
# they are listed there too; an older database gets them here, once.
COLUMNS: dict[str, dict[str, str]] = {
    "google_accounts": {"needs_reconnect_at": "TEXT", "reconnect_reason": "TEXT",
                        "classroom_synced_at": "TEXT", "classroom_tried_at": "TEXT",
                        "classroom_error": "TEXT"},
    "items": {"external_id": "TEXT", "external_version": "BIGINT", "category": "TEXT",
              "organisation": "TEXT", "role": "TEXT", "link": "TEXT", "mail_link": "TEXT",
              "summary": "TEXT", "event_at": "TEXT"},
    "reminders": {"channel": "TEXT NOT NULL DEFAULT 'push'"},
    "students": {"call_consent_at": "TEXT", "quiet_start": "TEXT", "quiet_end": "TEXT",
                 "auth_user_id": "TEXT", "username": "TEXT", "email": "TEXT", "college": "TEXT",
                 "token_hash": "TEXT", "token_created_at": "TEXT", "created_at": "TEXT"},
}

INDEXES = """
CREATE INDEX IF NOT EXISTS notifications_student ON notifications(student_id, id);
CREATE INDEX IF NOT EXISTS reminders_due ON reminders(status, fire_at);
CREATE INDEX IF NOT EXISTS calls_provider ON calls(provider_id);
CREATE INDEX IF NOT EXISTS calls_student ON calls(student_id, created_at);
CREATE INDEX IF NOT EXISTS items_external ON items(student_id, external_id);
CREATE UNIQUE INDEX IF NOT EXISTS students_auth_user ON students(auth_user_id);
CREATE UNIQUE INDEX IF NOT EXISTS students_username ON students(username);
CREATE UNIQUE INDEX IF NOT EXISTS students_token_hash ON students(token_hash);
CREATE UNIQUE INDEX IF NOT EXISTS events_student_key ON events(student_id, idempotency_key);
CREATE INDEX IF NOT EXISTS items_event ON items(event_id);
CREATE INDEX IF NOT EXISTS events_queued ON events(created_at) WHERE status='queued';
"""

try:  # psycopg is only needed against Postgres
    import psycopg
    from psycopg.rows import dict_row

    INTEGRITY: tuple[type[Exception], ...] = (sqlite3.IntegrityError, psycopg.IntegrityError)
    # A connection that died under us (the pooler closed it, Lambda was frozen, the network).
    DROPPED: tuple[type[Exception], ...] = (psycopg.OperationalError, psycopg.InterfaceError)
except ImportError:  # pragma: no cover
    psycopg = None  # type: ignore[assignment]
    INTEGRITY = (sqlite3.IntegrityError,)
    DROPPED = ()

# A Postgres connection unused for this long is checked (SELECT 1) before the next statement.
IDLE_CHECK_SECONDS = 20.0


def token_hash(token: str) -> str:
    """What the database keeps of a token or code: its SHA-256, never the value."""
    return hashlib.sha256(token.encode()).hexdigest()


# The MCP connector's tokens (connector.py) say what they are, so a leaked one is easy to spot.
ACCESS_PREFIX, REFRESH_PREFIX = "75a_", "75r_"


def _ist(value: str | None) -> str | None:
    """Any ISO time as the IST minutes string every column holds (naive means IST)."""
    from datetime import datetime

    if value is None:
        return None
    at = datetime.fromisoformat(value)
    return clock.iso(at if at.tzinfo else at.replace(tzinfo=clock.IST))


def is_pg(url: str) -> bool:
    return url.startswith(("postgres://", "postgresql://", "postgresql+psycopg://"))


_is_pg = is_pg


def pg_options(url: str) -> dict[str, Any]:
    """Connection settings for Postgres, the same for the core and the SQLAlchemy stores.

    prepare_threshold=None: Supabase's transaction pooler cannot keep prepared statements.
    sslmode=require: anything but a local server is reached encrypted or not at all.
    Keepalives and tcp_user_timeout: a connection the network silently dropped is noticed,
    not waited on forever.
    """
    from psycopg.conninfo import conninfo_to_dict

    given = conninfo_to_dict(url.replace("postgresql+psycopg://", "postgresql://", 1))
    host = str(given.get("host") or "")
    local = host in ("", "localhost", "127.0.0.1", "::1") or host.startswith("/")
    options: dict[str, Any] = {"prepare_threshold": None, "connect_timeout": 10,
                               "application_name": "7even5ive", "keepalives": 1,
                               "keepalives_idle": 30, "keepalives_interval": 10,
                               "keepalives_count": 3,
                               # Data sent but never acknowledged for 10 s: the connection is
                               # dead (dropped while Lambda was frozen). Without this, the check
                               # before use could wait past Lambda's whole time limit.
                               "tcp_user_timeout": 10000}
    if not local and "sslmode" not in given:
        options["sslmode"] = "require"
    return options


def sqlalchemy_url(url: str) -> str:
    """postgres://... and postgresql://... as SQLAlchemy's psycopg 3 URL; SQLite as it is."""
    for prefix in ("postgresql+psycopg://", "postgresql://", "postgres://"):
        if url.startswith(prefix):
            return "postgresql+psycopg://" + url[len(prefix):]
    return url


def sqlalchemy_engine(url: str) -> Any:
    """The engine for PortMax's and the mail filter's stores. On Postgres: pooler-safe (no
    prepared statements), checked before each use (pool_pre_ping), and small, because each warm
    Lambda keeps its own pool."""
    from sqlalchemy import create_engine

    if not is_pg(url):
        return create_engine(url)
    return create_engine(sqlalchemy_url(url), pool_size=2, max_overflow=3, pool_pre_ping=True,
                         pool_recycle=300, connect_args=pg_options(url))


def open_store(cls: Any, url: str, metadata: Any) -> Any:
    """A PortMax or mail filter Store on sqlalchemy_engine: built without its own engine, which
    would know nothing of the pooler, then given ours and its tables, locked down like the
    core's (lock_down) wherever the store is opened from."""
    store = cls(sqlalchemy_url(url), create=False)
    store.engine.dispose()
    store.engine = sqlalchemy_engine(url)
    metadata.create_all(store.engine)
    if is_pg(url):
        conn = _Conn(url)
        try:
            lock_down(conn, metadata.tables)
        finally:
            conn.close()
    return store


class BadInput(ValueError):
    """A value no column can hold: text with a NUL character (Postgres refuses it, SQLite would
    keep it) or half of a surrogate pair (not UTF-8), or a whole number past 64 bits. Raised
    before anything is sent, on both engines alike; the API answers it with a 400."""


_INT64 = 2**63


def _check(args: Any) -> None:
    for value in args if isinstance(args, (tuple, list)) else ():
        if isinstance(value, str):
            if "\x00" in value:
                raise BadInput("That text has a character that can't be stored.")
            if not value.isascii():
                try:
                    value.encode("utf-8")
                except UnicodeEncodeError:
                    raise BadInput("That text has a character that can't be stored.") from None
        elif isinstance(value, int) and not isinstance(value, bool) and not (
                -_INT64 <= value < _INT64):
            raise BadInput("That number is too large.")


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
    Why no retry of a failed statement: it may have run before the connection dropped. Only a
    connection found dead before anything is sent is replaced (_fresh).
    """

    def __init__(self, url: str) -> None:
        self.lock = threading.RLock()
        self.url = url
        self.pg = is_pg(url)
        self._depth = 0  # open transactions on this connection
        self._used = time.monotonic()
        if self.pg:
            if psycopg is None:
                raise RuntimeError("DATABASE_URL is Postgres but psycopg is not installed")
            self.raw: Any = self._connect()
        else:
            Path(url).parent.mkdir(parents=True, exist_ok=True)
            self.raw = sqlite3.connect(url, check_same_thread=False, isolation_level=None)
            self.raw.row_factory = sqlite3.Row
            self.raw.execute("PRAGMA foreign_keys = ON")

    def _connect(self) -> Any:
        url = self.url.replace("postgresql+psycopg://", "postgresql://", 1)
        return psycopg.connect(url, autocommit=True, row_factory=dict_row, **pg_options(url))

    def _fresh(self) -> None:
        """Before the first statement of a turn (never inside a transaction): a Postgres
        connection that is closed, broken, or idle long enough to have been dropped is
        checked, and replaced if it is dead. Called with the lock held."""
        if not self.pg or self._depth:
            return
        if not (self.raw.closed or self.raw.broken):
            if time.monotonic() - self._used < IDLE_CHECK_SECONDS:
                return
            try:
                self.raw.execute("SELECT 1")
                self._used = time.monotonic()
                return
            except DROPPED:
                pass
        try:
            self.raw.close()
        except Exception:  # noqa: BLE001 - it is being replaced either way
            pass
        self.raw = self._connect()
        self._used = time.monotonic()

    def _sql(self, sql: str) -> str:
        # psycopg reads % as the start of a placeholder: a literal one (LIKE 'x%') is doubled.
        return sql.replace("%", "%%").replace("?", "%s") if self.pg else sql

    def execute(self, sql: str, args: Any = ()) -> _Result:
        _check(args)
        with self.lock:
            self._fresh()
            cur = self.raw.execute(self._sql(sql), args)
            # Only statements that return rows have a description (SELECT, ... RETURNING).
            rows = cur.fetchall() if cur.description is not None else []
            self._used = time.monotonic()
            return _Result(rows, cur.rowcount)

    def executemany(self, sql: str, rows: list[Any]) -> None:
        for row in rows:
            _check(row)
        with self.lock:
            self._fresh()
            if self.pg:
                # One statement at a time: psycopg's executemany pipelines, which the
                # transaction pooler does not support outside a transaction.
                with self.raw.cursor() as cur:
                    for row in rows:
                        cur.execute(self._sql(sql), row)
            else:
                self.raw.executemany(sql, rows)
            self._used = time.monotonic()

    @contextmanager
    def transaction(self) -> Iterator[_Conn]:
        with self.lock:
            self._fresh()
            self._depth += 1
            try:
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
            finally:
                self._depth -= 1
                self._used = time.monotonic()

    def script(self, sql: str) -> None:
        # Postgres runs a multi-statement string in one call when it has no parameters.
        with self.lock:
            self._fresh()
            if self.pg:
                self.raw.execute(sql)
            else:
                self.raw.executescript(sql)
            self._used = time.monotonic()

    def columns(self, table: str) -> set[str]:
        if self.pg:
            rows = self.execute("SELECT column_name FROM information_schema.columns"
                                " WHERE table_schema='public' AND table_name=?",
                                (table,)).fetchall()
            return {r["column_name"] for r in rows}
        return {r["name"] for r in self.execute(f"PRAGMA table_info({table})").fetchall()}

    def close(self) -> None:
        with self.lock:
            try:
                self.raw.close()
            except Exception:  # noqa: BLE001 - closing is best effort
                pass


_NAME = re.compile(r"^[a-z_][a-z0-9_]*$")


def _ddl(conn: _Conn, sql: str) -> None:
    """A schema change. On Postgres it gives up after 5 s waiting for a lock (an idle
    transaction elsewhere) instead of holding up the start and everyone queued behind it;
    the next start tries again."""
    if not conn.pg:
        conn.execute(sql)
        return
    with conn.transaction() as c:
        c.execute("SET LOCAL lock_timeout = '5s'")
        c.execute(sql)


def lock_down(conn: _Conn, tables: Iterable[str]) -> list[str]:
    """Supabase only: row level security on, and no grants to anon or authenticated, for each
    of these tables (only these: never another app's). Idempotent and cheap: three catalogue
    reads, whatever the number of tables, then a statement only for a table that still needs one
    (so on every start after the first, none). Returns the tables it changed. A plain Postgres
    (tests, a laptop) has no such roles and only gets row level security."""
    if not conn.pg:
        return []
    wanted = sorted({t for t in tables if _NAME.match(t)})
    if not wanted:
        return []
    roles = [r["rolname"] for r in conn.execute(
        "SELECT rolname FROM pg_roles WHERE rolname IN ('anon','authenticated') ORDER BY rolname"
    ).fetchall()]
    marks = ",".join("?" for _ in wanted)
    table_rights = "'SELECT,INSERT,UPDATE,DELETE,TRUNCATE,REFERENCES,TRIGGER'"
    granted = " OR ".join(f"has_table_privilege('{role}', c.oid, {table_rights})" for role in roles)
    rows = conn.execute(
        f"SELECT c.relname AS name, c.relrowsecurity AS rls, {granted or 'false'} AS granted"
        " FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace"
        f" WHERE n.nspname='public' AND c.relkind IN ('r','p') AND c.relname IN ({marks})",
        wanted).fetchall()
    changed: list[str] = []
    for row in rows:
        if row["rls"] and not row["granted"]:
            continue
        if not row["rls"]:
            _ddl(conn, f'ALTER TABLE public."{row["name"]}" ENABLE ROW LEVEL SECURITY')
        if row["granted"]:
            _ddl(conn, f'REVOKE ALL ON TABLE public."{row["name"]}" FROM {", ".join(roles)}')
        changed.append(row["name"])
    if roles:
        # The identity columns' sequences: nothing outside this service needs them either.
        seq_granted = " OR ".join(
            f"has_sequence_privilege('{role}', c.oid, 'USAGE,SELECT,UPDATE')" for role in roles)
        for seq in conn.execute(
                f"SELECT c.relname AS name FROM pg_class c JOIN pg_namespace n ON"
                " n.oid=c.relnamespace JOIN pg_depend d ON d.objid=c.oid AND d.deptype IN ('a','i')"
                " JOIN pg_class t ON t.oid=d.refobjid WHERE n.nspname='public' AND c.relkind='S'"
                f" AND t.relname IN ({marks}) AND ({seq_granted})", wanted).fetchall():
            _ddl(conn, f'REVOKE ALL ON SEQUENCE public."{seq["name"]}" FROM {", ".join(roles)}')
    return changed


def _schema(pg: bool) -> str:
    pk = "BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY" if pg else "INTEGER PRIMARY KEY"
    return SCHEMA.replace("{pk}", pk)


class Database:
    def __init__(self, url: str | None = None) -> None:
        self.conn = _Conn(url or settings.database_url)
        self.conn.script(_schema(self.conn.pg))
        self._migrate()
        self._indexes(INDEXES + CONNECTOR_INDEXES)
        lock_down(self.conn, CORE_TABLES)

    def _indexes(self, script: str) -> None:
        """Creates the indexes this database lacks. On Postgres only the missing ones are run,
        each giving up after 5 s waiting for a lock: CREATE INDEX IF NOT EXISTS takes a SHARE
        lock on its table even when the index is there, so at every cold start it would queue
        behind any open write and hold up everything queued behind it."""
        if not self.conn.pg:
            self.conn.script(script)
            return
        have = {r["indexname"] for r in self.conn.execute(
            "SELECT indexname FROM pg_indexes WHERE schemaname='public'").fetchall()}
        for statement in (s.strip() for s in script.split(";")):
            name = re.search(r"IF NOT EXISTS\s+(\w+)", statement)
            if statement and (name is None or name.group(1) not in have):
                _ddl(self.conn, statement)

    def _migrate(self) -> None:
        """Adds columns a database made by an older version lacks. Idempotent."""
        for table, wanted in COLUMNS.items():
            have = self.conn.columns(table)
            for name, decl in wanted.items():
                if name not in have:
                    # Two instances starting at once may both find it missing: the second one
                    # must not fail its start over a column the first just added.
                    if self.conn.pg:
                        _ddl(self.conn,
                             f"ALTER TABLE {table} ADD COLUMN IF NOT EXISTS {name} {decl}")
                        continue
                    try:
                        _ddl(self.conn, f"ALTER TABLE {table} ADD COLUMN {name} {decl}")
                    except sqlite3.OperationalError as err:
                        if "duplicate column" not in str(err):
                            raise
        # Tokens used to be stored as they are: keep only their hash, so they still work.
        for row in self.conn.execute("SELECT id, mcp_token FROM students WHERE mcp_token IS NOT"
                                     " NULL AND token_hash IS NULL").fetchall():
            self.conn.execute("UPDATE students SET token_hash=?, mcp_token=NULL WHERE id=?",
                              (token_hash(str(row["mcp_token"])), row["id"]))
        if self.conn.pg and self.conn.execute(
                "SELECT 1 FROM pg_constraint WHERE conname='events_idempotency_key_key'"
                " AND conrelid='public.events'::regclass").fetchone() is not None:
            # Event keys used to be unique across all students (a classmate's Classroom work
            # would have been dropped as a repeat); now they are unique per student only.
            # Checked first: the ALTER locks the whole table, and is needed once in its life.
            _ddl(self.conn, "ALTER TABLE events DROP CONSTRAINT events_idempotency_key_key")
        # One card per external id (a mail card, a Classroom piece, a bot deadline): copies two
        # instances made at once fold into the first, then a unique index stops it for good.
        # Here, not in INDEXES: it can only be made once the copies are gone.
        self._unique_external_ids()

    def close(self) -> None:
        self.conn.close()

    @contextmanager
    def tx(self) -> Iterator[_Conn]:
        with self.conn.transaction() as c:
            yield c

    # --- students -------------------------------------------------------------------
    def student_by_phone(self, phone: str) -> Any | None:
        return self.conn.execute("SELECT * FROM students WHERE wa_phone=?", (phone,)).fetchone()

    def student_by_token(self, token: str) -> Any | None:
        """The student whose personal token this is (the demo's, or one made for MCP)."""
        if not token:
            return None
        return self.conn.execute("SELECT * FROM students WHERE token_hash=?",
                                 (token_hash(token),)).fetchone()

    def student_by_auth(self, auth_user_id: str) -> Any | None:
        return self.conn.execute("SELECT * FROM students WHERE auth_user_id=?",
                                 (auth_user_id,)).fetchone()

    def student_by_username(self, username: str) -> Any | None:
        return self.conn.execute("SELECT * FROM students WHERE username=?",
                                 (username.lower(),)).fetchone()

    def student(self, student_id: int) -> Any:
        return self.conn.execute("SELECT * FROM students WHERE id=?", (student_id,)).fetchone()

    def create_student(self, **fields: Any) -> int:
        """A new student row. Raises IntegrityError when the username, the Auth user or the
        token is already someone's (the unique indexes decide, so two at once cannot both win)."""
        cols = ", ".join(fields)
        marks = ", ".join("?" for _ in fields)
        with self.tx() as c:
            row = c.execute(f"INSERT INTO students({cols}) VALUES ({marks}) RETURNING id",
                            tuple(fields.values())).fetchone()
            return int(row["id"])

    def update_student(self, student_id: int, **fields: Any) -> None:
        if not fields:
            return
        sets = ", ".join(f"{k}=?" for k in fields)
        with self.tx() as c:
            c.execute(f"UPDATE students SET {sets} WHERE id=?", (*fields.values(), student_id))

    def set_subjects(self, student_id: int, names: list[str]) -> None:
        """The student's own subject list, replacing the one before. Cards keep their subject."""
        with self.tx() as c:
            c.execute("DELETE FROM subjects WHERE student_id=?", (student_id,))
            for name in names:
                c.execute("INSERT INTO subjects(student_id, name) VALUES (?,?)"
                          " ON CONFLICT(student_id, name) DO NOTHING", (student_id, name))

    def clear_student_data(self, student_id: int) -> None:
        """Everything the student has in this database except the student row itself."""
        with self.tx() as c:
            for table in STUDENT_TABLES:
                c.execute(f"DELETE FROM {table} WHERE student_id=?", (student_id,))

    def delete_student(self, student_id: int) -> bool:
        """The student and every row of theirs, in one transaction. False if there was none."""
        with self.tx() as c:
            for table in STUDENT_TABLES:
                c.execute(f"DELETE FROM {table} WHERE student_id=?", (student_id,))
            return c.execute("DELETE FROM students WHERE id=?", (student_id,)).rowcount == 1

    def audit_count(self, student_id: int, tool: str, since: str) -> int:
        """How many times this happened for the student since then (the demo's daily caps)."""
        row = self.conn.execute("SELECT COUNT(*) AS n FROM audit WHERE student_id=? AND tool=?"
                                " AND at >= ?", (student_id, tool, since)).fetchone()
        return int(row["n"])

    def mark_deleted(self, auth_user_id: str, now: str) -> None:
        with self.tx() as c:
            c.execute("INSERT INTO deleted_accounts VALUES (?,?) ON CONFLICT(auth_user_id)"
                      " DO NOTHING", (auth_user_id, now))

    def is_deleted(self, auth_user_id: str) -> bool:
        return self.conn.execute("SELECT 1 FROM deleted_accounts WHERE auth_user_id=?",
                                 (auth_user_id,)).fetchone() is not None

    def mailbox_students(self) -> list[int]:
        """Students with a mailbox to read: a Google account, or no account of their own (the
        demo's invented mailbox). Real accounts without Google have none and cost no query."""
        rows = self.conn.execute(
            "SELECT s.id FROM students s WHERE s.auth_user_id IS NULL OR EXISTS"
            " (SELECT 1 FROM google_accounts g WHERE g.student_id = s.id) ORDER BY s.id"
        ).fetchall()
        return [int(r["id"]) for r in rows]

    # --- WhatsApp linking ------------------------------------------------------------------
    def add_link_code(self, code: str, student_id: int, expires_at: str) -> None:
        with self.tx() as c:
            c.execute("DELETE FROM wa_link_codes WHERE student_id=?", (student_id,))
            c.execute("INSERT INTO wa_link_codes VALUES (?,?,?)", (code, student_id, expires_at))

    def link_whatsapp(self, code: str, phone: str, now: str) -> int | None:
        """Spends the code and gives its student this number (taken from whoever had it: the
        signed message proves it is this student's now). None if unknown, used or expired."""
        with self.tx() as c:
            # One statement spends it: of two deliveries at once, only one gets the row back.
            row = c.execute("DELETE FROM wa_link_codes WHERE code=? RETURNING student_id,"
                            " expires_at", (code,)).fetchone()
            if row is None or row["expires_at"] <= now:
                return None
            sid = int(row["student_id"])
            if c.execute("SELECT id FROM students WHERE id=?", (sid,)).fetchone() is None:
                return None
            c.execute("UPDATE students SET wa_phone=NULL WHERE wa_phone=? AND id<>?", (phone, sid))
            c.execute("UPDATE students SET wa_phone=? WHERE id=?", (phone, sid))
            return sid

    # --- the MCP connector (connector.py) -------------------------------------------------------
    def oauth_client(self, client_id: str) -> str | None:
        row = self.conn.execute("SELECT info FROM oauth_clients WHERE client_id=?",
                                (client_id,)).fetchone()
        return str(row["info"]) if row is not None else None

    def add_oauth_client(self, client_id: str, info: str, now: int, unused_before: int) -> None:
        """Registers an app. Registrations that never connected anyone are dropped after a
        day, so anonymous registrations cannot pile up."""
        with self.tx() as c:
            c.execute("DELETE FROM oauth_clients WHERE created_at < ? AND NOT EXISTS (SELECT 1"
                      " FROM oauth_grants g WHERE g.client_id = oauth_clients.client_id)",
                      (unused_before,))
            c.execute("INSERT INTO oauth_clients(client_id, info, created_at) VALUES (?,?,?)",
                      (client_id, info, now))

    def add_oauth_request(self, request_id: str, client_id: str, params: str, expires_at: int,
                          now: int) -> None:
        with self.tx() as c:
            c.execute("DELETE FROM oauth_requests WHERE expires_at < ?", (now,))
            c.execute("INSERT INTO oauth_requests(id, client_id, params, expires_at)"
                      " VALUES (?,?,?,?)", (request_id, client_id, params, expires_at))

    def oauth_request(self, request_id: str, now: int) -> Any | None:
        return self.conn.execute("SELECT * FROM oauth_requests WHERE id=? AND expires_at >= ?",
                                 (request_id, now)).fetchone()

    def end_oauth_request(self, request_id: str, now: int) -> Any | None:
        """Spends a sign-in request (allowed or cancelled): one statement, so only once."""
        return self.conn.execute("DELETE FROM oauth_requests WHERE id=? AND expires_at >= ?"
                                 " RETURNING client_id, params", (request_id, now)).fetchone()

    def add_oauth_code(self, code_hash: str, client_id: str, student_id: int, params: str,
                       expires_at: int, now: int) -> None:
        with self.tx() as c:
            c.execute("DELETE FROM oauth_codes WHERE expires_at < ?", (now,))
            c.execute("INSERT INTO oauth_codes(code_hash, client_id, student_id, params,"
                      " expires_at) VALUES (?,?,?,?,?)",
                      (code_hash, client_id, student_id, params, expires_at))

    def oauth_code(self, code_hash: str) -> Any | None:
        return self.conn.execute("SELECT * FROM oauth_codes WHERE code_hash=?",
                                 (code_hash,)).fetchone()

    def grant_from_code(self, code_hash: str, client_id: str, grant: dict[str, Any]) -> int | None:
        """Spends the code (once: one DELETE, so two exchanges cannot both win) and connects
        the app for its student. None if the code was spent, or its student is gone."""
        with self.tx() as c:
            row = c.execute("DELETE FROM oauth_codes WHERE code_hash=? AND client_id=?"
                            " RETURNING student_id", (code_hash, client_id)).fetchone()
            if row is None or c.execute("SELECT 1 FROM students WHERE id=?",
                                        (row["student_id"],)).fetchone() is None:
                return None
            cols = {"student_id": int(row["student_id"]), "client_id": client_id, **grant}
            new = c.execute(f"INSERT INTO oauth_grants({', '.join(cols)}) VALUES"
                            f" ({', '.join('?' for _ in cols)}) RETURNING id",
                            tuple(cols.values())).fetchone()
            return int(new["id"])

    def oauth_grant(self, column: str, hashed: str, now: int) -> Any | None:
        """The live grant whose access or refresh token this is (column: access or refresh)."""
        if column not in ("access", "refresh"):
            raise ValueError(column)
        return self.conn.execute(
            f"SELECT * FROM oauth_grants WHERE {column}_hash=? AND {column}_expires_at >= ?",
            (hashed, now)).fetchone()

    def rotate_grant(self, grant_id: int, old_refresh_hash: str, tokens: dict[str, Any]) -> bool:
        """New access and refresh tokens for a grant, only if the refresh token used is still its
        current one (two refreshes at once: one wins, the other must sign in again)."""
        sets = ", ".join(f"{k}=?" for k in tokens)
        with self.tx() as c:
            return c.execute(f"UPDATE oauth_grants SET {sets} WHERE id=? AND refresh_hash=?",
                             (*tokens.values(), grant_id, old_refresh_hash)).rowcount == 1

    def revoke_grant(self, hashed: str) -> None:
        """Disconnects the app holding this access or refresh token."""
        with self.tx() as c:
            c.execute("DELETE FROM oauth_grants WHERE access_hash=? OR refresh_hash=?",
                      (hashed, hashed))

    def student_by_grant(self, access_hash: str, now: int, now_iso: str,
                         seen_before: str) -> Any | None:
        """The student a live access token belongs to. Notes when the app was last used, at
        most once an hour (seen_before), so a busy app costs no write per request."""
        row = self.conn.execute(
            "SELECT g.id AS grant_id, g.last_used_at AS grant_used, s.* FROM oauth_grants g"
            " JOIN students s ON s.id = g.student_id"
            " WHERE g.access_hash=? AND g.access_expires_at >= ?", (access_hash, now)).fetchone()
        if row is not None and (row["grant_used"] is None or row["grant_used"] < seen_before):
            self.conn.execute("UPDATE oauth_grants SET last_used_at=? WHERE id=?",
                              (now_iso, row["grant_id"]))
        return row

    def grants(self, student_id: int) -> list[Any]:
        return self.conn.execute(
            "SELECT id, client_name, created_at, last_used_at FROM oauth_grants"
            " WHERE student_id=? ORDER BY id", (student_id,)).fetchall()

    def drop_grant(self, student_id: int, grant_id: int) -> bool:
        with self.tx() as c:
            return c.execute("DELETE FROM oauth_grants WHERE id=? AND student_id=?",
                             (grant_id, student_id)).rowcount == 1

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

    def item_by_external(self, student_id: int, external_id: str) -> Any | None:
        return self.conn.execute(
            "SELECT * FROM items WHERE student_id=? AND external_id=?", (student_id, external_id)
        ).fetchone()

    def update_item(self, student_id: int, item_id: int, **fields: Any) -> None:
        sets = ", ".join(f"{k}=?" for k in fields)
        with self.tx() as c:
            c.execute(f"UPDATE items SET {sets} WHERE id=? AND student_id=?",
                      (*fields.values(), item_id, student_id))

    def add_subject(self, student_id: int, name: str) -> None:
        with self.tx() as c:
            c.execute("INSERT INTO subjects(student_id, name) VALUES (?,?)"
                      " ON CONFLICT(student_id, name) DO NOTHING", (student_id, name))

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

    def pending_reminders_for(self, student_id: int, item_id: int) -> list[Any]:
        return self.conn.execute(
            "SELECT * FROM reminders WHERE student_id=? AND item_id=? AND status='pending'",
            (student_id, item_id),
        ).fetchall()

    def move_reminder(self, reminder_id: int, fire_at: str) -> None:
        with self.tx() as c:
            c.execute("UPDATE reminders SET fire_at=? WHERE id=? AND status='pending'",
                      (fire_at, reminder_id))

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

    # --- Google accounts and sign-ins in progress ------------------------------------------
    def save_google(self, student_id: int, email: str | None, scopes: str, refresh_token: str,
                    now: str) -> None:
        """refresh_token arrives encrypted (google.py); this table never sees it in the clear."""
        with self.tx() as c:
            c.execute("INSERT INTO google_accounts(student_id, email, scopes, refresh_token,"
                      " connected_at) VALUES (?,?,?,?,?) ON CONFLICT(student_id) DO UPDATE SET"
                      " email=excluded.email, scopes=excluded.scopes,"
                      " refresh_token=excluded.refresh_token, connected_at=excluded.connected_at",
                      (student_id, email, scopes, refresh_token, now))

    def google_account(self, student_id: int) -> Any | None:
        return self.conn.execute("SELECT * FROM google_accounts WHERE student_id=?",
                                 (student_id,)).fetchone()

    def google_students(self) -> list[int]:
        rows = self.conn.execute("SELECT student_id FROM google_accounts ORDER BY student_id"
                                 ).fetchall()
        return [int(r["student_id"]) for r in rows]

    def delete_google(self, student_id: int) -> bool:
        with self.tx() as c:
            cur = c.execute("DELETE FROM google_accounts WHERE student_id=?", (student_id,))
            return cur.rowcount == 1

    def add_connect_code(self, code: str, student_id: int, verifier: str, redirect_uri: str,
                         expires_at: str) -> None:
        with self.tx() as c:
            # One sign-in at a time per student: an older, unfinished one stops working.
            c.execute("DELETE FROM connect_codes WHERE student_id=?", (student_id,))
            c.execute("INSERT INTO connect_codes VALUES (?,?,?,?,?)",
                      (code, student_id, verifier, redirect_uri, expires_at))

    def peek_connect_code(self, code: str, now: str) -> Any | None:
        """The sign-in for this code if it is still waiting, without spending it."""
        row = self.conn.execute("SELECT * FROM connect_codes WHERE code=?", (code,)).fetchone()
        return row if row is not None and row["expires_at"] > now else None

    def take_connect_code(self, code: str, now: str) -> Any | None:
        """The sign-in for this code, once: the row is deleted as it is read. None when it is
        unknown, already used or expired."""
        with self.tx() as c:
            row = c.execute("SELECT * FROM connect_codes WHERE code=?", (code,)).fetchone()
            if row is None:
                return None
            c.execute("DELETE FROM connect_codes WHERE code=?", (code,))
        return row if row["expires_at"] > now else None

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

    # --- reliability (mail, Classroom, events) ------------------------------------------
    # What a later run of an event writes over the card it left for review (file_item).
    _REFILED = ("kind", "subject", "title", "due_at", "status", "route", "relevance",
                "event_id", "source", "external_id")

    def _index_exists(self, name: str) -> bool:
        sql = ("SELECT 1 FROM pg_indexes WHERE schemaname='public' AND indexname=?" if self.conn.pg
               else "SELECT 1 FROM sqlite_master WHERE type='index' AND name=?")
        return self.conn.execute(sql, (name,)).fetchone() is not None

    def _unique_external_ids(self) -> None:
        """Once in a database's life: every set of cards with the same student and external id
        (two instances copied one mail card at once, before this index existed) folds into its
        first card, then items_external_unique is made. One transaction, with the table closed
        to writes on Postgres, so no new copy slips in between; given up after 5 s waiting for
        that lock and tried again at the next start, like the other migrations."""
        if self._index_exists("items_external_unique"):
            return
        with self.tx() as c:
            if self.conn.pg:
                c.execute("SET LOCAL lock_timeout = '5s'")
                c.execute("LOCK TABLE items IN SHARE ROW EXCLUSIVE MODE")
            groups = c.execute(
                "SELECT student_id, external_id, MIN(id) AS keep FROM items WHERE external_id"
                " IS NOT NULL GROUP BY student_id, external_id HAVING COUNT(*) > 1").fetchall()
            for group in groups:
                keep = c.execute("SELECT id, due_at FROM items WHERE id=?",
                                 (group["keep"],)).fetchone()
                for copy in c.execute("SELECT id, due_at FROM items WHERE student_id=? AND"
                                      " external_id=? AND id<>? ORDER BY id",
                                      (group["student_id"], group["external_id"],
                                       keep["id"])).fetchall():
                    self._fold(c, int(group["student_id"]), copy, keep)
            c.execute("CREATE UNIQUE INDEX IF NOT EXISTS items_external_unique ON"
                      " items(student_id, external_id) WHERE external_id IS NOT NULL")

    @staticmethod
    def _fold(c: _Conn, student_id: int, copy: Any, keep: Any) -> None:
        """One copy of a card into the card it copies. Its reminders move over, as far before
        the card's date as they were before the copy's (the first card is the one later mail
        updated); one landing on a moment the card already has is dropped. Calls and messages
        about it point at the card. An approval waiting on the copy is dropped: its signed
        token names the copy. Then the copy goes."""
        from datetime import datetime

        copy_id, keep_id = int(copy["id"]), int(keep["id"])
        shift = None
        if copy["due_at"] and keep["due_at"] and copy["due_at"] != keep["due_at"]:
            shift = datetime.fromisoformat(keep["due_at"]) - datetime.fromisoformat(copy["due_at"])
        taken = {r["fire_at"] for r in c.execute("SELECT fire_at FROM reminders WHERE item_id=?",
                                                 (keep_id,)).fetchall()}
        for r in c.execute("SELECT id, fire_at, status FROM reminders WHERE item_id=? ORDER BY"
                           " id", (copy_id,)).fetchall():
            fire_at = r["fire_at"]
            if shift is not None and r["status"] == "pending":
                fire_at = clock.iso(datetime.fromisoformat(fire_at) + shift)
            if fire_at in taken:
                c.execute("DELETE FROM reminders WHERE id=?", (r["id"],))
                continue
            taken.add(fire_at)
            c.execute("UPDATE reminders SET item_id=?, fire_at=? WHERE id=?",
                      (keep_id, fire_at, r["id"]))
        c.execute("UPDATE calls SET item_id=? WHERE item_id=?", (keep_id, copy_id))
        c.execute("UPDATE notifications SET item_id=? WHERE item_id=?", (keep_id, copy_id))
        for p in c.execute("SELECT nonce, args FROM pending_approvals WHERE student_id=?",
                           (student_id,)).fetchall():
            try:
                named = json.loads(p["args"]).get("item_id")
            except (ValueError, AttributeError):
                continue
            if named is not None and str(named) == str(copy_id):
                c.execute("DELETE FROM pending_approvals WHERE nonce=?", (p["nonce"],))
        c.execute("DELETE FROM items WHERE id=?", (copy_id,))

    def insert_item_once(self, **row: Any) -> int | None:
        """A card with an external id, inserted once: None when the student already has a card
        with that id (another instance or another delivery made it a moment ago). The unique
        index decides, so two at once can never both insert."""
        cols = ", ".join(row)
        marks = ", ".join("?" for _ in row)
        with self.tx() as c:
            new = c.execute(f"INSERT INTO items({cols}) VALUES ({marks}) ON CONFLICT DO NOTHING"
                            " RETURNING id", tuple(row.values())).fetchone()
        return int(new["id"]) if new is not None else None

    def file_item(self, **row: Any) -> int:
        """The cascade's write: one card per event, and one per external id (a Classroom piece).
        A card already there is kept as it is, except one left for review, which this outcome
        replaces in place: an event run again (Classroom work retried, an event re-driven after
        a killed Lambda) files its card where the unreadable one was. Returns the card's id."""
        sid, event_id, external = row["student_id"], row.get("event_id"), row.get("external_id")
        with self.tx() as c:
            old = None
            if external is not None:
                old = c.execute("SELECT id, status FROM items WHERE student_id=? AND"
                                " external_id=?", (sid, external)).fetchone()
            if old is None and event_id is not None:
                old = c.execute("SELECT id, status FROM items WHERE student_id=? AND event_id=?"
                                " AND status='needs_review' ORDER BY id LIMIT 1",
                                (sid, event_id)).fetchone()
            if old is not None:
                if old["status"] == "needs_review" and row.get("status", "filed") != "needs_review":
                    fields = {k: row[k] for k in self._REFILED if k in row}
                    fields["status"] = row.get("status", "filed")  # the column's own default
                    sets = ", ".join(f"{k}=?" for k in fields)
                    c.execute(f"UPDATE items SET {sets} WHERE id=?", (*fields.values(), old["id"]))
                return int(old["id"])
            cols = ", ".join(row)
            marks = ", ".join("?" for _ in row)
            once = " ON CONFLICT DO NOTHING" if external is not None else ""
            new = c.execute(f"INSERT INTO items({cols}) VALUES ({marks}){once} RETURNING id",
                            tuple(row.values())).fetchone()
            if new is None:  # another worker filed this external id since the SELECT above
                new = c.execute("SELECT id FROM items WHERE student_id=? AND external_id=?",
                                (sid, external)).fetchone()
            return int(new["id"])

    def card_of_event(self, event_id: int) -> Any | None:
        """The card this event filed, unless it is only one left for review."""
        return self.conn.execute("SELECT * FROM items WHERE event_id=? AND status<>'needs_review'"
                                 " ORDER BY id LIMIT 1", (event_id,)).fetchone()

    def link_event_card(self, student_id: int, event_id: int, external_id: str) -> Any | None:
        """The card an event filed without its external id (filed before the cascade kept
        them) gets it, so later syncs find it. Returns the card, or None when there is none."""
        try:
            with self.tx() as c:
                row = c.execute("SELECT id FROM items WHERE student_id=? AND event_id=? AND"
                                " external_id IS NULL ORDER BY id LIMIT 1",
                                (student_id, event_id)).fetchone()
                if row is None:
                    return None
                c.execute("UPDATE items SET external_id=? WHERE id=?", (external_id, row["id"]))
        except INTEGRITY:  # another card has the id already
            return None
        return self.item_by_external(student_id, external_id)

    def stale_events(self, before: str, tries: int, limit: int) -> list[Any]:
        """Events still queued that arrived at or before `before` and were tried fewer than
        `tries` times, oldest first."""
        return self.conn.execute(
            "SELECT id, student_id, attempts FROM events WHERE status='queued' AND created_at <= ?"
            " AND attempts < ? ORDER BY id LIMIT ?", (before, tries, limit)).fetchall()

    def claim_event(self, event_id: int) -> int | None:
        """Counts one more try of a queued event: its tries so far, or None when it is no longer
        queued (another worker finished it)."""
        with self.tx() as c:
            row = c.execute("UPDATE events SET attempts=attempts+1 WHERE id=? AND status='queued'"
                            " RETURNING attempts", (event_id,)).fetchone()
        return int(row["attempts"]) if row is not None else None

    def requeue_event(self, student_id: int, key: str, payload: dict[str, Any]) -> int | None:
        """An event seen before goes back on the queue with its latest payload, as a fresh try.
        Returns its id, or None when there is no such event."""
        with self.tx() as c:
            row = c.execute("UPDATE events SET status='queued', attempts=0, last_error=NULL,"
                            " payload=? WHERE student_id=? AND idempotency_key=? RETURNING id",
                            (json.dumps(payload), student_id, key)).fetchone()
        return int(row["id"]) if row is not None else None

    def take_lease(self, name: str, now: str, free_before: str) -> bool:
        """One instance at a time for a job. True when the caller now holds `name`: nobody did,
        or the holder took it at or before `free_before` and has run out of time. A jobs row:
        its last_run_at is when the holder took the lease."""
        with self.tx() as c:
            row = c.execute("INSERT INTO jobs(name, last_run_at) VALUES (?,?) ON CONFLICT(name)"
                            " DO UPDATE SET last_run_at=excluded.last_run_at WHERE"
                            " jobs.last_run_at <= ? RETURNING name",
                            (name, now, free_before)).fetchone()
        return row is not None

    def mail_owners(self) -> list[Any]:
        """mailbox_students with what decides each one's mailbox (mail.mode), in one query:
        an account of their own or not, the Google scopes, and a grant Google refused."""
        return self.conn.execute(
            "SELECT s.id, s.auth_user_id, g.scopes, g.needs_reconnect_at FROM students s"
            " LEFT JOIN google_accounts g ON g.student_id = s.id"
            " WHERE s.auth_user_id IS NULL OR g.student_id IS NOT NULL ORDER BY s.id").fetchall()

    def google_grant_lost(self, student_id: int, refresh_token: str, reason: str, now: str,
                          title: str, body: str) -> bool:
        """Google refused this grant for good. True for the first caller only, and only while
        `refresh_token` (sealed) is still the stored grant: the refusal of a grant a reconnect
        already replaced changes nothing. That caller's message to the student is written in
        the same transaction, so it is said exactly once."""
        with self.tx() as c:
            cur = c.execute("UPDATE google_accounts SET needs_reconnect_at=?, reconnect_reason=?"
                            " WHERE student_id=? AND refresh_token=? AND needs_reconnect_at IS"
                            " NULL", (now, reason, student_id, refresh_token))
            if cur.rowcount != 1:
                return False
            c.execute("INSERT INTO notifications(student_id, kind, title, body, item_id,"
                      " created_at) VALUES (?,?,?,?,NULL,?)",
                      (student_id, "google", title, body, now))
            return True

    def google_reconnected(self, student_id: int) -> None:
        """A new grant: Google's refusal is forgotten, and Classroom is read again soon."""
        with self.tx() as c:
            c.execute("UPDATE google_accounts SET needs_reconnect_at=NULL, reconnect_reason=NULL,"
                      " classroom_synced_at=NULL, classroom_tried_at=NULL, classroom_error=NULL"
                      " WHERE student_id=?", (student_id,))

    def classroom_due(self, slot: str, retry_after: str) -> list[Any]:
        """Google accounts whose Classroom has not been read completely since `slot`, least
        recently tried first. One whose last try failed waits until `retry_after`; a grant
        Google refused waits for the student."""
        return self.conn.execute(
            "SELECT student_id, scopes FROM google_accounts WHERE needs_reconnect_at IS NULL"
            " AND (classroom_synced_at IS NULL OR classroom_synced_at < ?)"
            " AND (classroom_error IS NULL OR classroom_tried_at IS NULL"
            " OR classroom_tried_at <= ?)"
            " ORDER BY COALESCE(classroom_tried_at, ''), student_id", (slot, retry_after)
        ).fetchall()

    def claim_classroom(self, student_id: int, now: str) -> bool:
        """This student's Classroom for one caller per minute: two instances never read the
        same Classroom at once."""
        with self.tx() as c:
            cur = c.execute("UPDATE google_accounts SET classroom_tried_at=? WHERE student_id=?"
                            " AND needs_reconnect_at IS NULL AND (classroom_tried_at IS NULL OR"
                            " classroom_tried_at < ?)", (now, student_id, now))
            return cur.rowcount == 1

    def classroom_tried(self, student_id: int, started: str, done: bool,
                        error: str | None) -> None:
        """How a Classroom read went: done until the next slot (read completely, or refused:
        `error` says which), cut short (goes on at the next turn) or failed (`error`, tried
        again later)."""
        with self.tx() as c:
            if done:
                c.execute("UPDATE google_accounts SET classroom_synced_at=?, classroom_error=?"
                          " WHERE student_id=?", (started, error, student_id))
            else:
                c.execute("UPDATE google_accounts SET classroom_error=? WHERE student_id=?",
                          (error, student_id))
