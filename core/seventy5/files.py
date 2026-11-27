"""Files that come with a material: kept with its event, handed to the phone to open.

Why with the event: a forwarded file arrives as part of one message, so it lives in that
event's payload (base64), the same row that already holds the file's name. No second store
to keep in step, and a redelivery is deduped with its message.
Not: a file server. Files are small class material (notes, slides, manuals); anything over
MAX_BYTES is refused at the door, and Lambda's 6 MB response limit is the ceiling anyway.

The demo's files are generated here (a one-page PDF, a minimal .docx), so the demo has real
files to open without shipping binaries in the repo. Each says it is a demo copy.
"""

from __future__ import annotations

import base64
import binascii
import io
import json
import zipfile
from typing import Any

from .db import Database

MAX_BYTES = 4 * 1024 * 1024

TYPES = {
    "pdf": "application/pdf",
    "doc": "application/msword",
    "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "ppt": "application/vnd.ms-powerpoint",
    "pptx": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
    "txt": "text/plain",
    "png": "image/png",
    "jpg": "image/jpeg",
    "jpeg": "image/jpeg",
}


class BadFile(ValueError):
    pass


def mime_for(name: str) -> str:
    return TYPES.get(name.rsplit(".", 1)[-1].lower() if "." in name else "", "application/octet-stream")


def check(b64: str) -> str:
    """The base64 a client sent, checked: decodes, not empty, under the limit."""
    if len(b64) > MAX_BYTES * 4 // 3 + 8:
        raise BadFile("file too large (4 MB at most)")
    try:
        raw = base64.b64decode(b64, validate=True)
    except (binascii.Error, ValueError) as err:
        raise BadFile("file is not valid base64") from err
    if not raw:
        raise BadFile("file is empty")
    return b64


def _payload(db: Database, student_id: int, item_id: int) -> dict[str, Any] | None:
    item = db.item(student_id, item_id)
    if item is None or item["event_id"] is None:
        return None
    event = db.event(item["event_id"])
    return json.loads(event["payload"]) if event is not None else None


def has_file(db: Database, student_id: int, item_id: int) -> bool:
    p = _payload(db, student_id, item_id)
    return bool(p and p.get("file") and p.get("attachment"))


def file_of(db: Database, student_id: int, item_id: int) -> tuple[str, str, bytes] | None:
    """(name, media type, bytes) of the file filed with this student's item, if any."""
    p = _payload(db, student_id, item_id)
    if not p or not p.get("file") or not p.get("attachment"):
        return None
    name = str(p["attachment"])
    return name, mime_for(name), base64.b64decode(p["file"])


# --- demo files ---------------------------------------------------------------------------


def _pdf_text(s: str) -> str:
    return s.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)").encode(
        "latin-1", "replace").decode("latin-1")


def demo_pdf(title: str, lines: list[str]) -> bytes:
    """A real one-page PDF (Helvetica, A4): a title and lines of text."""
    ops = ["BT", "/F2 20 Tf", "56 770 Td", f"({_pdf_text(title)}) Tj", "/F1 11 Tf", "0 -18 Td",
           "(7even5ive demo copy) Tj", "/F1 12 Tf"]
    for line in lines:
        ops += ["0 -22 Td", f"({_pdf_text(line)}) Tj"]
    ops.append("ET")
    stream = "\n".join(ops).encode("latin-1")
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] "
        b"/Resources << /Font << /F1 5 0 R /F2 6 0 R >> >> /Contents 4 0 R >>",
        b"<< /Length %d >>\nstream\n" % len(stream) + stream + b"\nendstream",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica-Bold >>",
    ]
    out = io.BytesIO()
    out.write(b"%PDF-1.4\n")
    offsets = []
    for i, body in enumerate(objects, 1):
        offsets.append(out.tell())
        out.write(b"%d 0 obj\n" % i + body + b"\nendobj\n")
    xref = out.tell()
    out.write(b"xref\n0 %d\n0000000000 65535 f \n" % (len(objects) + 1))
    for off in offsets:
        out.write(b"%010d 00000 n \n" % off)
    out.write(b"trailer\n<< /Size %d /Root 1 0 R >>\nstartxref\n%d\n%%%%EOF\n"
              % (len(objects) + 1, xref))
    return out.getvalue()


def demo_docx(title: str, lines: list[str]) -> bytes:
    """A minimal valid .docx: a bold title and one paragraph per line."""
    def para(text: str, bold: bool = False) -> str:
        esc = text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
        rpr = "<w:rPr><w:b/><w:sz w:val=\"36\"/></w:rPr>" if bold else ""
        return f"<w:p><w:r>{rpr}<w:t xml:space=\"preserve\">{esc}</w:t></w:r></w:p>"

    body = para(title, bold=True) + para("7even5ive demo copy") + "".join(para(x) for x in lines)
    files = {
        "[Content_Types].xml": (
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
            '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
            '<Default Extension="xml" ContentType="application/xml"/>'
            '<Override PartName="/word/document.xml" ContentType="application/'
            'vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/></Types>'),
        "_rels/.rels": (
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
            '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/'
            'relationships/officeDocument" Target="word/document.xml"/></Relationships>'),
        "word/document.xml": (
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
            f"<w:body>{body}</w:body></w:document>"),
    }
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
        for name, text in files.items():
            z.writestr(name, text)
    return out.getvalue()


# What each demo attachment holds: short, real study notes, so opening one shows something.
DEMO_CONTENT: dict[str, tuple[str, list[str]]] = {
    "DBMS_Unit3_notes.pdf": ("DBMS Unit 3: Normalisation", [
        "1NF: every attribute holds one atomic value.",
        "2NF: 1NF, and no partial dependency on part of a candidate key.",
        "3NF: 2NF, and no transitive dependency of a non-key attribute on the key.",
        "BCNF: for every non-trivial X -> Y, X is a superkey.",
        "Decompose losslessly: the common attributes must be a key of one side.",
        "Keep dependencies where you can; BCNF may lose some, 3NF never does.",
    ]),
    "DCN_Lab_Manual.docx": ("DCN Lab Manual", [
        "Experiment 1: Simulate a point-to-point network with three nodes (NS2/NS3).",
        "Experiment 2: Measure throughput as the queue size changes; plot drops.",
        "Experiment 3: Implement CRC-CCITT error detection in C.",
        "Experiment 4: Distance vector routing: build and print routing tables.",
        "Experiment 5: Sliding window protocol with Go-Back-N.",
        "Bring a printed copy of this manual to every lab session.",
    ]),
    "OS_Unit4_Deadlocks.pdf": ("OS Unit 4: Deadlocks", [
        "Four conditions, all needed: mutual exclusion, hold and wait,",
        "no preemption, circular wait. Break any one and deadlock cannot happen.",
        "Prevention: deny a condition, e.g. order resources to rule out circular wait.",
        "Avoidance: Banker's algorithm grants a request only if the state stays safe.",
        "Safe state: some order lets every process finish with what is available.",
        "Detection: a wait-for graph cycle (single instances) means deadlock.",
        "Recovery: abort processes or preempt resources, cheapest victim first.",
    ]),
}


def demo_file_b64(name: str) -> str | None:
    """The demo copy of a named attachment, as base64, or None if the demo has none."""
    if name not in DEMO_CONTENT:
        return None
    title, lines = DEMO_CONTENT[name]
    raw = demo_docx(title, lines) if name.endswith(".docx") else demo_pdf(title, lines)
    return base64.b64encode(raw).decode()
