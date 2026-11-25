from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from portmax.connector import Connector
from portmax.errors import NotSupported, PortalChanged, SessionExpired
from portmax.mock_portal.app import MockPortal
from portmax.mock_portal.data import (
    MockState,
    expected_attendance,
    expected_marks,
    expected_profile,
    expected_results,
    expected_timetable,
)
from portmax.pages import by_step
from tests.conftest import FakeClock, login, refresh


def test_one_refresh_reads_every_page_once_and_nothing_else(
    portal: TestClient, connector: Connector
) -> None:
    login(portal)
    pages = refresh(connector, portal)
    counts = {step: len(found) for step, found in by_step(pages).items()}
    assert counts == {"dashboard": 1, "course": 6, "cie": 6, "timetable": 1, "results": 1}
    assert not any("fees" in p.url or "logout" in p.url for p in pages)


def test_every_tool_matches_the_portals_ground_truth(
    portal: TestClient, connector: Connector, state: MockState
) -> None:
    login(portal)
    pages = by_step(refresh(connector, portal))
    student = state.student("1MC24CS042")
    assert connector.parse("get_attendance", pages) == expected_attendance(student)
    assert connector.parse("get_marks", pages) == expected_marks(student)
    assert connector.parse("get_timetable", pages) == expected_timetable(student)
    assert connector.parse("get_results", pages) == expected_results(student)
    assert connector.parse("get_profile", pages) == expected_profile(student)


def test_new_numbers_on_the_portal_come_through(
    portal: TestClient, connector: Connector, state: MockState
) -> None:
    login(portal)
    course = state.student("1MC24CS042").courses[1]
    course.held, course.attended = 31, 22  # one more DBMS class held, and missed
    attendance = connector.parse("get_attendance", by_step(refresh(connector, portal)))
    dbms = next(row for row in attendance if row.subject_code == "CS52")
    assert (dbms.attended, dbms.held, dbms.percent) == (22, 31, 70.97)


def test_the_keep_alive_reads_one_page_and_keeps_the_session(
    portal: TestClient, connector: Connector, clock: FakeClock
) -> None:
    login(portal)
    for _ in range(4):
        clock.advance(16 * 60)
        pages = refresh(connector, portal, steps=[connector.plan.keepalive_step])
        assert [p.step for p in pages] == ["dashboard"]
    mock: MockPortal = portal.app.state.portal  # type: ignore[attr-defined]
    assert mock.ended == []


def test_an_expired_session_is_reported_not_parsed(
    portal: TestClient, connector: Connector, clock: FakeClock
) -> None:
    login(portal)
    clock.advance(21 * 60)
    with pytest.raises(SessionExpired):
        refresh(connector, portal)


def test_a_changed_page_is_refused_rather_than_guessed(
    portal: TestClient, connector: Connector
) -> None:
    login(portal)
    pages = by_step(refresh(connector, portal))
    broken = [
        page.model_copy(update={"html": page.html.replace("Classes held", "Lectures held")})
        for page in pages["course"]
    ]
    with pytest.raises(PortalChanged):
        connector.parse("get_attendance", {**pages, "course": broken})


def test_a_tool_the_college_lacks_says_so(connector: Connector) -> None:
    lacking = connector.manifest.model_copy(update={"tools": ["get_attendance"]})
    narrowed = Connector(lacking, connector.plan, connector.parsers, connector.root)
    with pytest.raises(NotSupported):
        narrowed.parse("get_timetable", {})
