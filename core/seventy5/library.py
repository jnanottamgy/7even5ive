"""Reading the WhatsApp bot's library: subjects, shelves, files, and one file's link.

Why read through, never copy: the bot's database is the one library. Renames, re-filing and
deletions there are simply what the next read returns, and the file bytes go from the bot's
storage straight to the phone through a link that expires in minutes.
Why the phone number travels in a header: it stays out of URLs and access logs.
Not: called by the app directly. Every call comes through the gateway (tools.py), which
checks the policy and logs it; the app never holds the bot's key.
"""

from __future__ import annotations

import logging
from typing import Any, Protocol

import httpx

from .config import settings

log = logging.getLogger(__name__)
TIMEOUT_SECONDS = 8.0


UNREACHABLE = "The library can't be reached right now."
NO_STORAGE = "That file can't be fetched from storage right now."


class LibraryUnavailable(RuntimeError):
    """The bot's API or its file storage failed. The message is said to the student as it is;
    Files shows it and every other tab keeps working."""


class Library(Protocol):
    def library(self, phone: str) -> dict[str, Any]: ...
    def files(self, phone: str, *, subject_id: int | None, shelf: str | None, unsorted: bool,
              offset: int) -> dict[str, Any]: ...
    def open(self, phone: str, file_id: int) -> dict[str, Any]: ...
    def deadlines(self, phone: str) -> list[dict[str, Any]]: ...


class HttpLibrary:
    def __init__(self, base: str, token: str, client: httpx.Client | None = None) -> None:
        self.base = base.rstrip("/") + "/seventy5/v1"
        self.token = token
        self.http = client or httpx.Client(timeout=TIMEOUT_SECONDS)

    def _get(self, phone: str, path: str, params: dict[str, Any] | None = None) -> Any:
        headers = {"Authorization": f"Bearer {self.token}", "X-Student-Phone": phone}
        try:
            r = self.http.get(self.base + path, params=params, headers=headers)
        except httpx.HTTPError as err:
            log.warning("library unreachable", extra={"error": type(err).__name__})
            raise LibraryUnavailable(UNREACHABLE) from err
        if r.status_code == 404:
            raise LookupError("not found")  # also what an unlinked student gets
        if r.status_code >= 400:
            log.warning("library refused", extra={"status": r.status_code})
            # 502 is the bot's own word for "storage failed": the library is fine, the file is not.
            raise LibraryUnavailable(NO_STORAGE if r.status_code == 502 else UNREACHABLE)
        return r.json()

    def library(self, phone: str) -> dict[str, Any]:
        return dict(self._get(phone, "/library"))

    def files(self, phone: str, *, subject_id: int | None, shelf: str | None, unsorted: bool,
              offset: int) -> dict[str, Any]:
        params: dict[str, Any] = {"offset": offset}
        if unsorted:
            params["unsorted"] = "true"
        else:
            params["subject_id"] = subject_id
            if shelf:
                params["shelf"] = shelf
        return dict(self._get(phone, "/files", params))

    def open(self, phone: str, file_id: int) -> dict[str, Any]:
        return dict(self._get(phone, f"/files/{int(file_id)}/open"))

    def deadlines(self, phone: str) -> list[dict[str, Any]]:
        return list(self._get(phone, "/deadlines")["deadlines"])


SHELVES = (("material", "Material"), ("pyq", "PYQ & Questions"), ("info", "Info & Admin"))


class DemoLibrary:
    """Invented library in the bot's exact shape, so Files works with no bot configured.
    It has no deadlines: the demo morning already files its own."""

    FILES = [
        # (id, subject_id, shelf, kind, title, filename, mime)
        (101, 1, "material", "file", "DBMS unit 3 notes", "DBMS_Unit3_notes.pdf", "application/pdf"),
        (102, 1, "material", "file", "ER diagram slides", "ER_Diagrams.pptx",
         "application/vnd.openxmlformats-officedocument.presentationml.presentation"),
        (103, 1, "pyq", "file", "CIE-1 question paper", "DBMS_CIE1_2025.pdf", "application/pdf"),
        (104, 2, "material", "file", "DCN lab manual", "DCN_Lab_Manual.docx",
         "application/vnd.openxmlformats-officedocument.wordprocessingml.document"),
        (105, 2, "info", "note", "Lab moved to Thursday", None, None),
        (106, 3, "material", "file", "Scheduling algorithms", "OS_Unit2_Scheduling.pdf",
         "application/pdf"),
    ]
    SUBJECTS = [(1, "Database Management Systems"), (2, "Computer Networks"),
                (3, "Operating Systems")]

    def library(self, phone: str) -> dict[str, Any]:
        return {
            "subjects": [
                {"id": sid, "name": name, "shelves": [
                    {"shelf": shelf, "label": label,
                     "files": sum(1 for f in self.FILES if f[1] == sid and f[2] == shelf)}
                    for shelf, label in SHELVES]}
                for sid, name in self.SUBJECTS
            ],
            "unsorted": 0,
        }

    def files(self, phone: str, *, subject_id: int | None, shelf: str | None, unsorted: bool,
              offset: int) -> dict[str, Any]:
        if unsorted:
            return {"files": [], "next_offset": None}
        if subject_id not in {s for s, _ in self.SUBJECTS}:
            raise LookupError("not found")
        rows = [f for f in self.FILES if f[1] == subject_id and (shelf is None or f[2] == shelf)]
        return {"files": [
            {"id": f[0], "kind": f[3], "title": f[4], "filename": f[5], "mime_type": f[6],
             "shelf": f[2], "subject_id": f[1], "created_at": "2026-11-20T10:00:00+05:30"}
            for f in rows[offset:]], "next_offset": None}

    def open(self, phone: str, file_id: int) -> dict[str, Any]:
        found = next((f for f in self.FILES if f[0] == file_id), None)
        if found is None:
            raise LookupError("not found")
        if found[3] == "note":
            return {"kind": "note", "title": found[4],
                    "text": "DCN lab moved to Thursday, 2 pm. Bring your record."}
        return {"kind": "file", "url": f"https://example.invalid/demo/{found[5]}",
                "expires_in": 300, "filename": found[5], "mime_type": found[6]}

    def deadlines(self, phone: str) -> list[dict[str, Any]]:
        return []


def configured() -> bool:
    return bool(settings.library_url and settings.library_service_token)


def get_library() -> Library:
    if configured():
        return HttpLibrary(settings.library_url, settings.library_service_token)
    return DemoLibrary()
