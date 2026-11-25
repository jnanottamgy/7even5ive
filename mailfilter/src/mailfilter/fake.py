"""A stand-in Gmail for tests and the offline demo, with Gmail's own behaviour where it matters.

Mail is stored as raw RFC 822 bytes and parsed by the same code that reads real Gmail, so the
fake exercises the real parsing path. Listing follows Gmail: newest first, spam and trash left
out, everything after a moment. A mail can be hidden from listing (Gmail indexing late), gone
(deleted after listing) or made to fail.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass, field, replace
from datetime import datetime
from email.message import EmailMessage
from email.utils import format_datetime

from mailfilter.mail import MailMessage
from mailfilter.mime import parse_raw

STUDENT_ADDRESS = "student@mockcollege.edu.in"


@dataclass(frozen=True)
class Attachment:
    filename: str
    data: bytes
    maintype: str = "application"
    subtype: str = "pdf"


def build_raw(
    *,
    sender: str,
    subject: str,
    received_at: datetime,
    message_id: str,
    plain: str | None = None,
    html: str | None = None,
    charset: str = "utf-8",
    headers: Sequence[tuple[str, str]] = (),
    attachments: Sequence[Attachment] = (),
    to: str = STUDENT_ADDRESS,
) -> bytes:
    message = EmailMessage()
    message["From"] = sender
    message["To"] = to
    message["Subject"] = subject
    message["Date"] = format_datetime(received_at)
    message["Message-ID"] = message_id
    for name, value in headers:
        message[name] = value
    if plain is not None:
        message.set_content(plain, charset=charset)
        if html is not None:
            message.add_alternative(html, subtype="html", charset=charset)
    elif html is not None:
        message.set_content(html, subtype="html", charset=charset)
    else:
        message.set_content("", charset=charset)
    for attachment in attachments:
        message.add_attachment(
            attachment.data,
            maintype=attachment.maintype,
            subtype=attachment.subtype,
            filename=attachment.filename,
        )
    return message.as_bytes()


@dataclass(frozen=True)
class FakeMail:
    id: str
    thread_id: str
    received_at: datetime
    raw: bytes
    labels: frozenset[str] = frozenset({"INBOX"})


@dataclass
class FakeMailbox:
    mails: list[FakeMail]
    max_text_chars: int = 15_000
    address: str = STUDENT_ADDRESS
    hidden: set[str] = field(default_factory=set)
    gone: set[str] = field(default_factory=set)
    errors: dict[str, Exception] = field(default_factory=dict)
    list_error: Exception | None = None
    # The present moment: mail received later does not exist yet. None shows everything.
    now: Callable[[], datetime] | None = None
    # Gmail's change history: (history id, message id) for mail that arrived or was moved out
    # of spam or trash. History at or below `history_floor` has expired.
    history: list[tuple[int, str]] = field(default_factory=list)
    history_counter: int = 1000
    history_floor: int = 0
    got: list[str] = field(default_factory=list)

    def add(self, mails: Iterable[FakeMail]) -> None:
        self.mails.extend(mails)

    def _record(self, message_id: str) -> None:
        self.history_counter += 1
        self.history.append((self.history_counter, message_id))

    def arrive(self, mail: FakeMail) -> None:
        self.mails.append(mail)
        self._record(mail.id)

    def move_to_inbox(self, message_id: str) -> None:
        """The student rescues a mail from spam or trash; Gmail records the label change."""
        self.mails = [
            replace(mail, labels=(mail.labels - {"SPAM", "TRASH"}) | {"INBOX"})
            if mail.id == message_id
            else mail
            for mail in self.mails
        ]
        self._record(message_id)

    def list_ids(self, after: datetime) -> list[str]:
        if self.list_error is not None:
            raise self.list_error
        visible = [
            mail
            for mail in self.mails
            if mail.received_at > after
            and (self.now is None or mail.received_at <= self.now())
            and mail.id not in self.hidden
            and not mail.labels & {"SPAM", "TRASH"}
        ]
        visible.sort(key=lambda mail: mail.received_at, reverse=True)
        return [mail.id for mail in visible]

    def history_id(self) -> str:
        return str(self.history_counter)

    def changed_since(self, history_id: str) -> list[str] | None:
        start = int(history_id)
        if start < self.history_floor:
            return None
        return list(dict.fromkeys(mid for hid, mid in self.history if hid > start))

    def get(self, message_id: str) -> MailMessage | None:
        self.got.append(message_id)
        if message_id in self.errors:
            raise self.errors[message_id]
        if message_id in self.gone:
            return None
        mail = next(mail for mail in self.mails if mail.id == message_id)
        return MailMessage(
            id=mail.id,
            thread_id=mail.thread_id,
            received_at=mail.received_at,
            labels=mail.labels,
            content=parse_raw(mail.raw, self.max_text_chars),
        )

    def email_address(self) -> str:
        return self.address
