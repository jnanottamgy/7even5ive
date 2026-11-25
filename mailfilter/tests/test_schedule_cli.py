from __future__ import annotations

from datetime import datetime, time, timedelta

import pytest

from mailfilter.cli import main
from mailfilter.config import Settings, parse_times
from mailfilter.schedule import eventbridge_crons, longest_gap, next_check
from mailfilter.timekit import IST


def test_one_pm_and_nine_pm_india_time_in_eventbridge_utc() -> None:
    assert eventbridge_crons((time(13, 0), time(21, 0))) == ["cron(30 7,15 * * ? *)"]
    assert eventbridge_crons((time(13, 0), time(21, 15))) == [
        "cron(30 7 * * ? *)",
        "cron(45 15 * * ? *)",
    ]


def test_the_next_check_and_the_longest_wait() -> None:
    times = (time(13, 0), time(21, 0))
    assert next_check(datetime(2026, 12, 1, 12, 59, tzinfo=IST), times) == datetime(
        2026, 12, 1, 13, 0, tzinfo=IST
    )
    assert next_check(datetime(2026, 12, 1, 21, 0, tzinfo=IST), times) == datetime(
        2026, 12, 2, 13, 0, tzinfo=IST
    )
    assert longest_gap(times) == timedelta(hours=16)


def test_check_times_come_from_the_environment() -> None:
    assert parse_times(" 21:00, 13:00,13:00 ") == (time(13, 0), time(21, 0))
    assert Settings.from_env({"MAILFILTER_CHECK_TIMES": "9:30"}).check_times == (time(9, 30),)
    assert Settings.from_env({}).model == "anthropic.claude-haiku-5-5"
    assert Settings.from_env({}).aws_region == "ap-south-1"
    for bad in ("", "noon", "25:00"):
        with pytest.raises(ValueError):
            parse_times(bad)


def test_the_demo_and_cards_commands(
    tmp_path: object, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv("MAILFILTER_DATABASE_URL", f"sqlite:///{tmp_path}/cli.db")
    assert main(["demo"]) == 0
    assert "17 new cards, 2 updated, 9 not kept, 2 skipped" in capsys.readouterr().out
    assert main(["cards", "--include-past"]) == 0
    out = capsys.readouterr().out
    assert "Placement: Nimbus Systems Campus Drive. Last date Sat 5 Dec, 11:59 PM." in out
    assert main(["schedule"]) == 0
    assert "cron(30 7,15 * * ? *)" in capsys.readouterr().out


def test_commands_needing_google_say_what_is_missing(
    tmp_path: object, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv("MAILFILTER_DATABASE_URL", f"sqlite:///{tmp_path}/cli.db")
    monkeypatch.delenv("MAILFILTER_GOOGLE_CLIENT_ID", raising=False)
    assert main(["connect"]) == 2
    assert "gmail_config" in capsys.readouterr().err
    assert main(["cards", "--student", "nobody"]) == 2
    assert "not_connected" in capsys.readouterr().err
