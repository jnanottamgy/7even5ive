"""Logging in to the mock portal from code, for tests and the local demo only.

PortMax never automates a real portal's login: there the student types everything, CAPTCHA
included, in the app's WebView. The mock's CAPTCHA is fixed in test mode so this can run.
"""

from __future__ import annotations

from typing import Any

from portmax.connector import Connector, load_connector
from portmax.executor import run_plan
from portmax.forge.fixtures import save_fixtures, save_golden
from portmax.mock_portal.app import DASHBOARD, PortalConfig, create_app
from portmax.mock_portal.data import (
    MockState,
    Student,
    default_state,
    expected_attendance,
    expected_marks,
    expected_profile,
    expected_results,
    expected_timetable,
)


def scripted_login(client: Any, student: Student, captcha: str) -> None:
    client.get("/index.php")
    client.post(
        "/index.php?option=com_login&task=step1",
        data={
            "username": student.usn,
            "dd": f"{student.dob.day:02d}",
            "mm": f"{student.dob.month:02d}",
            "yyyy": str(student.dob.year),
            "captcha": captcha,
        },
    ).raise_for_status()
    done = client.post(
        "/index.php?option=com_login&task=step2",
        data={"parent_digits": student.parent_mobile[-4:]},
        follow_redirects=False,
    )
    if done.status_code != 303:
        raise RuntimeError(f"mock login failed: HTTP {done.status_code}")


def record_mock_fixtures(state: MockState | None = None) -> Connector:
    """Re-record the mock's fixtures, and its golden files from the mock's ground truth."""
    from fastapi.testclient import TestClient

    state = state or default_state()
    config = PortalConfig(captcha="fixed")
    mock = load_connector("mockcollege")
    connector = Connector(
        mock.manifest.model_copy(update={"base_url": "http://testserver"}),
        mock.plan,
        mock.parsers,
        mock.root,
    )
    student = next(iter(state.students.values()))
    with TestClient(create_app(state, config), headers={"user-agent": "PortMax recorder"}) as c:
        scripted_login(c, student, config.fixed_captcha)
        pages = run_plan(
            connector.plan,
            connector.manifest,
            c,
            landing_url=f"http://testserver/{DASHBOARD}",
            sleep=lambda _: None,
        )
    save_fixtures(pages, connector.root / "fixtures")
    save_golden(connector, "get_attendance", expected_attendance(student))
    save_golden(connector, "get_marks", expected_marks(student))
    save_golden(connector, "get_timetable", expected_timetable(student))
    save_golden(connector, "get_results", expected_results(student))
    save_golden(connector, "get_profile", expected_profile(student))
    return connector
