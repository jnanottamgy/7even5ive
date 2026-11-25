from __future__ import annotations

import socket
import threading
import time
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path

import pytest
import uvicorn
from fastapi.testclient import TestClient

from portmax.connector import Connector, load_connector
from portmax.executor import run_plan
from portmax.mock_portal.app import DASHBOARD, MockPortal, PortalConfig, create_app
from portmax.mock_portal.data import MockState, default_state
from portmax.pages import Page
from portmax.store import Store

PHONE_UA = "Mozilla/5.0 (Linux; Android 14; Pixel 8) AppleWebKit/537.36 Chrome/131.0 Mobile"
PORTAL = "http://testserver"


class FakeClock:
    """The portal's clock, moved by hand so timeouts are tested in milliseconds."""

    def __init__(self) -> None:
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += seconds


@pytest.fixture
def clock() -> FakeClock:
    return FakeClock()


@pytest.fixture
def state() -> MockState:
    return default_state()


@pytest.fixture
def config(clock: FakeClock) -> PortalConfig:
    return PortalConfig(captcha="fixed", clock=clock, idle_timeout_seconds=20 * 60)


@pytest.fixture
def portal(state: MockState, config: PortalConfig) -> Iterator[TestClient]:
    with TestClient(create_app(state, config), headers={"user-agent": PHONE_UA}) as client:
        yield client


def login(client: TestClient, usn: str = "1MC24CS042") -> None:
    """Do what the student does in the app's WebView: both login steps, CAPTCHA included."""
    client.get("/index.php")
    step1 = client.post(
        "/index.php?option=com_login&task=step1",
        data={"username": usn, "dd": "14", "mm": "08", "yyyy": "2005", "captcha": "PM42X"},
    )
    assert step1.status_code == 200, step1.text
    step2 = client.post(
        "/index.php?option=com_login&task=step2",
        data={"parent_digits": "2345"},
        follow_redirects=False,
    )
    assert step2.status_code == 303, step2.text
    assert step2.headers["location"] == f"/{DASHBOARD}"


def portal_get(client: TestClient, path: str) -> str:
    """A logged-in page view, sent the way a browser sends it: with a Referer from the portal."""
    response = client.get(path, headers={"referer": f"{PORTAL}/{DASHBOARD}"})
    return response.text


@pytest.fixture
def connector() -> Connector:
    mock = load_connector("mockcollege")
    # Tests serve the mock portal at TestClient's host, not the manifest's local-demo address.
    manifest = mock.manifest.model_copy(update={"base_url": PORTAL})
    return Connector(manifest=manifest, plan=mock.plan, parsers=mock.parsers, root=mock.root)


def refresh(connector: Connector, client: TestClient, steps: list[str] | None = None) -> list[Page]:
    """What the phone does after login or on a keep-alive: run the plan in the student's session."""
    return run_plan(
        connector.plan,
        connector.manifest,
        client,
        landing_url=f"{PORTAL}/{DASHBOARD}",
        steps=steps,
        sleep=lambda _: None,
    )


@pytest.fixture
def store(tmp_path: Path) -> Store:
    # A file, not ":memory:": the API test serves requests from another thread.
    return Store(f"sqlite:///{tmp_path / 'portmax.db'}")


IDLE_TIMEOUT = 3.0  # seconds; short so the keep-alive test runs fast


@dataclass
class LivePortal:
    url: str
    portal: MockPortal
    state: MockState


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        port: int = s.getsockname()[1]
        return port


@pytest.fixture
def live_portal() -> Iterator[LivePortal]:
    state = default_state()
    app = create_app(state, PortalConfig(captcha="fixed", idle_timeout_seconds=IDLE_TIMEOUT))
    port = _free_port()
    server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning"))
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    while not server.started:
        time.sleep(0.02)
    yield LivePortal(f"http://127.0.0.1:{port}", app.state.portal, state)
    server.should_exit = True
    thread.join(timeout=5)
