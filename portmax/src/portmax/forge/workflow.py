"""The forge's steps between engineer and publish: fixtures, review, publish."""

from __future__ import annotations

import json
import shutil
from datetime import date
from pathlib import Path
from typing import Any

import yaml
from pydantic import TypeAdapter

from portmax.connector import CONNECTORS_DIR, TOOL_TYPES, Connector, load_connector
from portmax.executor import run_plan
from portmax.forge.fixtures import replay, save_fixtures, save_golden
from portmax.forge.har import HarClient, load_har
from portmax.forge.verify import VerifyReport, verify
from portmax.manifest import Manifest


def draft_connector(draft: Path) -> Connector:
    return load_connector(draft.name, root=draft.parent)


def fixtures_from_capture(draft: Path, har_path: Path) -> int:
    """Run the draft's plan against the recording; the pages it gets back become its fixtures."""
    connector = draft_connector(draft)
    har = load_har(har_path)
    client = HarClient(har)
    first_html = next(
        e["request"]["url"]
        for e in har["log"]["entries"]
        if "html" in e["response"]["content"].get("mimeType", "")
    )
    origin = "/".join(first_html.split("/")[:3])
    manifest = connector.manifest.model_copy(update={"base_url": origin})
    pages = run_plan(connector.plan, manifest, client, sleep=lambda _: None)
    save_fixtures(pages, draft / "fixtures")
    return len(pages)


def current_answers(draft: Path) -> dict[str, Any]:
    connector = draft_connector(draft)
    return {
        tool: TypeAdapter(TOOL_TYPES[tool]).dump_python(answer, mode="json")
        for tool, answer in replay(connector).items()
    }


def accept_golden(draft: Path) -> list[str]:
    """After a person has checked the answers against the portal screen: save them as golden."""
    connector = draft_connector(draft)
    accepted: list[str] = []
    for tool, answer in replay(connector).items():
        save_golden(connector, tool, answer)
        accepted.append(tool)
    return accepted


def publish(draft: Path, *, secret_hashes: set[str], made_by: dict[str, Any]) -> Path:
    """Copy a draft that passes every check into the connectors, versioned and dated."""
    report: VerifyReport = verify(draft, secret_hashes=secret_hashes, require_golden=True)
    if not report.ok:
        failed = [check.name for check in report.checks if not check.ok]
        raise ValueError(f"not publishing: failed {failed}")
    target = CONNECTORS_DIR / draft.name
    manifest_data = yaml.safe_load((draft / "manifest.yaml").read_text())
    version = Manifest.model_validate(manifest_data).connector_version
    if (target / "manifest.yaml").exists():
        old = Manifest.model_validate(yaml.safe_load((target / "manifest.yaml").read_text()))
        major, minor, _ = (int(part) for part in old.connector_version.split("."))
        version = f"{major}.{minor + 1}.0"
    manifest_data.update(
        connector_version=version, verified_at=date.today().isoformat(), made_by=made_by
    )
    Manifest.model_validate(manifest_data)
    if target.exists():
        shutil.rmtree(target)
    shutil.copytree(draft, target, ignore=shutil.ignore_patterns(".rae", "__pycache__"))
    (target / "manifest.yaml").write_text(yaml.safe_dump(manifest_data, sort_keys=False))
    (target / "__init__.py").touch()
    return target


def load_report_hashes(path: Path | None) -> set[str]:
    if path is None or not path.exists():
        return set()
    hashes: list[str] = json.loads(path.read_text()).get("secret_hashes", [])
    return set(hashes)
