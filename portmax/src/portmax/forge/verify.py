"""The gate a connector must pass before it serves a single student.

1. It loads: manifest and fetch plan are valid, and every path in the plan is read-only.
2. Its parsers are pure: no network, files, processes or dynamic code.
3. Its fixtures are logged-in pages of the portal, at read-only paths.
4. It replays offline: parsing the fixtures gives the golden answers a person checked.
5. It hard-codes no answers: no subject, room or score from the golden files is in the code.
6. It leaks nothing: no captured cookie, token or personal detail is in the code.
"""

from __future__ import annotations

import ast
import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

from portmax.connector import Connector, load_connector
from portmax.executor import check_session
from portmax.forge.fixtures import golden_path, load_fixtures, load_golden, replay
from portmax.forge.sanitize import digest
from portmax.plan import check_path

ALLOWED_IMPORTS = {
    "__future__",
    "re",
    "datetime",
    "typing",
    "decimal",
    "math",
    "collections",
    "itertools",
    "functools",
    "enum",
    "portmax.contract",
    "portmax.htmlkit",
    "portmax.pages",
}
FORBIDDEN_CALLS = {
    "open",
    "eval",
    "exec",
    "compile",
    "__import__",
    "input",
    "breakpoint",
    "globals",
    "locals",
    "vars",
    "setattr",
    "delattr",
}
_WORD = re.compile(r"[A-Za-z0-9_\-+./=]{4,}")


@dataclass(frozen=True)
class Check:
    name: str
    ok: bool
    detail: str = ""


@dataclass
class VerifyReport:
    checks: list[Check] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return all(check.ok for check in self.checks)

    def add(self, name: str, problems: list[str]) -> None:
        self.checks.append(Check(name, not problems, "; ".join(problems[:5])))


def impure_parser_code(source: str) -> list[str]:
    problems: list[str] = []
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Import | ast.ImportFrom):
            names = (
                [alias.name for alias in node.names]
                if isinstance(node, ast.Import)
                else [node.module or ""]
            )
            for name in names:
                if name not in ALLOWED_IMPORTS:
                    problems.append(f"imports {name}")
        elif isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
            if node.func.id in FORBIDDEN_CALLS:
                problems.append(f"calls {node.func.id}()")
        elif isinstance(node, ast.Attribute) and node.attr.startswith("__"):
            problems.append(f"reaches into {node.attr}")
    return problems


def _answer_strings(value: Any) -> set[str]:
    """Distinctive values from a golden answer: names, codes, rooms, decimal scores."""
    found: set[str] = set()
    if isinstance(value, dict):
        for item in value.values():
            found |= _answer_strings(item)
    elif isinstance(value, list):
        for item in value:
            found |= _answer_strings(item)
    elif isinstance(value, str) and len(value) >= 4 and not re.fullmatch(r"[\d:\-T.]+", value):
        found.add(value)
    elif isinstance(value, float) and not value.is_integer():
        found.add(repr(value))
    return found


def verify(
    folder: Path, *, secret_hashes: set[str] | None = None, require_golden: bool = True
) -> VerifyReport:
    report = VerifyReport()
    try:
        connector: Connector = load_connector(folder.name, root=folder.parent)
    except Exception as error:  # any failure to load is the finding itself
        report.add("loads", [f"{type(error).__name__}: {error}"])
        return report
    report.add("loads", [])

    parsers_source = (folder / "parsers.py").read_text()
    report.add("parsers are pure", impure_parser_code(parsers_source))

    fixture_problems: list[str] = []
    try:
        pages = load_fixtures(folder / "fixtures")
    except FileNotFoundError:
        pages = []
        fixture_problems.append("no fixtures: run `portmax forge fixtures` first")
    for page in pages:
        parts = urlsplit(page.url)
        try:
            check_path(parts.path + (f"?{parts.query}" if parts.query else ""))
            check_session(page, connector.manifest.markers)
        except Exception as error:
            fixture_problems.append(f"{page.step}: {error}")
    report.add("fixtures are logged-in, read-only pages", fixture_problems)

    golden_problems: list[str] = []
    golden: dict[str, Any] = {
        path.stem: json.loads(path.read_text()) for path in (folder / "golden").glob("*.json")
    }
    if pages and not fixture_problems:
        try:
            answers = replay(connector)
        except Exception as error:
            answers = {}
            golden_problems.append(f"replay failed: {error}")
        for tool, parsed in answers.items():
            if not golden_path(connector, tool).exists():
                if require_golden:
                    golden_problems.append(f"{tool}: no golden file; review and accept it")
                continue
            expected = load_golden(connector, tool)
            if parsed != expected:
                golden_problems.append(f"{tool}: parsed answer differs from the golden file")
    elif require_golden:
        golden_problems.append("cannot replay without valid fixtures")
    report.add("replays to the golden answers", golden_problems)

    code = parsers_source + (folder / "fetch_plan.json").read_text()
    hardcoded = sorted(value for value in _answer_strings(golden) if value in code)
    report.add(
        "hard-codes no answers", [f"{value!r} is written into the code" for value in hardcoded]
    )

    leaked: list[str] = []
    if secret_hashes:
        for name in ("parsers.py", "fetch_plan.json", "manifest.yaml"):
            for word in set(_WORD.findall((folder / name).read_text())):
                if digest(word) in secret_hashes:
                    leaked.append(f"{name} contains a captured secret")
                    break
    report.add("leaks nothing from the capture", leaked)
    return report
