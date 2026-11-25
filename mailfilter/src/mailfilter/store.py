"""Where the filter keeps each student's connection, which mail ids it has judged, and cards.

Mail bodies are never stored: a dropped mail leaves only its id and an outcome code, so the
same mail is never judged twice; a kept mail leaves only the card's checked fields. SQLite
serves development and tests; production points `database_url` at Postgres (Supabase, Mumbai).
Every time written is UTC; SQLite drops the zone, so reads put it back.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Literal

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Index,
    Integer,
    MetaData,
    String,
    Table,
    Text,
    UniqueConstraint,
    create_engine,
    delete,
    insert,
    or_,
    select,
    update,
)
from sqlalchemy.engine import Connection as DbConnection
from sqlalchemy.engine import Engine

from mailfilter.contract import ConnectionStatus, KeptKind
from mailfilter.timekit import aware, ist_midnight

metadata = MetaData()

connections = Table(
    "mail_connections",
    metadata,
    Column("student_id", String(64), primary_key=True),
    Column("email", String(320), nullable=True),
    Column("status", String(20), nullable=False),
    Column("connected_at", DateTime(timezone=True), nullable=False),
    Column("checked_through", DateTime(timezone=True), nullable=False),
    Column("last_run_at", DateTime(timezone=True), nullable=True),
    Column("last_ok_at", DateTime(timezone=True), nullable=True),
    Column("last_error", String(40), nullable=True),
    Column("lease_until", DateTime(timezone=True), nullable=True),
)

seen = Table(
    "mail_seen",
    metadata,
    Column("student_id", String(64), primary_key=True),
    Column("message_id", String(64), primary_key=True),
    Column("received_at", DateTime(timezone=True), nullable=True),
    Column("outcome", String(10), nullable=False),
    Column("reason", String(120), nullable=True),
    Column("attempts", Integer, nullable=False),
    Column("updated_at", DateTime(timezone=True), nullable=False),
)

cards = Table(
    "mail_cards",
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("student_id", String(64), nullable=False),
    Column("card_key", String(300), nullable=False),
    Column("kind", String(16), nullable=False),
    Column("title", String(200), nullable=False),
    Column("organisation", String(200), nullable=True),
    Column("role", String(200), nullable=True),
    Column("deadline", DateTime(timezone=True), nullable=True),
    Column("event_date", DateTime(timezone=True), nullable=True),
    Column("event_has_time", Boolean, nullable=False),
    Column("form_link", Text, nullable=True),
    Column("details", Text, nullable=True),
    Column("first_received_at", DateTime(timezone=True), nullable=False),
    Column("last_received_at", DateTime(timezone=True), nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False),
    Column("updated_at", DateTime(timezone=True), nullable=False),
    Column("message_id", String(64), nullable=False),
    Column("rfc822_id", String(300), nullable=True),
    Column("thread_id", String(64), nullable=False),
    Column("mails", Integer, nullable=False),
    UniqueConstraint("student_id", "card_key", name="uq_mail_cards_student_key"),
    Index("ix_mail_cards_student_deadline", "student_id", "deadline"),
)

runs = Table(
    "mail_runs",
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("student_id", String(64), nullable=False),
    Column("trigger", String(16), nullable=False),
    Column("started_at", DateTime(timezone=True), nullable=False),
    Column("finished_at", DateTime(timezone=True), nullable=False),
    Column("window_start", DateTime(timezone=True), nullable=True),
    Column("listed", Integer, nullable=False),
    Column("judged", Integer, nullable=False),
    Column("carded", Integer, nullable=False),
    Column("dropped", Integer, nullable=False),
    Column("skipped", Integer, nullable=False),
    Column("failed", Integer, nullable=False),
    Column("more", Boolean, nullable=False),
    Column("error", String(40), nullable=True),
    Index("ix_mail_runs_student_started", "student_id", "started_at"),
)

Outcome = Literal["carded", "dropped", "skipped", "gone", "retry", "failed"]
FINAL: frozenset[str] = frozenset({"carded", "dropped", "skipped", "gone", "failed"})


def _db(value: datetime | None) -> datetime | None:
    return None if value is None else aware(value).astimezone(UTC)


def _read(value: datetime | None) -> datetime | None:
    return None if value is None else aware(value)


@dataclass(frozen=True)
class Connection:
    student_id: str
    email: str | None
    status: ConnectionStatus
    connected_at: datetime
    checked_through: datetime
    last_run_at: datetime | None
    last_ok_at: datetime | None
    last_error: str | None


@dataclass(frozen=True)
class SeenState:
    outcome: str
    attempts: int


@dataclass(frozen=True)
class CardDraft:
    key: str
    kind: KeptKind
    title: str
    organisation: str | None
    role: str | None
    deadline: datetime | None
    event_date: datetime | None
    event_has_time: bool
    form_link: str | None
    details: str | None
    received_at: datetime
    message_id: str
    rfc822_id: str | None
    thread_id: str
    # A forward repeats old news: it fills gaps in a card but never overrides it.
    authoritative: bool


@dataclass(frozen=True)
class CardRow:
    id: int
    kind: KeptKind
    title: str
    organisation: str | None
    role: str | None
    deadline: datetime | None
    event_date: datetime | None
    event_has_time: bool
    form_link: str | None
    details: str | None
    first_received_at: datetime
    last_received_at: datetime
    created_at: datetime
    updated_at: datetime
    message_id: str
    rfc822_id: str | None
    mails: int


@dataclass(frozen=True)
class RunRecord:
    student_id: str
    trigger: str
    started_at: datetime
    finished_at: datetime
    window_start: datetime | None
    listed: int
    judged: int
    carded: int
    dropped: int
    skipped: int
    failed: int
    more: bool
    error: str | None


_MERGED = ("organisation", "role", "deadline", "event_date", "form_link", "details")


class Store:
    def __init__(self, database_url: str = "sqlite:///mailfilter.db", *, create: bool = True):
        self.engine: Engine = create_engine(database_url)
        if create:
            metadata.create_all(self.engine)

    # Connections ---------------------------------------------------------------------------

    def connect(self, student_id: str, email: str | None, now: datetime) -> None:
        """Connect (or reconnect) a mailbox. A new mailbox is read from the start of today."""
        existing = self.connection(student_id)
        with self.engine.begin() as db:
            if existing is None:
                db.execute(
                    insert(connections).values(
                        student_id=student_id,
                        email=email,
                        status="connected",
                        connected_at=_db(now),
                        checked_through=_db(ist_midnight(now)),
                    )
                )
                return
            changed = bool(email and existing.email and email.lower() != existing.email.lower())
            values: dict[str, object] = {
                "status": "connected",
                "email": email or existing.email,
                "last_error": None,
                "connected_at": _db(now),
            }
            if changed:
                # Ids are per mailbox: another account's judged ids mean nothing here.
                db.execute(delete(seen).where(seen.c.student_id == student_id))
                values["checked_through"] = _db(ist_midnight(now))
            db.execute(
                update(connections).where(connections.c.student_id == student_id).values(**values)
            )

    def connection(self, student_id: str) -> Connection | None:
        with self.engine.connect() as db:
            row = db.execute(
                select(connections).where(connections.c.student_id == student_id)
            ).first()
        if row is None:
            return None
        return Connection(
            student_id=row.student_id,
            email=row.email,
            status=row.status,
            connected_at=aware(row.connected_at),
            checked_through=aware(row.checked_through),
            last_run_at=_read(row.last_run_at),
            last_ok_at=_read(row.last_ok_at),
            last_error=row.last_error,
        )

    def connected_students(self) -> list[str]:
        """Connected mailboxes, the longest-unchecked first."""
        with self.engine.connect() as db:
            rows = db.execute(
                select(connections.c.student_id, connections.c.last_run_at).where(
                    connections.c.status == "connected"
                )
            ).all()
        never = datetime.min.replace(tzinfo=UTC)
        ordered = sorted(rows, key=lambda r: (_read(r.last_run_at) or never, r.student_id))
        return [row.student_id for row in ordered]

    def acquire(self, student_id: str, now: datetime, lease: timedelta) -> bool:
        """Hold the mailbox for one check; False when another check holds it."""
        with self.engine.begin() as db:
            result = db.execute(
                update(connections)
                .where(
                    connections.c.student_id == student_id,
                    or_(connections.c.lease_until.is_(None), connections.c.lease_until < _db(now)),
                )
                .values(lease_until=_db(now + lease))
            )
            return result.rowcount == 1

    def release(self, student_id: str) -> None:
        with self.engine.begin() as db:
            db.execute(
                update(connections)
                .where(connections.c.student_id == student_id)
                .values(lease_until=None)
            )

    def finish(
        self,
        student_id: str,
        now: datetime,
        checked_through: datetime,
        status: ConnectionStatus,
        error: str | None,
    ) -> None:
        values: dict[str, object] = {
            "checked_through": _db(checked_through),
            "last_run_at": _db(now),
            "status": status,
            "last_error": error,
        }
        if error is None:
            values["last_ok_at"] = _db(now)
        with self.engine.begin() as db:
            db.execute(
                update(connections).where(connections.c.student_id == student_id).values(**values)
            )

    def record_run(self, record: RunRecord) -> None:
        with self.engine.begin() as db:
            db.execute(
                insert(runs).values(
                    student_id=record.student_id,
                    trigger=record.trigger,
                    started_at=_db(record.started_at),
                    finished_at=_db(record.finished_at),
                    window_start=_db(record.window_start),
                    listed=record.listed,
                    judged=record.judged,
                    carded=record.carded,
                    dropped=record.dropped,
                    skipped=record.skipped,
                    failed=record.failed,
                    more=record.more,
                    error=record.error,
                )
            )

    def runs(self, student_id: str) -> list[RunRecord]:
        with self.engine.connect() as db:
            rows = db.execute(
                select(runs).where(runs.c.student_id == student_id).order_by(runs.c.id)
            ).all()
        return [
            RunRecord(
                student_id=row.student_id,
                trigger=row.trigger,
                started_at=aware(row.started_at),
                finished_at=aware(row.finished_at),
                window_start=_read(row.window_start),
                listed=row.listed,
                judged=row.judged,
                carded=row.carded,
                dropped=row.dropped,
                skipped=row.skipped,
                failed=row.failed,
                more=row.more,
                error=row.error,
            )
            for row in rows
        ]

    # Mail ----------------------------------------------------------------------------------

    def seen_states(self, student_id: str, message_ids: Iterable[str]) -> dict[str, SeenState]:
        wanted = list(dict.fromkeys(message_ids))
        found: dict[str, SeenState] = {}
        with self.engine.connect() as db:
            for start in range(0, len(wanted), 500):
                chunk = wanted[start : start + 500]
                for row in db.execute(
                    select(seen.c.message_id, seen.c.outcome, seen.c.attempts).where(
                        seen.c.student_id == student_id, seen.c.message_id.in_(chunk)
                    )
                ):
                    found[row.message_id] = SeenState(row.outcome, row.attempts)
        return found

    def record_mail(
        self,
        student_id: str,
        message_id: str,
        received_at: datetime | None,
        outcome: Outcome,
        reason: str | None,
        now: datetime,
        card: CardDraft | None = None,
    ) -> Literal["created", "updated"] | None:
        """One mail's outcome and, for a kept mail, its card, in a single transaction."""
        with self.engine.begin() as db:
            previous = db.execute(
                select(seen.c.attempts).where(
                    seen.c.student_id == student_id, seen.c.message_id == message_id
                )
            ).first()
            attempts = (previous.attempts if previous else 0) + (
                1 if outcome in ("retry", "failed") else 0
            )
            values = {
                "received_at": _db(received_at),
                "outcome": outcome,
                "reason": reason[:120] if reason else None,
                "attempts": attempts,
                "updated_at": _db(now),
            }
            if previous is None:
                db.execute(
                    insert(seen).values(student_id=student_id, message_id=message_id, **values)
                )
            else:
                db.execute(
                    update(seen)
                    .where(seen.c.student_id == student_id, seen.c.message_id == message_id)
                    .values(**values)
                )
            return None if card is None else self._merge_card(db, student_id, card, now)

    def attempts(self, student_id: str, message_id: str) -> int:
        state = self.seen_states(student_id, [message_id]).get(message_id)
        return state.attempts if state else 0

    def _merge_card(
        self, db: DbConnection, student_id: str, card: CardDraft, now: datetime
    ) -> Literal["created", "updated"]:
        existing = db.execute(
            select(cards).where(cards.c.student_id == student_id, cards.c.card_key == card.key)
        ).first()
        if existing is None:
            db.execute(
                insert(cards).values(
                    student_id=student_id,
                    card_key=card.key,
                    kind=card.kind,
                    title=card.title,
                    organisation=card.organisation,
                    role=card.role,
                    deadline=_db(card.deadline),
                    event_date=_db(card.event_date),
                    event_has_time=card.event_has_time,
                    form_link=card.form_link,
                    details=card.details,
                    first_received_at=_db(card.received_at),
                    last_received_at=_db(card.received_at),
                    created_at=_db(now),
                    updated_at=_db(now),
                    message_id=card.message_id,
                    rfc822_id=card.rfc822_id,
                    thread_id=card.thread_id,
                    mails=1,
                )
            )
            return "created"
        last = aware(existing.last_received_at)
        newer = card.received_at >= last
        overrides = newer and card.authoritative
        values: dict[str, object] = {"mails": existing.mails + 1, "updated_at": _db(now)}
        new_values = {
            "organisation": card.organisation,
            "role": card.role,
            "deadline": _db(card.deadline),
            "event_date": _db(card.event_date),
            "form_link": card.form_link,
            "details": card.details,
        }
        for name in _MERGED:
            new = new_values[name]
            if new is None:
                continue
            if overrides or getattr(existing, name) is None:
                values[name] = new
                if name == "event_date":
                    values["event_has_time"] = card.event_has_time
        if newer:
            values["last_received_at"] = _db(card.received_at)
            if card.authoritative:
                values["message_id"] = card.message_id
                values["rfc822_id"] = card.rfc822_id
        if card.received_at < aware(existing.first_received_at):
            values["first_received_at"] = _db(card.received_at)
        db.execute(update(cards).where(cards.c.id == existing.id).values(**values))
        return "updated"

    def cards(self, student_id: str) -> list[CardRow]:
        with self.engine.connect() as db:
            rows = db.execute(
                select(cards).where(cards.c.student_id == student_id).order_by(cards.c.id)
            ).all()
        return [
            CardRow(
                id=row.id,
                kind=row.kind,
                title=row.title,
                organisation=row.organisation,
                role=row.role,
                deadline=_read(row.deadline),
                event_date=_read(row.event_date),
                event_has_time=row.event_has_time,
                form_link=row.form_link,
                details=row.details,
                first_received_at=aware(row.first_received_at),
                last_received_at=aware(row.last_received_at),
                created_at=aware(row.created_at),
                updated_at=aware(row.updated_at),
                message_id=row.message_id,
                rfc822_id=row.rfc822_id,
                mails=row.mails,
            )
            for row in rows
        ]

    def mark(self, student_id: str, status: ConnectionStatus, error: str | None) -> None:
        with self.engine.begin() as db:
            db.execute(
                update(connections)
                .where(connections.c.student_id == student_id)
                .values(status=status, last_error=error)
            )

    def forget(self, student_id: str) -> None:
        """Everything the filter holds about one student, gone: the disconnect promise."""
        with self.engine.begin() as db:
            for table in (cards, seen, runs, connections):
                db.execute(delete(table).where(table.c.student_id == student_id))
