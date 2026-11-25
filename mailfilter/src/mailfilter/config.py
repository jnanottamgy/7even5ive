"""Settings, read from the environment. Every value to tune lives here, never in code."""

from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import time, timedelta


def parse_times(raw: str) -> tuple[time, ...]:
    """'13:00,21:00' -> (13:00, 21:00), sorted, India time."""
    found: set[time] = set()
    for part in raw.split(","):
        part = part.strip()
        if not part:
            continue
        hours, _, minutes = part.partition(":")
        if not hours.isdigit() or not minutes.isdigit():
            raise ValueError(f"check time {part!r} is not HH:MM")
        found.add(time(int(hours), int(minutes)))
    if not found:
        raise ValueError("no check time given")
    return tuple(sorted(found))


@dataclass(frozen=True)
class Settings:
    database_url: str = "sqlite:///mailfilter.db"
    # Claude on Amazon Bedrock in Mumbai. Bedrock model ids take the `anthropic.` prefix.
    model: str = "anthropic.claude-haiku-5-5"
    aws_region: str = "ap-south-1"
    # When the twice-daily check runs, India time.
    check_times: tuple[time, ...] = (time(13, 0), time(21, 0))
    # Each check re-reads this far before the last one: covers mail Gmail indexes late. Mail
    # already judged is skipped by id, so the overlap costs one list call, not a second judgement.
    overlap: timedelta = timedelta(hours=2)
    # After an outage, never reach further back than this.
    lookback: timedelta = timedelta(days=7)
    max_mails_per_run: int = 200
    # What Claude reads of one mail's text; the rest is cut and marked.
    max_text_chars: int = 15_000
    check_now_cooldown: timedelta = timedelta(minutes=5)
    # A mail Claude could not judge is tried at this many checks, then given up.
    max_attempts: int = 3
    # A check's hold on the mailbox, renewed before every mail: it lapses only when the check
    # died, and then another check may take over.
    lease: timedelta = timedelta(minutes=10)
    # The Jev slot: a sorter may drop a mail as "other" without Claude only at this confidence.
    sorter_threshold: float = 0.9
    # Google sign-in for development and the demo (production: AgentCore Identity).
    google_client_id: str = ""
    google_client_secret: str = field(default="", repr=False)
    token_file: str = ".mailfilter-tokens.json"

    @classmethod
    def from_env(cls, env: Mapping[str, str] | None = None) -> Settings:
        source = os.environ if env is None else env
        defaults = cls()

        def text(name: str, default: str) -> str:
            value = source.get(name, "").strip()
            return value or default

        times = source.get("MAILFILTER_CHECK_TIMES", "").strip()
        return cls(
            database_url=text("MAILFILTER_DATABASE_URL", defaults.database_url),
            model=text("MAILFILTER_MODEL", defaults.model),
            aws_region=text("MAILFILTER_AWS_REGION", defaults.aws_region),
            check_times=parse_times(times) if times else defaults.check_times,
            google_client_id=text("MAILFILTER_GOOGLE_CLIENT_ID", ""),
            google_client_secret=text("MAILFILTER_GOOGLE_CLIENT_SECRET", ""),
            token_file=text("MAILFILTER_TOKEN_FILE", defaults.token_file),
        )
