"""One mail's raw bytes (RFC 822, as Gmail's `format=raw` returns them) into plain text.

Python's own `email` parser does the hard parts: transfer encodings, charsets, encoded header
words and nested forwards. This module decides what Claude reads: the text parts (plain text
first, HTML turned into text when there is no plain part), every web link including those
hidden behind "click here", and the names of attachments, never their contents.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from email import message_from_bytes, policy
from email.message import Message
from html.parser import HTMLParser

URL = re.compile(r"https?://[^\s<>\"'`{}|\\^\[\]]+", re.IGNORECASE)
_TRAILING = ".,;:!?)]}'\""
_INVISIBLE = dict.fromkeys(map(ord, "​‌‍⁠﻿­"), None)
_FORWARD_SUBJECT = re.compile(r"^\s*(fwd?|fw)\s*:", re.IGNORECASE)
_FORWARD_MARK = re.compile(r"-{3,}\s*forwarded message\s*-{3,}|begin forwarded message", re.I)
MAX_LINKS = 40


@dataclass(frozen=True)
class MailContent:
    sender: str
    subject: str
    message_id: str | None
    bulk: bool
    forwarded: bool
    attachments: tuple[str, ...]
    text: str
    links: tuple[str, ...]
    truncated: bool


def clean_link(raw: str) -> str:
    link = raw.strip()
    while link and link[-1] in _TRAILING:
        # Keep a closing bracket the link itself opened, e.g. a wiki-style path.
        if link[-1] == ")" and link.count("(") >= link.count(")"):
            break
        link = link[:-1]
    return link


def find_links(text: str) -> list[str]:
    return [clean_link(match.group(0)) for match in URL.finditer(text)]


def _normalise_text(text: str) -> str:
    text = text.replace("\r\n", "\n").replace("\r", "\n").translate(_INVISIBLE)
    text = text.replace(" ", " ").replace("\t", " ")
    lines = [re.sub(r" {2,}", " ", line).strip() for line in text.split("\n")]
    joined = "\n".join(lines)
    return re.sub(r"\n{3,}", "\n\n", joined).strip()


def _one_line(value: object, limit: int) -> str:
    text = re.sub(r"\s+", " ", str(value or "")).translate(_INVISIBLE).strip()
    return text[:limit]


class _HtmlText(HTMLParser):
    """HTML to readable text; a link's target is written after its words: 'Register <url>'."""

    _BREAK = {"br", "hr"}
    _BLOCK = {
        "p", "div", "li", "tr", "table", "ul", "ol", "section", "article", "header", "footer",
        "blockquote", "pre", "h1", "h2", "h3", "h4", "h5", "h6", "dt", "dd", "center",
    }  # fmt: skip
    _SKIP = {"script", "style", "head", "title", "noscript", "template", "svg"}

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self.links: list[str] = []
        self._skipping = 0
        self._anchors: list[tuple[str | None, int]] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in self._SKIP:
            self._skipping += 1
        elif tag in self._BREAK or tag in self._BLOCK:
            self.parts.append("\n")
        elif tag in ("td", "th"):
            self.parts.append(" ")
        if tag == "a":
            self._anchors.append((dict(attrs).get("href"), len(self.parts)))

    def handle_endtag(self, tag: str) -> None:
        if tag in self._SKIP:
            self._skipping = max(0, self._skipping - 1)
        elif tag in self._BLOCK:
            self.parts.append("\n")
        if tag == "a" and self._anchors:
            href, start = self._anchors.pop()
            link = clean_link(href or "")
            if URL.fullmatch(link):
                self.links.append(link)
                words = "".join(self.parts[start:])
                if link not in words:
                    self.parts.append(f" <{link}>")

    def handle_data(self, data: str) -> None:
        if not self._skipping:
            self.parts.append(data)


def html_to_text(markup: str) -> tuple[str, list[str]]:
    parser = _HtmlText()
    try:
        parser.feed(markup)
        parser.close()
    except Exception:  # noqa: BLE001 - malformed markup: fall back to stripping tags
        stripped = re.sub(r"(?s)<(script|style)[^>]*>.*?</\1>|<[^>]+>", " ", markup)
        return _normalise_text(stripped), find_links(stripped)
    return _normalise_text("".join(parser.parts)), parser.links


def _decoded(part: Message) -> str:
    payload = part.get_payload(decode=True)
    if not isinstance(payload, bytes):
        return ""
    charset = part.get_content_charset() or "utf-8"
    try:
        return payload.decode(charset, errors="replace")
    except LookupError:  # a charset Python does not know: read it as UTF-8
        return payload.decode("utf-8", errors="replace")


def _header(message: Message, name: str) -> str:
    try:
        value = message.get(name)
    except Exception:  # noqa: BLE001 - a malformed header is treated as absent
        return ""
    return "" if value is None else str(value)


def parse_raw(raw: bytes, max_chars: int) -> MailContent:
    message = message_from_bytes(raw, policy=policy.default)
    plains: list[str] = []
    htmls: list[str] = []
    attachments: list[str] = []
    for part in message.walk():
        if part.is_multipart():
            continue
        content_type = part.get_content_type()
        filename = part.get_filename()
        is_file = part.get_content_disposition() == "attachment" or (
            filename is not None and content_type not in ("text/plain", "text/html")
        )
        if is_file:
            if filename:
                attachments.append(_one_line(filename, 120))
            continue
        if content_type == "text/plain":
            plains.append(_decoded(part))
        elif content_type == "text/html":
            htmls.append(_decoded(part))

    html_links: list[str] = []
    html_texts: list[str] = []
    for markup in htmls:
        text, hrefs = html_to_text(markup)
        html_texts.append(text)
        html_links.extend(hrefs)
    plain = _normalise_text("\n\n".join(plains))
    body = plain if plain else _normalise_text("\n\n".join(html_texts))

    links: list[str] = []
    for link in [*find_links(body), *html_links]:
        if link and link not in links:
            links.append(link)

    truncated = len(body) > max_chars
    if truncated:
        body = body[:max_chars].rstrip() + "\n[... the rest of this mail was cut ...]"

    subject = _one_line(_header(message, "Subject"), 300)
    sender = _one_line(_header(message, "From"), 300)
    message_id = _one_line(_header(message, "Message-ID"), 300) or None
    precedence = _header(message, "Precedence").strip().lower()
    bulk = bool(_header(message, "List-Unsubscribe") or _header(message, "List-Id")) or (
        precedence in ("bulk", "list", "junk")
    )
    forwarded = bool(_FORWARD_SUBJECT.match(subject) or _FORWARD_MARK.search(body))
    return MailContent(
        sender=sender,
        subject=subject,
        message_id=message_id,
        bulk=bulk,
        forwarded=forwarded,
        attachments=tuple(dict.fromkeys(attachments)),
        text=body,
        links=tuple(links[:MAX_LINKS]),
        truncated=truncated,
    )
