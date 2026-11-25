from __future__ import annotations

from fastapi.testclient import TestClient

from portmax.mock_portal.app import DASHBOARD, FEES, LOGOUT, MockPortal
from tests.conftest import PHONE_UA, FakeClock, login, portal_get

LOGGED_IN = "id='pm-student-dashboard'"
LOGIN_FORM = "id='pm-login'"


def mock(client: TestClient) -> MockPortal:
    portal: MockPortal = client.app.state.portal  # type: ignore[attr-defined]
    return portal


def test_the_student_logs_in_and_sees_the_dashboard(portal: TestClient) -> None:
    login(portal)
    page = portal_get(portal, f"/{DASHBOARD}")
    assert LOGGED_IN in page
    assert "Database Management Systems" in page


def test_a_wrong_captcha_or_birth_date_is_refused(portal: TestClient) -> None:
    portal.get("/index.php")
    wrong_code = portal.post(
        "/index.php?option=com_login&task=step1",
        data={"username": "1MC24CS042", "dd": "14", "mm": "08", "yyyy": "2005", "captcha": "X"},
    )
    assert wrong_code.status_code == 401
    wrong_dob = portal.post(
        "/index.php?option=com_login&task=step1",
        data={"username": "1MC24CS042", "dd": "15", "mm": "08", "yyyy": "2005", "captcha": "PM42X"},
    )
    assert wrong_dob.status_code == 401


def test_without_a_session_every_page_sends_you_to_login(portal: TestClient) -> None:
    response = portal.get(f"/{DASHBOARD}", follow_redirects=False)
    assert response.status_code == 302
    assert LOGIN_FORM in portal.get(response.headers["location"]).text


def test_a_request_without_a_portal_referer_ends_the_session(portal: TestClient) -> None:
    login(portal)
    portal.get(f"/{DASHBOARD}")  # no Referer, like a script would send
    assert LOGIN_FORM in portal_get(portal, f"/{DASHBOARD}")
    assert mock(portal).ended == ["referer"]


def test_a_different_user_agent_ends_the_session(portal: TestClient) -> None:
    login(portal)
    portal.get(f"/{DASHBOARD}", headers={"referer": "http://testserver/", "user-agent": "curl/8"})
    assert LOGIN_FORM in portal_get(portal, f"/{DASHBOARD}")
    assert mock(portal).ended == ["user-agent"]


def test_an_idle_session_times_out(portal: TestClient, clock: FakeClock) -> None:
    login(portal)
    clock.advance(20 * 60 + 1)
    assert LOGIN_FORM in portal_get(portal, f"/{DASHBOARD}")
    assert mock(portal).ended == ["idle"]


def test_a_ping_inside_the_timeout_keeps_the_session_alive(
    portal: TestClient, clock: FakeClock
) -> None:
    login(portal)
    for _ in range(6):  # two hours of pings every 16 minutes against a 20-minute timeout
        clock.advance(16 * 60)
        assert LOGGED_IN in portal_get(portal, f"/{DASHBOARD}")
    assert mock(portal).ended == []


def test_a_second_login_ends_the_first(portal: TestClient) -> None:
    login(portal)
    with TestClient(portal.app, headers={"user-agent": PHONE_UA}) as parents_phone:
        login(parents_phone)
        assert LOGGED_IN in portal_get(parents_phone, f"/{DASHBOARD}")
    assert LOGIN_FORM in portal_get(portal, f"/{DASHBOARD}")
    assert mock(portal).ended == ["replaced"]
    assert mock(portal).live_sessions("1MC24CS042") == 1


def test_logout_ends_the_session(portal: TestClient) -> None:
    login(portal)
    portal_get(portal, f"/{LOGOUT}")
    assert LOGIN_FORM in portal_get(portal, f"/{DASHBOARD}")


def test_the_portal_has_pages_portmax_must_never_touch(portal: TestClient) -> None:
    login(portal)
    page = portal_get(portal, f"/{FEES}")
    assert "task=paynow" in page
