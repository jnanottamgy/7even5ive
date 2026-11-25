"""Scoring a judge on the sample mails: what ended up on the card, never the wording.

`golden_judge()` must score clean (the expectations and the checks agree), and a judge that
answers "other" to everything must fail every kept sample (the scorer is not vacuous). The real
eval asks Claude on Bedrock: `mailfilter eval`, or `RUN_EVALS=1 uv run pytest -m real_model`.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from mailfilter.checks import check
from mailfilter.errors import JudgeFailed
from mailfilter.fake import FakeMailbox
from mailfilter.judge import Judge
from mailfilter.mail import SKIP_LABELS, render
from mailfilter.samples import SAMPLES, Sample


@dataclass
class Score:
    key: str
    problems: list[str] = field(default_factory=list)

    @property
    def passed(self) -> bool:
        return not self.problems


def judged_samples() -> list[Sample]:
    """The samples a judge ever sees: sent mail and drafts never reach Claude."""
    return [sample for sample in SAMPLES if not sample.mail.labels & SKIP_LABELS]


def score_sample(sample: Sample, judge: Judge) -> Score:
    score = Score(sample.key)
    mail = FakeMailbox([sample.mail]).get(sample.mail.id)
    if mail is None:
        score.problems.append("mail missing")
        return score
    rendered = render(mail)
    try:
        proposal = judge.judge(rendered.for_claude)
    except JudgeFailed as error:
        score.problems.append(f"judge failed: {error.detail}")
        return score
    checked = check(proposal, mail, rendered.checkable)
    expect = sample.expect
    got_kind = checked.kind or "other"
    if got_kind != expect.kind:
        score.problems.append(f"kind {got_kind}, expected {expect.kind}")
        return score
    if expect.kind == "other":
        return score
    deadline = checked.deadline.strftime("%Y-%m-%dT%H:%M") if checked.deadline else None
    if deadline != expect.deadline:
        score.problems.append(f"deadline {deadline}, expected {expect.deadline}")
    event = None
    if checked.event_date is not None:
        layout = "%Y-%m-%dT%H:%M" if checked.event_has_time else "%Y-%m-%d"
        event = checked.event_date.strftime(layout)
    if event != expect.event:
        score.problems.append(f"event {event}, expected {expect.event}")
    if checked.form_link != expect.link:
        score.problems.append(f"link {checked.form_link}, expected {expect.link}")
    return score


def score_all(judge: Judge) -> list[Score]:
    return [score_sample(sample, judge) for sample in judged_samples()]
