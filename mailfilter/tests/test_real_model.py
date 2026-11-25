"""The real eval: Claude on Bedrock judges every sample mail. Costs money, needs AWS access.

RUN_EVALS=1 uv run pytest tests/test_real_model.py -v -s
"""

from __future__ import annotations

import os

import pytest

from mailfilter.config import Settings
from mailfilter.evaluate import score_all
from mailfilter.judge import ClaudeJudge

pytestmark = [
    pytest.mark.real_model,
    pytest.mark.skipif(
        os.environ.get("RUN_EVALS") != "1", reason="set RUN_EVALS=1 to call Bedrock"
    ),
]


def test_claude_sorts_the_sample_mails() -> None:
    settings = Settings.from_env()
    scores = score_all(ClaudeJudge.from_settings(settings))
    failed = [f"{s.key}: {'; '.join(s.problems)}" for s in scores if not s.passed]
    print(f"\n{len(scores) - len(failed)}/{len(scores)} passed with {settings.model}")
    assert failed == []
