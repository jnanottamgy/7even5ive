"""The phone, simulated: a real Chromium logs in to the mock portal and runs the JS runner.

This is what the Android app's WebView will do. The login here is scripted because it is our own
mock with a fixed CAPTCHA; on a real portal the student types it.
"""

from __future__ import annotations

import os
import socket
import threading
import time
from collections.abc import Iterator
from dataclasses import dataclass
from typing import Any

import pytest
import uvicorn

from portmax.api import RUNNER_JS, phone_settings
from portmax.connector import Connector
from portmax.contract import utc_now
from portmax.ingest import ingest
from portmax.mock_portal.app import MockPortal, PortalConfig, create_app
from portmax.mock_portal.data import MockState, default_state, expected_attendance
from portmax.pages import Page
from portmax.store import Store
from portmax.tools import answer
from tests.conftest import PHONE_UA

os.environ.setdefault("PLAYWRIGHT_BROWSERS_PATH", "/opt/pw-browsers")
playwright = pytest.importorskip("playwright.sync_api")

pytestmark = pytest.mark.browser

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


@pytest.fixture
def phone(live_portal: LivePortal) -> Iterator[Any]:
    """A WebView stand-in: the student logs in, then the app injects the runner."""
    with playwright.sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_context(user_agent=PHONE_UA).new_page()
        page.goto(f"{live_portal.url}/index.php")
        page.fill("input[name=username]", "1MC24CS042")
        page.select_option("select[name=dd]", "14")
        page.select_option("select[name=mm]", "08")
        page.select_option("select[name=yyyy]", "2005")
        page.fill("input[name=captcha]", "PM42X")
        page.click("button[type=submit]")
        page.fill("input[name=parent_digits]", "2345")
        page.click("button[type=submit]")
        page.wait_for_url("**task=dashboard")
        page.add_script_tag(path=str(RUNNER_JS))
        yield page
        browser.close()


def settings_for(connector: Connector) -> dict[str, Any]:
    settings = phone_settings(connector)
    settings["plan"]["pace_ms"] = 0
    return settings


def test_the_runner_reads_the_portal_inside_the_students_session(
    phone: Any, live_portal: LivePortal, connector: Connector, store: Store
) -> None:
    raw = phone.evaluate("s => PortMaxRunner.run(s)", settings_for(connector))
    pages = [Page.model_validate(p) for p in raw]
    assert [p.step for p in pages].count("course") == 6
    ingest(store, connector, "asha", pages, utc_now())
    student = live_portal.state.student("1MC24CS042")
    assert answer(store, "asha", "get_attendance", utc_now()).data == expected_attendance(student)
    assert live_portal.portal.ended == []  # the student's own session was never disturbed


def test_pings_inside_the_timeout_keep_the_login_and_it_lapses_without_them(
    phone: Any, live_portal: LivePortal, connector: Connector
) -> None:
    settings = settings_for(connector)
    for _ in range(4):  # 8 seconds of pings against a 3-second idle timeout
        time.sleep(IDLE_TIMEOUT * 0.66)
        pinged = phone.evaluate("s => PortMaxRunner.keepAlive(s)", settings)
        assert [p["step"] for p in pinged] == ["dashboard"]
    assert live_portal.portal.ended == []
    time.sleep(IDLE_TIMEOUT + 1)
    with pytest.raises(playwright.Error, match="session_expired"):
        phone.evaluate("s => PortMaxRunner.keepAlive(s)", settings)
    assert live_portal.portal.ended == ["idle"]


def test_the_runner_refuses_a_plan_that_would_log_out(
    phone: Any, live_portal: LivePortal, connector: Connector
) -> None:
    settings = settings_for(connector)
    settings["plan"]["steps"][1]["for_each"]["select"] = "a#pm-logout"
    with pytest.raises(playwright.Error, match="unsafe_plan"):
        phone.evaluate("s => PortMaxRunner.run(s)", settings)
    assert "logout" not in live_portal.portal.ended
