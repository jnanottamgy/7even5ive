"""The whole forge on the mock portal: capture in a real browser, sanitise, fixtures from the
recording, verify, accept golden answers, publish. The engineer step is stood in for by copying
the hand-written connector, because the real one needs a model; its prompt is tested on its own.
"""

from __future__ import annotations

import json
import shutil
from datetime import date
from pathlib import Path
from typing import Any

import pytest

from portmax.connector import CONNECTORS_DIR
from portmax.forge import workflow
from portmax.forge.capture import capture
from portmax.forge.engineer import EngineerJob, build_prompts, run_engineer
from portmax.forge.sanitize import Identity, sanitize
from portmax.forge.verify import verify
from portmax.mock_portal.data import expected_attendance
from tests.conftest import LivePortal

WHO = Identity(usn="1MC24CS042", name="Asha Rao", dob=date(2005, 8, 14), phone="9845012345")


def student_clicks_through(page: Any) -> None:
    """The team member's visit, scripted for the mock only: log in, open every page once."""
    page.fill("input[name=username]", "1MC24CS042")
    page.select_option("select[name=dd]", "14")
    page.select_option("select[name=mm]", "08")
    page.select_option("select[name=yyyy]", "2005")
    page.fill("input[name=captcha]", "PM42X")
    page.click("button[type=submit]")
    page.fill("input[name=parent_digits]", "2345")
    page.click("button[type=submit]")
    page.wait_for_url("**task=dashboard")
    # Click, never type URLs: a typed URL sends no Referer, and the portal logs out on the spot.
    for i in range(len(page.query_selector_all("a.pm-course"))):
        page.click(f"a.pm-course >> nth={i}")
        page.click("a.pm-cie")
        page.click("text=Dashboard")
    for section in ("Timetable", "Results"):
        page.click(f"text={section}")
        page.click("text=Dashboard")


@pytest.fixture
def recorded(live_portal: LivePortal, tmp_path: Path) -> tuple[Path, dict[str, Any], set[str], str]:
    done = capture(
        f"{live_portal.url}/index.php", tmp_path / "captures", driver=student_clicks_through
    )
    raw = json.loads(done.har.read_text())
    session_cookie = next(
        c["value"]
        for e in raw["log"]["entries"]
        for c in e["response"].get("cookies", [])
        if c["name"] == "PORTALSESSID"
    )
    clean, report = sanitize(raw, WHO)
    clean_path = tmp_path / "captures" / "sanitized.har"
    clean_path.write_text(json.dumps(clean))
    return clean_path, clean, report.secret_hashes, session_cookie


@pytest.fixture
def draft(tmp_path: Path) -> Path:
    """What the engineer step writes; here, the hand-written connector stands in for the model."""
    folder = tmp_path / "drafts" / "mockcollege"
    folder.mkdir(parents=True)
    for name in ("manifest.yaml", "fetch_plan.json", "parsers.py"):
        shutil.copy(CONNECTORS_DIR / "mockcollege" / name, folder / name)
    return folder


pytestmark = pytest.mark.browser


def test_the_recording_holds_no_session_or_personal_detail(
    recorded: tuple[Path, dict[str, Any], set[str], str],
) -> None:
    _, clean, _, cookie = recorded
    text = json.dumps(clean)
    for secret in (cookie, "1MC24CS042", "Asha Rao", "14-08-2005", "PM42X"):
        assert secret not in text


def test_a_draft_built_from_the_recording_verifies_and_publishes(
    recorded: tuple[Path, dict[str, Any], set[str], str],
    draft: Path,
    tmp_path: Path,
    live_portal: LivePortal,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    har, _, hashes, _ = recorded
    assert workflow.fixtures_from_capture(draft, har) == 15
    before_review = verify(draft, secret_hashes=hashes, require_golden=False)
    assert before_review.ok, before_review.checks
    answers = workflow.current_answers(draft)
    truth = expected_attendance(live_portal.state.student("1MC24CS042"))
    assert answers["get_attendance"] == [row.model_dump(mode="json") for row in truth]
    assert answers["get_profile"]["usn"] == "USN0000001"  # the stand-in, never the real USN
    workflow.accept_golden(draft)  # after a person checks the answers against the screen
    assert verify(draft, secret_hashes=hashes).ok
    monkeypatch.setattr(workflow, "CONNECTORS_DIR", tmp_path / "connectors")
    published = workflow.publish(
        draft, secret_hashes=hashes, made_by={"hand_written": False, "model": "test"}
    )
    assert (published / "golden" / "get_attendance.json").exists()


@pytest.mark.parametrize(
    ("change", "failing"),
    [
        ('_TITLE = re.compile(r"Database Management Systems")\n', "hard-codes no answers"),
        ("import httpx\n", "parsers are pure"),
        ("data = open('/etc/passwd').read()\n", "parsers are pure"),
        ("SESSION = '{cookie}'\n", "leaks nothing from the capture"),
    ],
)
def test_verify_catches_what_a_model_might_get_wrong(
    recorded: tuple[Path, dict[str, Any], set[str], str],
    draft: Path,
    change: str,
    failing: str,
) -> None:
    har, _, hashes, cookie = recorded
    workflow.fixtures_from_capture(draft, har)
    workflow.accept_golden(draft)
    parsers = draft / "parsers.py"
    parsers.write_text(parsers.read_text() + "\n" + change.format(cookie=cookie))
    failed = {c.name for c in verify(draft, secret_hashes=hashes).checks if not c.ok}
    assert failing in failed


def test_the_engineer_prompt_carries_the_rules(tmp_path: Path) -> None:
    job = EngineerJob(
        college="mockcollege",
        draft_dir=tmp_path / "drafts" / "mockcollege",
        har_path=tmp_path / "sanitized.har",
        report_path=tmp_path / "sanitize-report.json",
    )
    system, user = build_prompts(job)
    assert "$" not in system.replace("$ ", "")  # every placeholder filled
    for rule in ("Never write a cookie", "Never hard-code an answer", "bot detection", "GET"):
        assert rule in system
    assert "hardcode all credentials" not in system.lower()  # RAE's default is gone
    assert str(job.draft_dir.resolve()) in user


def test_the_engineer_refuses_to_run_without_a_model(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("CLAUDE_CODE_USE_BEDROCK", raising=False)
    job = EngineerJob("mockcollege", tmp_path, tmp_path / "x.har", tmp_path / "r.json")
    with pytest.raises(RuntimeError, match="needs a model"):
        run_engineer(job)
