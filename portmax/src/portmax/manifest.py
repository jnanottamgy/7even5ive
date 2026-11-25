"""What PortMax knows about one college's portal, written by the forge and read at run time."""

from __future__ import annotations

from datetime import date
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from portmax.contract import ToolName

# Android's WorkManager runs periodic work no more often than every 15 minutes. A shorter interval
# has to be driven by a push message from our server instead.
WORKMANAGER_MINIMUM_MINUTES = 15.0
# Until a portal's idle timeout is measured, ping as often as WorkManager allows.
UNMEASURED_INTERVAL_MINUTES = WORKMANAGER_MINIMUM_MINUTES


class _Model(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class Markers(_Model):
    """CSS selectors that tell a logged-in page from the login page, on any page we fetch."""

    logged_in: str = Field(min_length=1, max_length=200)
    login_page: str = Field(min_length=1, max_length=200)


class SessionRules(_Model):
    idle_timeout_minutes: float | None = Field(
        default=None, gt=0, description="Measured by a team member; None until measured"
    )
    max_lifetime_minutes: float | None = Field(default=None, gt=0)
    one_session_per_student: bool = True


class MadeBy(_Model):
    hand_written: bool
    rae_version: str | None = None
    model: str | None = None


class Manifest(_Model):
    college: str = Field(pattern=r"^[a-z][a-z0-9_]{1,31}$")
    name: str = Field(min_length=2, max_length=120)
    vendor: str = Field(min_length=2, max_length=60)
    base_url: str = Field(pattern=r"^https?://[^/\s]+$", description="Scheme and host, no path")
    login_path: str = "/"
    fetch_mode: Literal["phone", "server"] = "phone"
    markers: Markers
    session: SessionRules
    tools: list[ToolName] = Field(min_length=1)
    refresh_minutes: float = Field(
        default=180,
        ge=15,
        description="How often a keep-alive runs the whole plan; other pings read one page",
    )
    connector_version: str = Field(pattern=r"^\d+\.\d+\.\d+$")
    verified_at: date | None = None
    made_by: MadeBy


def keepalive_interval_minutes(session: SessionRules) -> float:
    """The longest ping interval that still keeps the login alive, with room for Android's delays.

    The margin is a fifth of the timeout, at least two minutes, because Android may run a
    scheduled task late; pinging at exactly the timeout would lose the session on the first delay.
    """
    if session.idle_timeout_minutes is None:
        return UNMEASURED_INTERVAL_MINUTES
    timeout = session.idle_timeout_minutes
    margin = max(2.0, timeout * 0.2)
    return max(1.0, timeout - margin)


def needs_push_wakeup(session: SessionRules) -> bool:
    """True when pings must come more often than WorkManager can schedule them on its own."""
    return keepalive_interval_minutes(session) < WORKMANAGER_MINIMUM_MINUTES
