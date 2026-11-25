"""Where the filter keeps each student's connection, which mail ids it has judged, and cards.

Mail bodies are never stored: a dropped mail leaves only its id and an outcome code, so the
same mail is never judged twice; a kept mail leaves only the card's checked fields. SQLite
serves development and tests; production points `database_url` at Postgres (Supabase, Mumbai).
Every time written is UTC; SQLite drops the zone, so reads put it back.

Three rules keep the data right when things overlap:
- A check holds a lease with its own token; it renews the lease as it goes, and only the holder
  of the token can move the checkpoint or release it, so a check that overran never undoes the
  work of the one that took over.
- Every write for a student first locks that student's connection row and refuses if it is
  gone, and disconnecting locks it before deleting, so a check running during a disconnect
  cannot leave anything behind.
- A mail already settled is never merged into a card a second time.
"""

from __future__ import annotations

import json
import secrets
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any, Literal

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
from sqlalchemy.engine import Engine, Row

from mailfilter.checks import normalise, same_title
from mailfilter.contract import ConnectionStatus, KeptKind
from mailfilter.errors import NotConnected
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
    Column("history_id", String(32), nullable=True),
    Column("last_run_at", DateTime(timezone=True), nullable=True),
    Column("last_ok_at", DateTime(timezone=True), nullable=True),
    Column("last_error", String(40), nullable=True),
    Column("lease_until", DateTime(timezone=True), nullable=True),
    Column("lease_token", String(64), nullable=True),
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
    Index("ix_mail_seen_student_outcome", "student_id", "outcome"),
)

