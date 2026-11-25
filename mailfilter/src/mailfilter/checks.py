"""Code checks Claude's answer against the mail itself. A field that fails is dropped, never
guessed; a kept mail with nothing else verified still becomes a card titled by its subject.

- Copied values and quotes must appear in the mail (spacing, capitals, dashes and quote marks
  may differ). The Received line is not part of the mail, so nothing may come from it.
- A date must be one the quote itself names (dates.py), at the time the quote names (or 23:59
  when it names none), and not before the mail arrived.
- A form link must be https, carry no user name, and appear in the mail exactly as given.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from mailfilter.contract import KEPT_KINDS, DatedQuote, KeptKind, Proposal
from mailfilter.dates import END_OF_DAY, mentions
from mailfilter.mail import MailMessage
from mailfilter.mime import clean_link
from mailfilter.timekit import IST, to_ist

LIMITS = {"title": 100, "organisation": 120, "role": 120, "details": 300, "quote": 300}
LATEST = timedelta(days=400)
_FWD = re.compile(r"^\s*((fwd?|fw|re|reminder)\s*:\s*)+", re.IGNORECASE)
_DASHES = dict.fromkeys(map(ord, "‐‑‒–—―−"), "-")
_QUOTES = {ord("‘"): "'", ord("’"): "'", ord("“"): '"', ord("”"): '"'}


@dataclass(frozen=True)
class Checked:
    kind: KeptKind | None
    title: str
    organisation: str | None
    role: str | None
    deadline: datetime | None
    event_date: datetime | None
    event_has_time: bool
    form_link: str | None
    details: str | None
    rejected: tuple[str, ...]

    @property
    def keep(self) -> bool:
        return self.kind is not None


def normalise(text: str) -> str:
    text = unicodedata.normalize("NFKC", text).translate(_DASHES).translate(_QUOTES)
    return re.sub(r"\s+", " ", text).strip().casefold()


def in_mail(span: str, mail_text: str) -> bool:
    wanted = normalise(span)
    return bool(wanted) and wanted in normalise(mail_text)


def subject_title(subject: str) -> str:
    title = _FWD.sub("", subject).strip()
    return (title or "Notice from college mail")[: LIMITS["title"]]


def _span(name: str, value: str | None, mail_text: str, rejected: list[str]) -> str | None:
    if value is None:
        return None
    value = re.sub(r"\s+", " ", value).strip()
    if not value:
        return None
    if len(value) > LIMITS[name]:
        rejected.append(f"{name}:too_long")
        return None
    if not in_mail(value, mail_text):
        rejected.append(f"{name}:not_in_mail")
        return None
    return value


def _parse_value(value: str) -> tuple[date, time | None] | None:
    value = value.strip()
    try:
        if len(value) == 10:
            return date.fromisoformat(value), None
        moment = datetime.fromisoformat(value)
    except ValueError:
        return None
    if moment.tzinfo is not None:
        moment = moment.astimezone(IST)
    return moment.date(), moment.time().replace(second=0, microsecond=0)


def _dated(
    name: str,
    proposed: DatedQuote | None,
    mail_text: str,
    received: datetime,
    rejected: list[str],
    *,
    time_required: bool,
) -> tuple[datetime, bool] | None:
    """The checked moment and whether a time was stated, or None (with the reason recorded)."""
    if proposed is None:
        return None
    quote = re.sub(r"\s+", " ", proposed.quote).strip()
    if not quote or len(quote) > LIMITS["quote"] or not in_mail(quote, mail_text):
        rejected.append(f"{name}:quote_not_in_mail")
        return None
    parsed = _parse_value(proposed.value)
    if parsed is None:
        rejected.append(f"{name}:bad_value")
        return None
    day, clock = parsed
    if clock is None and time_required:
        clock = END_OF_DAY
    local_received = to_ist(received)
    said = mentions(quote, local_received.date())
    if day not in said.dates:
        rejected.append(f"{name}:date_not_in_quote")
        return None
    if clock is not None:
        stated = said.times or ({END_OF_DAY} if time_required else set())
        if clock not in stated:
            rejected.append(f"{name}:time_not_in_quote")
            return None
    moment = datetime.combine(day, clock or time(0), IST)
    if time_required and moment < local_received:
        rejected.append(f"{name}:before_mail")
        return None
    if not time_required and day < local_received.date():
        rejected.append(f"{name}:before_mail")
        return None
    if moment > local_received + LATEST:
        rejected.append(f"{name}:too_far")
        return None
    return moment, clock is not None


def _link(proposed: str | None, mail: MailMessage, rejected: list[str]) -> str | None:
    if proposed is None:
        return None
    link = clean_link(proposed)
    if not link:
        return None
    try:
        parts = urlsplit(link)
        host = parts.hostname
    except ValueError:  # "https://[insert form link here]" and other unparseable text
        rejected.append("form_link:bad_link")
        return None
    if parts.scheme.lower() != "https":
        rejected.append("form_link:not_https")
        return None
    if not host or "@" in parts.netloc or any(c.isspace() for c in link):
        rejected.append("form_link:bad_link")
        return None
    if len(link) > 2000:
        rejected.append("form_link:too_long")
        return None
    # Exactly a link the mail contains, never a piece of one: a shortened link is a broken one.
    if link not in mail.content.links:
        rejected.append("form_link:not_in_mail")
        return None
    return link


def check(proposal: Proposal, mail: MailMessage, mail_text: str) -> Checked:
    rejected: list[str] = []
    if proposal.kind not in KEPT_KINDS:
        return Checked(None, "", None, None, None, None, False, None, None, ())
    kind: KeptKind = proposal.kind  # "other" returned above
    title = _span("title", proposal.title, mail_text, rejected)
    deadline = _dated(
        "deadline", proposal.deadline, mail_text, mail.received_at, rejected, time_required=True
    )
    event = _dated(
        "event_date",
        proposal.event_date,
        mail_text,
        mail.received_at,
        rejected,
        time_required=False,
    )
    return Checked(
        kind=kind,
        title=title or subject_title(mail.content.subject),
        organisation=_span("organisation", proposal.organisation, mail_text, rejected),
        role=_span("role", proposal.role, mail_text, rejected),
        deadline=deadline[0] if deadline else None,
        event_date=event[0] if event else None,
        event_has_time=bool(event and event[1]),
        form_link=_link(proposal.form_link, mail, rejected),
        details=_span("details", proposal.details, mail_text, rejected),
        rejected=tuple(rejected),
    )


def canonical_link(link: str) -> str | None:
    """A form link as a matching key: host lower-cased, tracking and fragment dropped."""
    try:
        parts = urlsplit(link)
        host = (parts.hostname or "").lower()
    except ValueError:
        return None
    query = [
        (k, v)
        for k, v in parse_qsl(parts.query, keep_blank_values=True)
        if not k.startswith("utm_")
    ]
    return urlunsplit(("https", host, parts.path.rstrip("/"), urlencode(query), ""))


def link_key(link: str | None) -> str | None:
    """The key a link gives a card, or None for a portal's front page shared by many notices."""
    if not link:
        return None
    try:
        parts = urlsplit(link)
    except ValueError:
        return None
    if not (parts.path.strip("/") or parts.query):
        return None
    key = canonical_link(link)
    return key[:300] if key else None


_LITTLE_WORDS = frozenset((
    "a", "an", "and", "at", "by", "for", "from", "in", "is", "of", "on", "re", "fw", "fwd",
    "the", "to", "with", "reminder", "update", "updated", "revised", "last", "date",
    "extended", "new", "notice",
))  # fmt: skip


def title_words(title: str) -> frozenset[str]:
    return frozenset(re.findall(r"[a-z0-9]+", normalise(title))) - _LITTLE_WORDS


def same_title(first: str, second: str) -> bool:
    """Two titles name the same thing when most of their words are shared."""
    a, b = title_words(first), title_words(second)
    return bool(a and b) and len(a & b) / len(a | b) >= 0.5
