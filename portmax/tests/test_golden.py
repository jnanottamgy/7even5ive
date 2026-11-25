from __future__ import annotations

import pytest

from portmax.connector import CONNECTORS_DIR, load_connector
from portmax.contract import TOOLS
from portmax.forge.fixtures import load_golden, replay

COLLEGES = sorted(p.name for p in CONNECTORS_DIR.iterdir() if (p / "manifest.yaml").exists())


@pytest.mark.parametrize("college", COLLEGES)
def test_every_connector_replays_to_its_golden_answers_offline(college: str) -> None:
    connector = load_connector(college)
    answers = replay(connector)
    for tool in TOOLS:
        if tool in connector.manifest.tools:
            assert answers[tool] == load_golden(connector, tool), tool
