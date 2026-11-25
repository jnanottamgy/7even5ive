import pytest
from pydantic import ValidationError

from portmax.errors import UnsafePlan
from portmax.manifest import (
    SessionRules,
    keepalive_interval_minutes,
    needs_push_wakeup,
)
from portmax.plan import FetchPlan, check_path, resolve_link

BASE = "https://portal.example.edu"


@pytest.mark.parametrize(
    "path",
    [
        "/index.php?option=com_dashboard&task=dashboard",
        "/index.php?option=com_results&task=credits",  # "credits" must not trip "edit"
        "/attendance/CS52",
    ],
)
def test_read_paths_pass(path: str) -> None:
    assert check_path(path) == path


@pytest.mark.parametrize(
    "path",
    [
        "/index.php?option=com_users&task=logout",
        "/index.php?task=saveProfile",  # camelCase is split before matching
        "/fees/pay_now",
        "/account/change-password",
        "https://evil.example.com/steal",
        "//evil.example.com/steal",
        "",
    ],
)
def test_paths_that_change_or_leave_are_refused(path: str) -> None:
    with pytest.raises(UnsafePlan):
        check_path(path)


def test_links_found_on_a_page_must_stay_on_the_portal() -> None:
    page = f"{BASE}/index.php?task=dashboard"
    assert resolve_link(BASE, page, "index.php?task=course&code=CS52") == (
        "/index.php?task=course&code=CS52"
    )
    with pytest.raises(UnsafePlan):
        resolve_link(BASE, page, "https://elsewhere.example.com/x")
    with pytest.raises(UnsafePlan):
        resolve_link(BASE, page, "index.php?option=com_users&task=logout")


def plan(**overrides: object) -> FetchPlan:
    fields: dict[str, object] = {
        "version": "1",
        "steps": [
            {"id": "dashboard", "path": "/dash"},
            {"id": "course", "for_each": {"from": "dashboard", "select": "a.course"}},
        ],
        "keepalive_step": "dashboard",
        "tool_steps": {"get_attendance": ["course"]},
    }
    fields.update(overrides)
    return FetchPlan.model_validate(fields)


def test_a_well_formed_plan_loads() -> None:
    assert plan().step("course").for_each is not None


@pytest.mark.parametrize(
    "overrides",
    [
        {"keepalive_step": "course"},  # keep-alive must be one fixed page
        {"tool_steps": {"get_attendance": ["nowhere"]}},
        {"steps": [{"id": "course", "for_each": {"from": "dashboard", "select": "a"}}]},
        {"steps": [{"id": "dashboard", "path": "/x?task=logout"}]},
        {"steps": [{"id": "dashboard", "path": "/x", "method": "POST"}]},  # no methods exist
    ],
)
def test_malformed_or_unsafe_plans_are_refused(overrides: dict[str, object]) -> None:
    with pytest.raises((ValidationError, UnsafePlan)):
        plan(**overrides)


@pytest.mark.parametrize(
    ("timeout", "interval", "push"),
    [
        (None, 15.0, False),  # unmeasured: as often as WorkManager allows
        (60.0, 48.0, False),  # the longest interval with a fifth kept as margin
        (24 * 60.0, 24 * 60.0 * 0.8, False),
        (12.0, 9.6, True),  # shorter than WorkManager's floor needs a push wake-up
    ],
)
def test_keepalive_interval_is_the_longest_safe_gap(
    timeout: float | None, interval: float, push: bool
) -> None:
    rules = SessionRules(idle_timeout_minutes=timeout)
    assert keepalive_interval_minutes(rules) == pytest.approx(interval)
    assert needs_push_wakeup(rules) is push
