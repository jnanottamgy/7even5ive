"""Where PortMax keeps each student's latest answers and the state of their portal login.

Only parsed answers are kept; the pages they came from are discarded at ingest. SQLite serves
development and tests; production points `database_url` at Postgres (Supabase, Mumbai).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Literal

from sqlalchemy import (
    JSON,
    Column,
    DateTime,
    MetaData,
    String,
    Table,
    create_engine,
    delete,
    insert,
    select,
    update,
)
from sqlalchemy.engine import Engine

from portmax.contract import ToolName

metadata = MetaData()

snapshots = Table(
    "portmax_snapshots",
    metadata,
    Column("student_id", String(64), primary_key=True),
    Column("tool", String(32), primary_key=True),
    Column("college", String(32), nullable=False),
    Column("connector_version", String(20), nullable=False),
    Column("fetched_at", DateTime(timezone=True), nullable=False),
    Column("data", JSON, nullable=False),
)

logins = Table(
    "portmax_logins",
    metadata,
    Column("student_id", String(64), primary_key=True),
    Column("college", String(32), nullable=False),
    Column("state", String(16), nullable=False),
    Column("connected_at", DateTime(timezone=True), nullable=False),
    Column("last_ok_at", DateTime(timezone=True), nullable=False),
    Column("last_refresh_at", DateTime(timezone=True), nullable=True),
    Column("expired_at", DateTime(timezone=True), nullable=True),
)

LoginState = Literal["connected", "expired"]


def _utc(value: datetime) -> datetime:
    # SQLite drops the timezone; every time PortMax writes is UTC, so put it back on read.
    return value if value.tzinfo else value.replace(tzinfo=UTC)


@dataclass(frozen=True)
class Snapshot:
    student_id: str
    tool: ToolName
    college: str
    connector_version: str
    fetched_at: datetime
    data: Any


@dataclass(frozen=True)
class Login:
    student_id: str
    college: str
    state: LoginState
    connected_at: datetime
    last_ok_at: datetime
    last_refresh_at: datetime | None
    expired_at: datetime | None


class Store:
    def __init__(self, database_url: str = "sqlite:///portmax.db", *, create: bool = True) -> None:
        self.engine: Engine = create_engine(database_url)
        if create:
            metadata.create_all(self.engine)

    def save_answers(
        self,
        student_id: str,
        college: str,
        connector_version: str,
        fetched_at: datetime,
        answers: dict[ToolName, Any],
    ) -> None:
        with self.engine.begin() as db:
            for tool, data in answers.items():
                db.execute(
                    delete(snapshots).where(
                        snapshots.c.student_id == student_id, snapshots.c.tool == tool
                    )
                )
                db.execute(
                    insert(snapshots).values(
                        student_id=student_id,
                        tool=tool,
                        college=college,
                        connector_version=connector_version,
                        fetched_at=fetched_at,
                        data=data,
                    )
                )

    def snapshot(self, student_id: str, tool: ToolName) -> Snapshot | None:
        with self.engine.connect() as db:
            row = db.execute(
                select(snapshots).where(
                    snapshots.c.student_id == student_id, snapshots.c.tool == tool
                )
            ).first()
        if row is None:
            return None
        return Snapshot(
            student_id=row.student_id,
            tool=row.tool,
            college=row.college,
            connector_version=row.connector_version,
            fetched_at=_utc(row.fetched_at),
            data=row.data,
        )

    def login(self, student_id: str) -> Login | None:
        with self.engine.connect() as db:
            row = db.execute(select(logins).where(logins.c.student_id == student_id)).first()
        if row is None:
            return None
        return Login(
            student_id=row.student_id,
            college=row.college,
            state=row.state,
            connected_at=_utc(row.connected_at),
            last_ok_at=_utc(row.last_ok_at),
            last_refresh_at=_utc(row.last_refresh_at) if row.last_refresh_at else None,
            expired_at=_utc(row.expired_at) if row.expired_at else None,
        )

    def record_ok(self, student_id: str, college: str, at: datetime, *, refreshed: bool) -> None:
        """The portal answered a logged-in page: the login is alive as of `at`."""
        values: dict[str, Any] = {
            "college": college,
            "state": "connected",
            "last_ok_at": at,
            "expired_at": None,
        }
        if refreshed:
            values["last_refresh_at"] = at
        with self.engine.begin() as db:
            existing = db.execute(
                select(logins.c.state).where(logins.c.student_id == student_id)
            ).first()
            if existing is None:
                db.execute(
                    insert(logins).values(
                        student_id=student_id,
                        connected_at=at,
                        last_refresh_at=at if refreshed else None,
                        **{k: v for k, v in values.items() if k != "last_refresh_at"},
                    )
                )
            else:
                if existing.state == "expired":
                    values["connected_at"] = at  # a fresh login after the last one ended
                db.execute(update(logins).where(logins.c.student_id == student_id).values(values))

    def record_expired(self, student_id: str, at: datetime) -> None:
        with self.engine.begin() as db:
            db.execute(
                update(logins)
                .where(logins.c.student_id == student_id)
                .values(state="expired", expired_at=at)
            )

    def connected(self) -> list[Login]:
        with self.engine.connect() as db:
            ids = db.execute(
                select(logins.c.student_id).where(logins.c.state == "connected")
            ).scalars()
            found = list(ids)
        result = [self.login(student_id) for student_id in found]
        return [login for login in result if login is not None]
