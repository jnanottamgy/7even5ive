from __future__ import annotations

import pytest

from portmax.connector import CONNECTORS_DIR, load_connector
from portmax.contract import TOOLS
from portmax.forge.fixtures import load_golden, replay

COLLEGES = sorted(p.name for p in CONNECTORS_DIR.iterdir() if (p / "manifest.yaml").exists())


@pytest.mark.parametrize("college", COLLEGES)
def test_every_connector_replays_to_its_golden_answers_offline(college: str) -> None:
    # A scaffolded connector that has no captured fixtures yet (verified_at null, no fixtures
    # index) is work in progress — skip it rather than fail the suite. It still fails safe at
    # runtime (any parse mismatch becomes PortalChanged), so nothing wrong is ever shown.
    if not (CONNECTORS_DIR / college / "fixtures" / "index.json").exists():
        pytest.skip(f"{college}: no fixtures captured yet")
    connector = load_connector(college)
    answers = replay(connector)
    for tool in TOOLS:
        if tool in connector.manifest.tools:
            assert answers[tool] == load_golden(connector, tool), tool
