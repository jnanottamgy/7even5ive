"""MSRIT (Contineo) portal HTML → PortMax's tools.

PROVISIONAL (connector 0.1.0). Written from the reconnaissance in
``docs/msrit-connector-notes.md`` before any real logged-in page was captured, so these
selectors and shapes still need calibrating against one sanitised capture of each page
(see ``fixtures/README.md``). Until then they are deliberately strict: anything that does
not match the documented structure raises ``Missing``/``ValueError``, which the connector
turns into ``PortalChanged`` — the app asks the student to log in again rather than ever
showing a wrong attendance or marks figure.

Pure functions: no network, no files, no clock. ``get_marks`` is intentionally absent —
Contineo loads CIE marks through an uncaptured XHR, so it is not in the manifest yet.
"""

from __future__ import annotations

import json
import re

from portmax.contract import (
    AttendanceRow,
    Profile,
    ResultRow,
    Results,
    SemesterSummary,
    TimetableSlot,
    Weekday,
)
from portmax.htmlkit import Missing, number, parse, text
from portmax.pages import PagesByStep

# A Contineo subject code: a year prefix then the code, e.g. 24CS51, 24CSL56, 24CSAEC510.
_CODE = re.compile(r"\b(\d{2}[A-Z]{2,6}\d{2,3})\b")
_USN = re.compile(r"\b(1[A-Z]{2}\d{2}[A-Z]{2}\d{3})\b")
_SGPA = re.compile(r"SGPA[^0-9]*([0-9]\.?[0-9]*)", re.IGNORECASE)
_CGPA = re.compile(r"CGPA[^0-9]*([0-9]\.?[0-9]*)", re.IGNORECASE)
_SEM = re.compile(r"\bSem(?:ester)?\s*[-:]?\s*([0-9]{1,2})\b", re.IGNORECASE)
_PRESENT = re.compile(r"\bP(?:resent)?\b", re.IGNORECASE)
_ABSENT = re.compile(r"\bA(?:bsent)?\b", re.IGNORECASE)


def _billboard_arrays(html: str) -> list[list[tuple[str, float]]]:
    """Every billboard.js ``columns`` array in the page, as lists of (code, number) pairs.

    The dashboard embeds attendance as ``columns: [["24CS51", 86], ...]``. We read the pairs
    out of the raw HTML because the chart's own script builds the DOM later.
    """
    arrays: list[list[tuple[str, float]]] = []
    for block in re.finditer(r"columns\s*:\s*(\[\[.*?\]\])", html, re.DOTALL):
        try:
            raw = json.loads(block.group(1))
        except ValueError:
            continue
        pairs: list[tuple[str, float]] = []
        for item in raw:
            if isinstance(item, list) and len(item) >= 2 and isinstance(item[0], str):
                code = item[0].strip().upper()
                if _CODE.fullmatch(code) and isinstance(item[1], (int, float)):
                    pairs.append((code, float(item[1])))
        if pairs:
            arrays.append(pairs)
    return arrays


def parse_profile(pages: PagesByStep) -> Profile:
    html = pages["dashboard"][0].html
    body = parse(html).text() or ""
    usn = _USN.search(body) or _USN.search(html)
    if usn is None:
        raise Missing("no USN on the dashboard")
    sem = _SEM.search(body)
    if sem is None:
        raise Missing("no semester on the dashboard (calibrate parse_profile)")
    # Branch is in the student header; its exact selector is unconfirmed. Derive from the USN's
    # branch code as a safe placeholder until a capture pins the real field down.
    branch_code = usn.group(1)[5:7]
    return Profile(usn=usn.group(1), branch=branch_code, semester=int(sem.group(1)))


