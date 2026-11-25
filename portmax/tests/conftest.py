from __future__ import annotations

from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient

from portmax.mock_portal.app import DASHBOARD, PortalConfig, create_app
from portmax.mock_portal.data import MockState, default_state

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
