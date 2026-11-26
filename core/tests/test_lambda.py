"""The serverless demo's own parts: keys from Parameter Store at a cold start, and the tick that
stands in for a server's background loop."""

from __future__ import annotations

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


def test_no_permission_leaves_the_stand_ins():
    class Refused:
        def get_parameters_by_path(self, **kwargs):
            raise PermissionError("AccessDenied")

    assert lambda_demo.load_settings("/7even5ive-demo", Refused()) == []
    assert lambda_demo.load_settings(None) == []


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
