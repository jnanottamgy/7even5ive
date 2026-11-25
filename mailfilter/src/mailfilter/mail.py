"""One mail as the filter handles it, and the exact text Claude is shown.

`render` returns two strings: what Claude reads, and the part of it the checks verify against.
They differ by one line: the Received line tells Claude when the mail arrived (so "tomorrow"
can be worked out) but it is not part of the mail, so no quote may come from it.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from mailfilter.mime import MailContent
from mailfilter.timekit import moment_text

# Mail the student sent, drafts, spam, trash and chats are never judged.
SKIP_LABELS = frozenset({"SENT", "DRAFT", "SPAM", "TRASH", "CHAT"})


@dataclass(frozen=True)
class MailMessage:
    id: str
    thread_id: str
    received_at: datetime
    labels: frozenset[str]
    content: MailContent

    @property
    def skipped(self) -> bool:
        return bool(self.labels & SKIP_LABELS)


@dataclass(frozen=True)
class Rendered:
    for_claude: str
    checkable: str


def render(mail: MailMessage) -> Rendered:
    content = mail.content
    lines = [f"From: {content.sender or '(unknown)'}", f"Subject: {content.subject or '(none)'}"]
    if content.bulk:
        lines.append("Sent to a mailing list: yes")
    if content.forwarded:
        lines.append("Forwarded: yes")
    if content.attachments:
        lines.append("Attachments (not read): " + ", ".join(content.attachments[:10]))
    lines += ["", "--- mail text ---", content.text or "(no text)"]
    extra = [link for link in content.links if link not in content.text][:40]
    if extra:
        lines += ["--- links in the mail ---", *extra]
    lines.append("--- end of mail ---")
    checkable = "\n".join(lines)
    received = f"Received: {moment_text(mail.received_at)} (India time)"
    return Rendered(for_claude=f"{received}\n{checkable}", checkable=checkable)
