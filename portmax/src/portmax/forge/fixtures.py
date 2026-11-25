"""Recorded pages (fixtures) and checked answers (golden files) for a connector.

Fixtures are sanitised portal pages saved with the connector; golden files are the answers a
person checked against the portal screen. Together they let CI prove a connector still reads
every page correctly with the network switched off.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

from pydantic import TypeAdapter

from portmax.connector import TOOL_TYPES, Connector
from portmax.contract import ToolName
from portmax.pages import Page, by_step

# Fixture URLs keep only path and query; the host is replaced so no real portal address is saved.
FIXTURE_ORIGIN = "https://portal.invalid"
FIXTURE_TIME = datetime(2026, 1, 1, tzinfo=UTC)


def save_fixtures(pages: list[Page], folder: Path) -> None:
    folder.mkdir(parents=True, exist_ok=True)
    for old in folder.glob("*.html"):
        old.unlink()
    index: list[dict[str, Any]] = []
    counts: dict[str, int] = {}
    for page in pages:
        n = counts.get(page.step, 0)
        counts[page.step] = n + 1
        name = f"{page.step}-{n}.html"
        (folder / name).write_text(page.html)
        parts = urlsplit(page.url)
        path = parts.path + (f"?{parts.query}" if parts.query else "")
        index.append({"step": page.step, "file": name, "path": path, "status": page.status})
    (folder / "index.json").write_text(json.dumps(index, indent=2) + "\n")


def load_fixtures(folder: Path) -> list[Page]:
    index = json.loads((folder / "index.json").read_text())
    return [
        Page(
            step=entry["step"],
            url=FIXTURE_ORIGIN + entry["path"],
            status=entry["status"],
            html=(folder / entry["file"]).read_text(),
            fetched_at=FIXTURE_TIME,
        )
        for entry in index
    ]


def golden_path(connector: Connector, tool: ToolName) -> Path:
    return connector.root / "golden" / f"{tool}.json"


def save_golden(connector: Connector, tool: ToolName, answer: Any) -> None:
    path = golden_path(connector, tool)
    path.parent.mkdir(parents=True, exist_ok=True)
    data = TypeAdapter(TOOL_TYPES[tool]).dump_python(answer, mode="json")
    path.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n")


def load_golden(connector: Connector, tool: ToolName) -> Any:
    raw = json.loads(golden_path(connector, tool).read_text())
    return TypeAdapter(TOOL_TYPES[tool]).validate_python(raw)


def replay(connector: Connector) -> dict[ToolName, Any]:
    """Every supported tool's answer, parsed from the saved fixtures with no network at all."""
    pages = by_step(load_fixtures(connector.root / "fixtures"))
    return {tool: connector.parse(tool, pages) for tool in connector.manifest.tools}