def parse_attendance(pages: PagesByStep) -> list[AttendanceRow]:
    """Attended/held per subject, cross-checked against the dashboard's percentage array.

    attended/held come from the per-class log on the ``attendencelist`` page; the dashboard's
    percentage array is the check. A subject is only emitted when round(attended/held) matches
    its dashboard percentage, so a mis-grouped table raises instead of reporting a wrong figure.
    """
    percent_by_code: dict[str, float] = {}
    for arr in _billboard_arrays(pages["dashboard"][0].html):
        if all(0.0 <= value <= 100.0 for _, value in arr):
            percent_by_code = {code: value for code, value in arr}
            break
    if not percent_by_code:
        raise Missing("no attendance percentage array on the dashboard")

    counts = _attended_held(pages["attendance"][0].html)
    if not counts:
        raise Missing("no per-class attendance tables on attendencelist (calibrate)")

    rows: list[AttendanceRow] = []
    for code, (attended, held) in counts.items():
        if held <= 0 or attended > held:
            raise Missing(f"{code}: implausible attended/held {attended}/{held}")
        pct = percent_by_code.get(code)
        if pct is None or abs(round(attended / held * 100) - round(pct)) > 1:
            raise Missing(f"{code}: counts {attended}/{held} disagree with dashboard {pct}")
        rows.append(
            AttendanceRow(
                subject_code=code,
                subject_name=code,  # TODO: real subject names once a capture shows where they live
                attended=attended,
                held=held,
                percent=round(attended / held * 100, 2),
            )
        )
    if not rows:
        raise Missing("attendance produced no rows")
    return rows


def _attended_held(html: str) -> dict[str, tuple[int, int]]:
    """Count Present/Absent rows per subject on the attendencelist page.

    Structure unconfirmed: this looks for a subject code heading followed by a log table whose
    rows carry a Present/Absent status. Raises (via the caller) if nothing is recognised.
    """
    tree = parse(html)
    counts: dict[str, tuple[int, int]] = {}
    for table in tree.css(".cn-attend-list1, .cn-attend-list2"):
        heading = table.parent.text() if table.parent is not None else ""
        code_match = _CODE.search(heading)
        if code_match is None:
            continue
        code = code_match.group(1).upper()
        attended = held = 0
        for row in table.css("tr"):
            status = row.text() or ""
            if _PRESENT.search(status):
                attended += 1
                held += 1
            elif _ABSENT.search(status):
                held += 1
        if held:
            counts[code] = (attended, held)
    return counts


def parse_results(pages: PagesByStep) -> Results:
    """SGPA per semester and the overall CGPA, read from labelled semester blocks.

    Needs an explicit semester label beside each SGPA; without it the mapping to a semester
    number is a guess, so this raises rather than number the rows by position.
    """
    html = pages["results"][0].html
    tree = parse(html)
    semesters: list[SemesterSummary] = []
    cgpa_match = _CGPA.search(tree.text() or "")
    cgpa = float(cgpa_match.group(1)) if cgpa_match else None
    for node in tree.css("*"):
        chunk = node.text(deep=False) or ""
        sem = _SEM.search(chunk)
        sgpa = _SGPA.search(chunk)
        if sem and sgpa:
            number_ = int(sem.group(1))
            if not any(s.semester == number_ for s in semesters):
                semesters.append(SemesterSummary(semester=number_, sgpa=float(sgpa.group(1))))
    if not semesters:
        raise Missing("no labelled SGPA found on the results page (calibrate parse_results)")
    semesters[-1] = semesters[-1].model_copy(update={"cgpa": cgpa})
    # Per-subject grade rows: structure unconfirmed, left empty until a capture shows the table.
    subjects: list[ResultRow] = []
    return Results(subjects=subjects, semesters=semesters)


def parse_timetable(pages: PagesByStep) -> list[TimetableSlot]:
    """Weekly slots from the timetable grid. Structure unconfirmed — calibrate against a capture."""
    tree = parse(pages["timetable"][0].html)
    slots: list[TimetableSlot] = []
    for table in tree.css("table"):
        rows = table.css("tr")
        if not rows:
            continue
        for row in rows[1:]:
            label = row.css_first("th, td")
            if label is None:
                continue
            try:
                day = Weekday(label.text(strip=True).title()[:9])
            except ValueError:
                continue
            # Period headers and cell layout differ per Contineo build; do not guess times here.
            del day  # placeholder: real slot extraction waits on a captured timetable page
    raise Missing("timetable parsing not yet calibrated against a real MSRIT page")
