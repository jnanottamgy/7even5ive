"""The engineer step: reverse-api-engineer's agent writes a draft connector from a recording.

PortMax uses reverse-api-engineer (RAE) as a pinned library and replaces exactly one thing, its
prompts, by overriding `_build_prompts`. RAE's own prompts tell the model to hard-code every
captured cookie into the client and to beat bot detection; ours forbid both and ask for a
fetch plan and pure parsers instead of a client.
"""

from __future__ import annotations

import asyncio
import os
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from string import Template
from typing import Any

import portmax.contract

PROMPT = Path(__file__).parent / "prompts" / "engineer.md"
PROJECT_DIR = Path(__file__).resolve().parents[3]


@dataclass(frozen=True)
class EngineerJob:
    college: str
    draft_dir: Path
    har_path: Path
    report_path: Path
    notes_path: Path | None = None
    model: str | None = None


def build_prompts(job: EngineerJob) -> tuple[str, str]:
    """The system prompt and opening message for the agent. Deterministic, so it is tested."""
    system = Template(PROMPT.read_text()).substitute(
        har_path=job.har_path.resolve(),
        draft_dir=job.draft_dir.resolve(),
        notes_path=job.notes_path.resolve() if job.notes_path else "(none)",
        report_path=job.report_path.resolve(),
        contract_path=Path(portmax.contract.__file__).resolve(),
        project_dir=PROJECT_DIR,
    )
    user = (
        f"Build the PortMax connector for `{job.college}` in `{job.draft_dir.resolve()}` from "
        f"the recording `{job.har_path.resolve()}`. Follow the rules in your instructions, run "
        "the checks, and stop when `portmax forge check` passes and the answers match the "
        "recording."
    )
    return system, user


def credentials_available() -> bool:
    return bool(
        os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("CLAUDE_CODE_USE_BEDROCK") == "1"
    )


def run_engineer(job: EngineerJob) -> dict[str, Any] | None:
    """Run the agent. Needs ANTHROPIC_API_KEY, or Claude on Bedrock (CLAUDE_CODE_USE_BEDROCK=1)."""
    if not credentials_available():
        raise RuntimeError(
            "the engineer needs a model: set ANTHROPIC_API_KEY, or CLAUDE_CODE_USE_BEDROCK=1 "
            "with AWS credentials for Claude on Bedrock in Mumbai (ap-south-1)"
        )
    try:
        from reverse_api.engineer import ClaudeEngineer
    except ImportError as error:
        raise RuntimeError("install the forge extra: uv sync --extra forge") from error

    class PortMaxEngineer(ClaudeEngineer):  # type: ignore[misc]
        def _build_prompts(self) -> tuple[str, str]:
            return build_prompts(job)

    stamp = datetime.now(UTC).strftime("%Y%m%d%H%M%S")
    engineer = PortMaxEngineer(
        run_id=f"portmax-{job.college}-{stamp}",
        har_path=job.har_path.resolve(),
        prompt=f"PortMax connector for {job.college}",
        model=job.model,
        output_dir=str(job.draft_dir.resolve().parent / ".rae"),
        sdk="claude",
        output_language="python",
        interactive=False,
    )
    result: dict[str, Any] | None = asyncio.run(engineer.analyze_and_generate())
    return result
