"""Loads a college's connector and turns its pages into the five tools' answers."""

from __future__ import annotations

import importlib
import importlib.util
import json
import re
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from types import ModuleType
from typing import Any

import yaml
from pydantic import TypeAdapter, ValidationError

from portmax.contract import (
    AttendanceRow,
    MarkRow,
    Profile,
    Results,
    TimetableSlot,
    ToolName,
)
from portmax.errors import NotSupported, PortalChanged
from portmax.htmlkit import Missing
from portmax.manifest import Manifest
from portmax.pages import PagesByStep
from portmax.plan import FetchPlan

CONNECTORS_DIR = Path(__file__).parent / "connectors"

# What each tool's parser must return. Parsers are generated code, so their output is
# re-validated here rather than trusted.
TOOL_TYPES: dict[ToolName, Any] = {
    "get_attendance": list[AttendanceRow],
    "get_timetable": list[TimetableSlot],
    "get_marks": list[MarkRow],
    "get_results": Results,
    "get_profile": Profile,
}


def parser_name(tool: ToolName) -> str:
    return "parse_" + tool.removeprefix("get_")


@dataclass(frozen=True)
class Connector:
    manifest: Manifest
    plan: FetchPlan
    parsers: ModuleType
    root: Path

    @property
    def college(self) -> str:
        return self.manifest.college

    def parse(self, tool: ToolName, pages: PagesByStep) -> Any:
        """Run one tool's parser over the pages it needs; refuse to guess when anything is off."""
        if tool not in self.manifest.tools:
            raise NotSupported(f"{self.college} has no {tool}")
        needed = self.plan.tool_steps.get(tool, [])
        missing = [step for step in needed if not pages.get(step)]
        if missing:
            raise PortalChanged(f"{tool}: no pages for {missing}")
        function = getattr(self.parsers, parser_name(tool), None)
        if function is None:
            raise NotSupported(f"{self.college} has no parser for {tool}")
        try:
            result = function({step: list(pages[step]) for step in needed})
            return TypeAdapter(TOOL_TYPES[tool]).validate_python(result)
        except (Missing, ValidationError, ValueError, KeyError, IndexError, AttributeError) as e:
            raise PortalChanged(f"{tool}: {type(e).__name__}: {e}") from e


def load_connector(college: str, root: Path | None = None) -> Connector:
    folder = (root or CONNECTORS_DIR) / college
    manifest = Manifest.model_validate(yaml.safe_load((folder / "manifest.yaml").read_text()))
    plan = FetchPlan.model_validate(json.loads((folder / "fetch_plan.json").read_text()))
    if manifest.college != college:
        raise ValueError(f"{folder} holds {manifest.college}, not {college}")
    if root is None:
        parsers = importlib.import_module(f"portmax.connectors.{college}.parsers")
    else:
        spec = importlib.util.spec_from_file_location(
            f"portmax_connector_{college}", folder / "parsers.py"
        )
        if spec is None or spec.loader is None:
            raise ValueError(f"no parsers.py in {folder}")
        parsers = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(parsers)
    return Connector(manifest=manifest, plan=plan, parsers=parsers, root=folder)


def parse_portal_origins(spec: str) -> dict[str, str]:
    """`college=origin,...` (PORTMAX_PORTAL_ORIGINS or `portmax api --portal-origin`).

    Why: the mock portal's manifest says 127.0.0.1, but a phone on the same Wi-Fi reaches it at
    the laptop's LAN address, and uploads are refused unless every page came from base_url. The
    check stays; this only says where the one allowed portal lives on this machine.
    """
    origins: dict[str, str] = {}
    for item in spec.split(","):
        if not item.strip():
            continue
        college, sep, origin = item.partition("=")
        if not sep or not college.strip() or not origin.strip():
            raise ValueError(
                f"portal origin must be college=http://host[:port], got {item.strip()!r}"
            )
        origin = origin.strip().rstrip("/")
        if not re.fullmatch(r"https?://[^/\s]+", origin):
            raise ValueError(f"portal origin must be scheme and host only, got {origin!r}")
        origins[college.strip()] = origin
    return origins


def with_portal_origins(
    origins: dict[str, str],
    load: Callable[[str], Connector] = load_connector,
) -> Callable[[str], Connector]:
    """A connector loader that moves the named colleges' base_url, validated like the manifest."""

    def loader(college: str) -> Connector:
        connector = load(college)
        origin = origins.get(college)
        if origin is None:
            return connector
        # model_copy changes only base_url. A dump-and-validate round trip would also turn
        # refresh_minutes 180 into 180.0 and change the settings the phone receives.
        manifest = connector.manifest.model_copy(update={"base_url": origin})
        return Connector(
            manifest=manifest, plan=connector.plan, parsers=connector.parsers, root=connector.root
        )

    return loader
