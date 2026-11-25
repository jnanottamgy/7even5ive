"""Scrub a recorded portal visit (a HAR file) before any model or shared disk sees it.

What goes: every request body (the login form among them), other sites' traffic, images, styles
and scripts. What gets replaced, consistently so request chains still trace: cookie and token
values, and the student's own details (USN, name, date of birth, phone, email). The report keeps
only SHA-256 hashes of what was removed, so `verify` can later prove none of it leaked into a
connector without anyone storing the values themselves.
"""

from __future__ import annotations

import base64
import hashlib
import re
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import date
from typing import Any
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

SECRET_HEADERS = re.compile(
    r"^(cookie|set-cookie|authorization|proxy-authorization|x-csrf-token|x-xsrf-token|"
    r"x-auth-token|x-api-key|x-session.*)$",
    re.I,
)
SECRET_PARAMS = re.compile(r"(token|sess|sid|auth|key|ksign|csrf|nonce|otp|captcha)", re.I)
ASSET_EXTENSIONS = (
    ".png", ".jpg", ".jpeg", ".gif", ".svg", ".ico", ".webp", ".css", ".js", ".mjs", ".map",
    ".woff", ".woff2", ".ttf", ".eot", ".mp4", ".mp3",
)  # fmt: skip
KEPT_TYPES = ("text/html", "application/xhtml", "application/json", "text/plain", "text/xml")

EMAIL = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
MOBILE = re.compile(r"(?<!\d)(?:\+?91[ -]?)?[6-9]\d{9}(?!\d)")
MASKED_MOBILE = re.compile(r"(?<![\dA-Za-z])[6-9]\d[Xx*]{4,8}\d{2,4}(?![\dA-Za-z])")
VTU_USN = re.compile(r"\b[1-4][A-Z]{2}\d{2}[A-Z]{2,3}\d{3}\b")
DATE_FORMATS = ("%d-%m-%Y", "%Y-%m-%d", "%d/%m/%Y", "%d.%m.%Y", "%d %b %Y", "%d %B %Y")
STAND_IN_DOB = date(2000, 1, 1)
REMOVED_BODY = "[removed by PortMax sanitize]"


@dataclass(frozen=True)
class Identity:
    """The capturing team member's own details, so they are replaced wherever they appear."""

    usn: str | None = None
    name: str | None = None
    dob: date | None = None
    phone: str | None = None
    email: str | None = None


@dataclass
class Report:
    kept: int = 0
    dropped_offsite: int = 0
    dropped_assets: int = 0
    bodies_removed: int = 0
    replaced: dict[str, int] = field(default_factory=dict)
    secret_hashes: set[str] = field(default_factory=set)

    def as_json(self) -> dict[str, Any]:
        return {
            "kept": self.kept,
            "dropped_offsite": self.dropped_offsite,
            "dropped_assets": self.dropped_assets,
            "bodies_removed": self.bodies_removed,
            "replaced": dict(sorted(self.replaced.items())),
            "secret_hashes": sorted(self.secret_hashes),
        }


