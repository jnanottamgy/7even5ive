"""The shapes that cross a boundary: Claude's answer about one mail, and the cards we serve."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

Kind = Literal["placement", "internship", "exam_notice", "other"]
KeptKind = Literal["placement", "internship", "exam_notice"]
KEPT_KINDS: tuple[KeptKind, ...] = ("placement", "internship", "exam_notice")
ConnectionStatus = Literal["connected", "needs_reconnect", "college_blocked", "not_connected"]


class Model(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class DatedQuote(Model):
    """A date Claude read, and the mail's own words it read it from."""

    value: str = Field(description="India time: YYYY-MM-DDTHH:MM, or YYYY-MM-DD for an event")
    quote: str


class Proposal(Model):
    """Claude's answer about one mail. Nothing in it is trusted until checks.py has run.

    No length limits here on purpose: one overlong field must cost that field (checks.py drops
    it), never the whole answer, or a placement would be lost to a long title.
    """

    kind: Kind
    title: str | None
    organisation: str | None
    role: str | None
    deadline: DatedQuote | None
    event_date: DatedQuote | None
    form_link: str | None
    details: str | None


OTHER = Proposal(
    kind="other",
    title=None,
    organisation=None,
    role=None,
    deadline=None,
    event_date=None,
    form_link=None,
    details=None,
)


class Card(Model):
    """One opportunity, as the student sees it. Dates are India time."""

    id: int
    kind: KeptKind
    title: str
    organisation: str | None
    role: str | None
    deadline: datetime | None = Field(description="Last moment to register or apply")
    event_date: datetime | None = Field(description="When the drive, test or exam happens")
    event_has_time: bool
    form_link: str | None
    details: str | None
    first_seen: datetime = Field(description="When the first mail about it arrived")
    last_seen: datetime = Field(description="When the latest mail about it arrived")
    mails: int = Field(description="How many mails were merged into this card")
    gmail_link: str
    summary: str = Field(description="One plain sentence for the student; no model wrote it")


class OpportunitiesAnswer(Model):
    tool: Literal["get_opportunities"] = "get_opportunities"
    connection: ConnectionStatus
    checked_at: datetime | None = Field(description="Last successful check of the mailbox")
    next_check_at: datetime | None
    stale: bool = Field(description="True when the mailbox has not been checked as planned")
    data: list[Card]


TOOL_DESCRIPTION = (
    "Placements, internships and exam-cell notices from the student's college mail, read twice a "
    "day (1 PM and 9 PM India time). Each card has the deadline, the event date, the form link "
    "and a link back to the mail, all copied from the mail and checked. Soonest first; past "
    "deadlines are left out unless include_past is true."
)