cards = Table(
    "mail_cards",
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("student_id", String(64), nullable=False),
    Column("card_key", String(80), nullable=False),
    Column("kind", String(16), nullable=False),
    Column("title", String(200), nullable=False),
    Column("organisation", String(200), nullable=True),
    Column("role", String(200), nullable=True),
    Column("deadline", DateTime(timezone=True), nullable=True),
    Column("event_date", DateTime(timezone=True), nullable=True),
    Column("event_has_time", Boolean, nullable=False),
    Column("form_link", Text, nullable=True),
    Column("link_key", String(300), nullable=True),
    Column("details", Text, nullable=True),
    Column("first_received_at", DateTime(timezone=True), nullable=False),
    Column("last_received_at", DateTime(timezone=True), nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False),
    Column("updated_at", DateTime(timezone=True), nullable=False),
    Column("message_id", String(64), nullable=False),
    Column("rfc822_id", String(300), nullable=True),
    Column("threads", Text, nullable=False),
    # Per field: when the news it holds was sent, and the values it has replaced.
    Column("provenance", Text, nullable=False),
    Column("mails", Integer, nullable=False),
    UniqueConstraint("student_id", "card_key", name="uq_mail_cards_student_key"),
    Index("ix_mail_cards_student_kind", "student_id", "kind"),
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
MERGED = ("organisation", "role", "deadline", "event_date", "form_link", "details")
# A card only takes in mail that arrives within this long of its latest mail.
MATCH_WITHIN = timedelta(days=90)


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
    history_id: str | None
    last_run_at: datetime | None
    last_ok_at: datetime | None
    last_error: str | None


@dataclass(frozen=True)
class SeenState:
    outcome: str
    attempts: int


@dataclass(frozen=True)
class CardDraft:
    kind: KeptKind
    title: str
    organisation: str | None
    role: str | None
    deadline: datetime | None
    event_date: datetime | None
    event_has_time: bool
    form_link: str | None
    link_key: str | None
    details: str | None
    received_at: datetime
    # When the news was sent: the received time, or a forward's original date when readable.
    news_at: datetime
    forwarded: bool
    message_id: str
    rfc822_id: str | None
    thread_id: str


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


def _comparable(name: str, value: Any, has_time: bool = False) -> str | None:
    """A field's value as text, so values can be compared and remembered."""
    if value is None:
        return None
    if isinstance(value, datetime):
        text = aware(value).astimezone(UTC).isoformat()
        return f"{text}|{int(has_time)}" if name == "event_date" else text
    return normalise(str(value)) if name in ("organisation", "role", "details") else str(value)


def _compatible(first: str | None, second: str | None) -> bool:
    return first is None or second is None or normalise(first) == normalise(second)


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
                # Ids and history are per mailbox: another account's mean nothing here.
                db.execute(delete(seen).where(seen.c.student_id == student_id))
                values["checked_through"] = _db(ist_midnight(now))
                values["history_id"] = None
                values["last_run_at"] = None
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
            history_id=row.history_id,
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

    def acquire(self, student_id: str, now: datetime, lease: timedelta) -> str | None:
        """Hold the mailbox for one check: a token, or None when another check holds it."""
        token = secrets.token_hex(16)
        with self.engine.begin() as db:
            result = db.execute(
                update(connections)
                .where(
                    connections.c.student_id == student_id,
                    or_(connections.c.lease_until.is_(None), connections.c.lease_until < _db(now)),
                )
                .values(lease_until=_db(now + lease), lease_token=token, last_run_at=_db(now))
            )
            return token if result.rowcount == 1 else None

    def renew(self, student_id: str, token: str, now: datetime, lease: timedelta) -> bool:
        """Extend the lease; False when this check no longer holds it."""
        with self.engine.begin() as db:
            result = db.execute(
                update(connections)
                .where(connections.c.student_id == student_id, connections.c.lease_token == token)
                .values(lease_until=_db(now + lease))
            )
            return result.rowcount == 1

    def release(self, student_id: str, token: str) -> None:
        with self.engine.begin() as db:
            db.execute(
                update(connections)
                .where(connections.c.student_id == student_id, connections.c.lease_token == token)
                .values(lease_until=None, lease_token=None)
            )

    def finish(
        self,
        student_id: str,
        token: str,
        now: datetime,
        checked_through: datetime,
        history_id: str | None,
        status: ConnectionStatus,
        error: str | None,
    ) -> bool:
        """Record where the next check starts. Only the lease holder may; the start never
        moves backwards. False when the lease was lost or the student disconnected."""
        with self.engine.begin() as db:
            row = db.execute(
                select(connections.c.checked_through)
                .where(connections.c.student_id == student_id, connections.c.lease_token == token)
                .with_for_update()
            ).first()
            if row is None:
                return False
            values: dict[str, object] = {
                "checked_through": _db(max(aware(row.checked_through), checked_through)),
                "status": status,
                "last_error": error,
            }
            if history_id is not None:
                values["history_id"] = history_id
            if error is None:
                values["last_ok_at"] = _db(now)
            db.execute(
                update(connections).where(connections.c.student_id == student_id).values(**values)
            )
            return True

    def mark(self, student_id: str, status: ConnectionStatus, error: str | None) -> None:
        with self.engine.begin() as db:
            db.execute(
                update(connections)
                .where(connections.c.student_id == student_id)
                .values(status=status, last_error=error)
            )

    def _lock(self, db: DbConnection, student_id: str) -> None:
        """Lock the student's connection row for this transaction, or refuse if it is gone."""
        row = db.execute(
            select(connections.c.student_id)
            .where(connections.c.student_id == student_id)
            .with_for_update()
        ).first()
        if row is None:
            raise NotConnected("disconnected")

    def record_run(self, record: RunRecord) -> None:
        with self.engine.begin() as db:
            try:
                self._lock(db, record.student_id)
            except NotConnected:
                return  # disconnected mid-check: nothing about the student may remain
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

    def forget(self, student_id: str) -> None:
        """Everything the filter holds about one student, gone: the disconnect promise. The
        connection row is locked first, so a check writing at the same moment either finishes
        first (and its rows are deleted here) or finds the student gone and writes nothing."""
        with self.engine.begin() as db:
            db.execute(
                select(connections.c.student_id)
                .where(connections.c.student_id == student_id)
                .with_for_update()
            )
            for table in (cards, seen, runs, connections):
                db.execute(delete(table).where(table.c.student_id == student_id))

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

    def retry_ids(self, student_id: str) -> list[str]:
        """Mail that could not be judged yet, oldest first: retried at every check."""
        with self.engine.connect() as db:
            rows = db.execute(
                select(seen.c.message_id)
                .where(seen.c.student_id == student_id, seen.c.outcome == "retry")
                .order_by(seen.c.updated_at, seen.c.message_id)
            ).all()
        return [row.message_id for row in rows]

    def record_mail(
        self,
        student_id: str,
        message_id: str,
        received_at: datetime | None,
        outcome: Outcome,
        reason: str | None,
        now: datetime,
        card: CardDraft | None = None,
    ) -> Literal["created", "updated", "unchanged"] | None:
        """One mail's outcome and, for a kept mail, its card, in a single transaction."""
        with self.engine.begin() as db:
            self._lock(db, student_id)
            previous = db.execute(
                select(seen.c.outcome, seen.c.attempts).where(
                    seen.c.student_id == student_id, seen.c.message_id == message_id
                )
            ).first()
            if previous is not None and previous.outcome in FINAL:
                return None  # settled already (by an overlapping check): never twice
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

    def _match(self, db: DbConnection, student_id: str, card: CardDraft) -> Row[Any] | None:
        """The card this mail is about, if any:
        1. the same specific form link, from the same organisation (or the same title when one
           side does not name it): a shared portal link alone never merges two drives;
        2. the same Gmail conversation and the same title, nothing in conflict;
        3. the same organisation and role, nothing in conflict."""
        rows = db.execute(
            select(cards).where(
                cards.c.student_id == student_id,
                cards.c.kind == card.kind,
                cards.c.last_received_at >= _db(card.received_at - MATCH_WITHIN),
            )
        ).all()

        def no_conflict(row: Row[Any]) -> bool:
            return (
                _compatible(row.organisation, card.organisation)
                and _compatible(row.role, card.role)
                and (row.link_key is None or card.link_key is None or row.link_key == card.link_key)
            )

        def same_source(row: Row[Any]) -> bool:
            if row.organisation and card.organisation:
                return normalise(row.organisation) == normalise(card.organisation)
            return same_title(row.title, card.title)

        rules = [
            [r for r in rows if card.link_key and r.link_key == card.link_key
             and _compatible(r.role, card.role) and same_source(r)],
            [r for r in rows if card.thread_id in json.loads(r.threads)
             and no_conflict(r) and same_title(r.title, card.title)],
            [r for r in rows if card.organisation and card.role and r.organisation and r.role
             and no_conflict(r)],
        ]  # fmt: skip
        for found in rules:
            if found:
                return max(found, key=lambda r: aware(r.last_received_at))
        return None

    def _merge_card(
        self, db: DbConnection, student_id: str, card: CardDraft, now: datetime
    ) -> Literal["created", "updated", "unchanged"]:
        existing = self._match(db, student_id, card)
        if existing is None:
            first_news = card.news_at.astimezone(UTC).isoformat()
            initial: dict[str, dict[str, Any]] = {
                name: {"at": first_news, "old": []}
                for name in MERGED
                if getattr(card, name) is not None
            }
            db.execute(
                insert(cards).values(
                    student_id=student_id,
                    card_key=f"mail:{card.message_id}",
                    kind=card.kind,
                    title=card.title,
                    organisation=card.organisation,
                    role=card.role,
                    deadline=_db(card.deadline),
                    event_date=_db(card.event_date),
                    event_has_time=card.event_has_time,
                    form_link=card.form_link,
                    link_key=card.link_key,
                    details=card.details,
                    first_received_at=_db(card.received_at),
                    last_received_at=_db(card.received_at),
                    created_at=_db(now),
                    updated_at=_db(now),
                    message_id=card.message_id,
                    rfc822_id=card.rfc822_id,
                    threads=json.dumps([card.thread_id]),
                    provenance=json.dumps(initial),
                    mails=1,
                )
            )
            return "created"
        provenance: dict[str, dict[str, Any]] = json.loads(existing.provenance)
        news = card.news_at.astimezone(UTC)
        latest_news = max(
            (datetime.fromisoformat(meta["at"]) for meta in provenance.values()), default=None
        )
        values: dict[str, object] = {}
        for name in MERGED:
            new_value = getattr(card, name)
            new = _comparable(name, new_value, card.event_has_time)
            if new is None:
                continue
            current = _comparable(name, getattr(existing, name), existing.event_has_time)
            meta = provenance.setdefault(name, {"at": news.isoformat(), "old": []})
            set_at = datetime.fromisoformat(meta["at"])
            if current is None or (new != current and not (card.forwarded and new in meta["old"])
                                   and news >= set_at):  # fmt: skip
                # Newer news wins; a forward never brings back a value already replaced.
                if current is not None:
                    meta["old"].append(current)
                values[name] = _db(new_value) if isinstance(new_value, datetime) else new_value
                if name == "event_date":
                    values["event_has_time"] = card.event_has_time
                if name == "form_link":
                    values["link_key"] = card.link_key
                meta["at"] = news.isoformat()
            elif new == current:
                meta["at"] = max(set_at, news).isoformat()  # confirmed by later news
            elif new not in meta["old"]:
                meta["old"].append(new)  # older news than what the card holds
        threads: list[str] = json.loads(existing.threads)
        if card.thread_id not in threads:
            threads.append(card.thread_id)
        changed = bool(values)
        values.update(
            mails=existing.mails + 1,
            updated_at=_db(now),
            provenance=json.dumps(provenance),
            threads=json.dumps(threads[-20:]),
            last_received_at=_db(max(aware(existing.last_received_at), card.received_at)),
            first_received_at=_db(min(aware(existing.first_received_at), card.received_at)),
        )
        if changed and (latest_news is None or news >= latest_news):
            # The link back opens the mail that brought the card's latest news.
            values["message_id"] = card.message_id
            values["rfc822_id"] = card.rfc822_id
        db.execute(update(cards).where(cards.c.id == existing.id).values(**values))
        return "updated" if changed else "unchanged"

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
