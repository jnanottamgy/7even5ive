"""The serverless demo's own parts: keys from Parameter Store at a cold start, and the tick that
stands in for a server's background loop."""

from __future__ import annotations

import pytest

import os

from seventy5 import lambda_demo


class FakeSsm:
    def __init__(self, pages):
        self.pages, self.calls = pages, []

    def get_parameters_by_path(self, **kwargs):
        self.calls.append(kwargs)
        return self.pages[len(self.calls) - 1]


def test_parameters_become_settings_and_real_variables_win(monkeypatch):
    monkeypatch.setenv("ALREADY_SET", "from-the-console")
    monkeypatch.delenv("X_ELEVEN", raising=False)
    monkeypatch.delenv("X_GOOGLE", raising=False)
    ssm = FakeSsm([
        {"Parameters": [{"Name": "/7even5ive-demo/X_ELEVEN", "Value": "xi"},
                        {"Name": "/7even5ive-demo/ALREADY_SET", "Value": "from-ssm"}],
         "NextToken": "page-2"},
        {"Parameters": [{"Name": "/7even5ive-demo/X_GOOGLE", "Value": "cid"}]},
    ])
    names = lambda_demo.load_settings("/7even5ive-demo", ssm)
    assert sorted(names) == ["X_ELEVEN", "X_GOOGLE"]
    assert os.environ["X_ELEVEN"] == "xi" and os.environ["ALREADY_SET"] == "from-the-console"
    assert ssm.calls[0] == {"Path": "/7even5ive-demo", "WithDecryption": True, "Recursive": False}
    assert ssm.calls[1]["NextToken"] == "page-2"


def test_an_unreadable_parameter_store_stops_the_start_and_says_why():
    """Not stand-ins for the instance's whole life (that would quietly be the offline demo):
    the start fails, the log names the kind of error, the next request tries again."""
    class Refused:
        def get_parameters_by_path(self, **kwargs):
            raise PermissionError("AccessDenied")

    with pytest.raises(lambda_demo.SettingsNotLoaded, match="PermissionError"):
        lambda_demo.load_settings("/7even5ive-demo", Refused())
    assert lambda_demo.load_settings(None) == []  # no Parameter Store named: nothing to read


def test_the_tick_budget_follows_the_time_lambda_has_left(monkeypatch):
    seen = {}

    class Context:
        def get_remaining_time_in_millis(self):
            return 15000  # a cold start used most of the minute

    class FakeApp:
        @property
        def deadline(self):
            return seen.get("deadline")

        @deadline.setter
        def deadline(self, value):
            if value is not None:
                seen["deadline"] = value

    class FakeRouter:
        app = FakeApp()

    import time

    monkeypatch.setattr(lambda_demo, "_ensure", lambda: None)
    monkeypatch.setattr(lambda_demo, "_router", FakeRouter())
    monkeypatch.setattr(lambda_demo, "_scheduler", type("S", (), {"jobs": []})())
    start = time.monotonic()
    lambda_demo.tick(Context())
    assert seen["deadline"] - start <= 15 - lambda_demo.TICK_RESERVE_SECONDS + 0.5


def test_the_startup_report_names_features_never_values(monkeypatch):
    from dataclasses import replace

    from seventy5 import report

    monkeypatch.setattr(report, "settings", replace(
        report.settings, elevenlabs_api_key="xi-secret-value", elevenlabs_assistant_agent_id="agent_1",
        google_client_id="", demo_student_phone="+919812345678"))
    text = "\n".join(report.lines())
    assert "live      ElevenLabs voice assistant" in text
    assert "stand-in  Google sign-in" in text
    assert "xi-secret-value" not in text and "9812345678" not in text
