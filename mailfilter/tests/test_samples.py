"""The sample mails and the scorer: the golden answers score clean, a lazy judge does not."""

from __future__ import annotations

from mailfilter.contract import OTHER, Proposal
from mailfilter.evaluate import judged_samples, score_all, score_sample
from mailfilter.fake import FakeMailbox
from mailfilter.mail import render
from mailfilter.samples import SAMPLES, golden_judge


class SaysOther:
    name = "other"

    def judge(self, rendered: str) -> Proposal:
        return OTHER


def test_thirty_invented_mails_with_unique_ids_and_markers() -> None:
    assert len(SAMPLES) == 30
    assert len({s.mail.id for s in SAMPLES}) == 30
    assert len({s.key for s in SAMPLES}) == 30
    rendered = {s.key: render(FakeMailbox([s.mail]).get(s.mail.id)).for_claude for s in SAMPLES}  # type: ignore[union-attr]
    for sample in SAMPLES:
        holders = [key for key, text in rendered.items() if sample.marker in text]
        assert holders == [sample.key], sample.key


def test_every_link_and_address_is_invented() -> None:
    for sample in SAMPLES:
        raw = sample.mail.raw.decode("latin-1")
        for domain in ("gmail.com", "msrit", "ramaiah"):
            assert domain not in raw.lower(), sample.key


def test_the_golden_answers_score_clean() -> None:
    scores = score_all(golden_judge())
    assert [s.key for s in scores if not s.passed] == []
    assert len(scores) == 28  # sent mail and drafts never reach a judge


def test_a_judge_that_keeps_nothing_fails_every_kept_mail() -> None:
    lazy = SaysOther()
    for sample in judged_samples():
        passed = score_sample(sample, lazy).passed
        assert passed == (sample.expect.kind == "other"), sample.key