def digest(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


class _Replacer:
    """Gives each distinct secret one stable stand-in, and counts and hashes what it replaced."""

    def __init__(self, report: Report) -> None:
        self.report = report
        self.stand_ins: dict[str, str] = {}
        self.counters: dict[str, int] = {}

    def stand_in(self, kind: str, value: str, make: str | None = None) -> str:
        if not value:
            return value
        if value not in self.stand_ins:
            n = self.counters.get(kind, 0) + 1
            self.counters[kind] = n
            self.stand_ins[value] = make or f"<{kind}:{n}>"
            self.report.secret_hashes.add(digest(value))
        self.report.replaced[kind] = self.report.replaced.get(kind, 0) + 1
        return self.stand_ins[value]


class Sanitizer:
    def __init__(self, portal_host: str, identity: Identity) -> None:
        self.portal_host = portal_host
        self.identity = identity
        self.report = Report()
        self.replacer = _Replacer(self.report)
        self.literals: list[tuple[str, str, str]] = self._identity_literals()

    def _identity_literals(self) -> list[tuple[str, str, str]]:
        found: list[tuple[str, str, str]] = []  # (kind, value, stand-in)
        who = self.identity
        if who.usn:
            found.append(("usn", who.usn.upper(), "USN0000001"))
        if who.name:
            found.append(("name", who.name, "Student Name"))
            found.extend(("name", part, "Student") for part in who.name.split() if len(part) > 2)
        if who.dob:
            for fmt in DATE_FORMATS:
                found.append(("dob", who.dob.strftime(fmt), STAND_IN_DOB.strftime(fmt)))
        if who.phone:
            digits = re.sub(r"\D", "", who.phone)[-10:]
            found.append(("phone", digits, "9000000000"))
            # The last four digits are a login answer: hashed so verify can catch a leak, but not
            # replaced, because four digits also occur in ordinary numbers on a page.
            self.report.secret_hashes.add(digest(digits[-4:]))
        if who.email:
            found.append(("email", who.email, "student@example.invalid"))
        # Longest first, so a full name is replaced before its parts.
        return sorted(found, key=lambda item: -len(item[1]))

    # Text: bodies, URLs and header values all pass through here.

    def _replacement(self, kind: str, secret: str, stand_in: str) -> Callable[[re.Match[str]], str]:
        def replace(_: re.Match[str]) -> str:
            return self.replacer.stand_in(kind, secret, stand_in)

        return replace

    def text(self, value: str) -> str:
        for kind, secret, stand_in in self.literals:
            if secret in value or (kind == "name" and secret.lower() in value.lower()):
                pattern = re.compile(re.escape(secret), re.I if kind == "name" else 0)
                value = pattern.sub(self._replacement(kind, secret, stand_in), value)
        for secret, stand_in in list(self.replacer.stand_ins.items()):
            if len(secret) >= 8 and secret in value:  # a cookie value echoed into a page or URL
                value = value.replace(secret, stand_in)
        value = EMAIL.sub(
            lambda m: self.replacer.stand_in("email", m.group(), "x@example.invalid"), value
        )
        value = MASKED_MOBILE.sub(
            lambda m: self.replacer.stand_in("phone", m.group(), "90XXXXX000"), value
        )
        value = MOBILE.sub(
            lambda m: self.replacer.stand_in("phone", m.group(), "9000000000"), value
        )
        return VTU_USN.sub(lambda m: self.replacer.stand_in("usn", m.group(), "USN0000002"), value)

    def url(self, url: str) -> str:
        parts = urlsplit(url)
        query = [
            (name, self.replacer.stand_in("param", value) if SECRET_PARAMS.search(name) else value)
            for name, value in parse_qsl(parts.query, keep_blank_values=True)
        ]
        cleaned = urlunsplit(parts._replace(query=urlencode(query, safe="<>:")))
        return self.text(cleaned)

    def headers(self, headers: list[dict[str, str]]) -> list[dict[str, str]]:
        cleaned = []
        for header in headers:
            name, value = header.get("name", ""), header.get("value", "")
            if SECRET_HEADERS.match(name):
                value = self._cookie_like(value)
            cleaned.append({"name": name, "value": self.text(value)})
        return cleaned

    def _cookie_like(self, value: str) -> str:
        """Keep cookie names (they say which session it is), replace every value."""
        attributes = {"path", "domain", "expires", "max-age", "samesite"}
        pieces = []
        for piece in value.split(";"):
            if "=" in piece:
                name, _, secret = piece.partition("=")
                if name.strip().lower() not in attributes:
                    secret = self.replacer.stand_in("cookie", secret.strip())
                pieces.append(f"{name}={secret}")
            elif piece.strip().lower() in {"httponly", "secure", ""}:
                pieces.append(piece)
            else:
                pieces.append(self.replacer.stand_in("token", piece.strip()))
        return ";".join(pieces)

    def cookies(self, cookies: list[dict[str, Any]]) -> list[dict[str, Any]]:
        return [
            {**cookie, "value": self.replacer.stand_in("cookie", str(cookie.get("value", "")))}
            for cookie in cookies
        ]

    # Entries.

    def is_asset(self, entry: dict[str, Any]) -> bool:
        path = urlsplit(entry["request"]["url"]).path.lower()
        mime = (entry.get("response", {}).get("content", {}).get("mimeType") or "").lower()
        if path.endswith(ASSET_EXTENSIONS):
            return True
        return bool(mime) and not mime.startswith(KEPT_TYPES) and "html" not in mime

    def entry(self, entry: dict[str, Any]) -> dict[str, Any] | None:
        request, response = entry["request"], entry.get("response", {})
        if urlsplit(request["url"]).hostname != self.portal_host:
            self.report.dropped_offsite += 1
            return None
        if self.is_asset(entry):
            self.report.dropped_assets += 1
            return None
        # Headers and cookies first, so their values are known when bodies are scrubbed.
        request_headers = self.headers(request.get("headers", []))
        response_headers = self.headers(response.get("headers", []))
        clean_request: dict[str, Any] = {
            "method": request["method"],
            "url": self.url(request["url"]),
            "httpVersion": request.get("httpVersion", "HTTP/1.1"),
            "headers": request_headers,
            "cookies": self.cookies(request.get("cookies", [])),
            "queryString": [],
            "headersSize": -1,
            "bodySize": 0,
        }
        if request.get("postData") is not None:
            self.report.bodies_removed += 1
            clean_request["postData"] = {
                "mimeType": request["postData"].get("mimeType", ""),
                "text": REMOVED_BODY,
            }
        content = dict(response.get("content", {}))
        body = content.get("text") or ""
        if content.get("encoding") == "base64" and body:
            body = base64.b64decode(body).decode("utf-8", errors="replace")
        clean_response = {
            "status": response.get("status", 0),
            "statusText": response.get("statusText", ""),
            "httpVersion": response.get("httpVersion", "HTTP/1.1"),
            "headers": response_headers,
            "cookies": self.cookies(response.get("cookies", [])),
            "content": {
                "size": len(body),
                "mimeType": content.get("mimeType", ""),
                "text": self.text(body),
            },
            "redirectURL": self.url(response["redirectURL"]) if response.get("redirectURL") else "",
            "headersSize": -1,
            "bodySize": -1,
        }
        self.report.kept += 1
        return {
            "startedDateTime": entry.get("startedDateTime", ""),
            "time": entry.get("time", 0),
            "request": clean_request,
            "response": clean_response,
            "cache": {},
            "timings": entry.get("timings", {"send": 0, "wait": 0, "receive": 0}),
        }


def portal_host_of(har: dict[str, Any]) -> str:
    """The host of the first HTML page in the recording: the portal the visit was to."""
    for entry in har["log"]["entries"]:
        mime = entry.get("response", {}).get("content", {}).get("mimeType", "")
        if "html" in mime:
            host = urlsplit(str(entry["request"]["url"])).hostname
            if host:
                return str(host)
    raise ValueError("the recording has no HTML page")


def sanitize(
    har: dict[str, Any], identity: Identity, portal_host: str | None = None
) -> tuple[dict[str, Any], Report]:
    sanitizer = Sanitizer(portal_host or portal_host_of(har), identity)
    entries = [e for e in (sanitizer.entry(entry) for entry in har["log"]["entries"]) if e]
    clean = {
        "log": {
            "version": "1.2",
            "creator": {"name": "portmax-sanitize", "version": "1"},
            "pages": [],
            "entries": entries,
        }
    }
    return clean, sanitizer.report
