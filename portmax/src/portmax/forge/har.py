"""Replaying a sanitised recording as if it were the portal, so a draft connector's fetch plan can
be run against what was captured: every page it asks for must be in the recording, and the pages
it gets back become its fixtures.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import urljoin, urlsplit


def load_har(path: Path) -> dict[str, Any]:
    har: dict[str, Any] = json.loads(path.read_text())
    return har


def _key(url: str) -> str:
    parts = urlsplit(url)
    return parts.path + (f"?{parts.query}" if parts.query else "")


@dataclass(frozen=True)
class ReplayResponse:
    url: str
    status_code: int
    text: str


class MissingFromCapture(LookupError):
    """The plan asked for a page the recording does not have: capture again and visit it."""


class HarClient:
    """Serves GET requests from a recording, following redirects inside it."""

    def __init__(self, har: dict[str, Any]) -> None:
        self.entries: dict[str, dict[str, Any]] = {}
        for entry in har["log"]["entries"]:
            if entry["request"]["method"] != "GET":
                continue
            response = entry["response"]
            redirect = 300 <= response["status"] < 400
            if not redirect and not response["content"].get("text"):
                continue  # a page whose body was not captured (the tab closed mid-load)
            # The last full response for a URL wins: it is what the student saw most recently.
            self.entries[_key(entry["request"]["url"])] = entry
        self.requested: list[str] = []

    def get(
        self, url: str, *, headers: Mapping[str, str], follow_redirects: bool
    ) -> ReplayResponse:
        current = url
        for _ in range(10):
            key = _key(current)
            self.requested.append(key)
            entry = self.entries.get(key)
            if entry is None:
                raise MissingFromCapture(f"{key} was not visited during the capture")
            response = entry["response"]
            location = response.get("redirectURL") or ""
            if follow_redirects and 300 <= response["status"] < 400 and location:
                current = urljoin(current, location)
                continue
            return ReplayResponse(
                url=current,
                status_code=response["status"],
                text=response["content"].get("text", ""),
            )
        raise MissingFromCapture(f"{url} redirects too many times in the capture")
