"""Record a team member's own visit to their portal, for the forge to learn the portal from.

A Chromium window opens on the login page. The team member logs in themselves and clicks
through every page PortMax needs (attendance for each course, internal marks, timetable,
results, profile), then closes the window. Only the portal's own traffic is recorded. The raw
recording holds their cookies and personal details: it stays on their laptop under `captures/`
(never committed) and goes through `portmax forge sanitize` before anything else reads it.
"""

from __future__ import annotations

import os
import re
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

PAGES_TO_VISIT = """# What I saw

Fill this in from the portal screen while you capture; the reviewer checks the connector's
answers against it. Use your own numbers, they never leave your laptop.

- Attendance, one line per course (code, attended of held, percentage):
- Internal marks for one course (component, scored of maximum):
- Timetable, Monday's classes:
- Latest SGPA and CGPA:
"""


@dataclass(frozen=True)
class Capture:
    har: Path
    notes: Path


def capture(
    login_url: str,
    out_dir: Path,
    *,
    driver: Callable[[Any], None] | None = None,
    headless: bool | None = None,
    user_agent: str | None = None,
) -> Capture:
    """Open the portal, let the person (or, for the mock only, `driver`) browse, save the HAR."""
    from playwright.sync_api import sync_playwright

    # Some Linux machines share one browser install there; everywhere else (Windows, macOS)
    # Playwright's own default location is the right one.
    if os.path.isdir("/opt/pw-browsers"):
        os.environ.setdefault("PLAYWRIGHT_BROWSERS_PATH", "/opt/pw-browsers")
    out_dir.mkdir(parents=True, exist_ok=True)
    har = out_dir / "raw.har"
    notes = out_dir / "what-i-saw.md"
    if not notes.exists():
        notes.write_text(PAGES_TO_VISIT)
    host = urlsplit(login_url).netloc
    only_portal = re.compile(rf"^https?://{re.escape(host)}/")
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=driver is not None if headless is None else headless)
        context = browser.new_context(
            record_har_path=str(har),
            record_har_content="embed",
            record_har_url_filter=only_portal,
            user_agent=user_agent,
        )
        page = context.new_page()
        page.goto(login_url)
        if driver is not None:
            driver(page)
            page.wait_for_load_state("load")
        else:
            page.wait_for_event("close", timeout=0)  # the person closes the tab when done
        context.close()  # writes the HAR
        browser.close()
    return Capture(har=har, notes=notes)
