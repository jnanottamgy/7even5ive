from __future__ import annotations

from datetime import datetime

import pytest

from mailfilter.checks import Checked, canonical_link, check, link_key, same_title
from mailfilter.contract import OTHER, DatedQuote, Proposal
from mailfilter.fake import FakeMail, FakeMailbox, build_raw
from mailfilter.mail import MailMessage, render
from mailfilter.samples import BY_KEY, proposal
from mailfilter.timekit import IST


def sample(key: str) -> tuple[MailMessage, str]:
    mail = FakeMailbox([BY_KEY[key].mail]).get(BY_KEY[key].mail.id)
    assert mail is not None
    return mail, render(mail).checkable


def judged(key: str, answer: Proposal) -> Checked:
    mail, text = sample(key)
    return check(answer, mail, text)


def nimbus(**changes: object) -> Proposal:
    return BY_KEY["nimbus_drive"].golden.model_copy(update=changes)


def test_the_right_answer_passes_whole() -> None:
    result = judged("nimbus_drive", BY_KEY["nimbus_drive"].golden)
    assert result.rejected == ()
    assert result.kind == "placement"
    assert result.deadline == datetime(2026, 12, 3, 17, 0, tzinfo=IST)
    assert result.event_date == datetime(2026, 12, 5, 10, 0, tzinfo=IST)
    assert result.event_has_time
    assert result.form_link == "https://forms.gle/NimbusDrive2027"
    assert result.role == "Graduate Engineer Trainee"


@pytest.mark.parametrize(
    ("deadline", "reason"),
    [
        (DatedQuote(value="2026-12-03T17:00", quote="register by 3 December"), "quote_not_in_mail"),
        (
            DatedQuote(value="2026-12-04T17:00", quote="on or before Thursday, 3 December 2026"),
            "date_not_in_quote",
        ),
        (
            DatedQuote(value="2026-12-03T18:00", quote="3 December 2026, 5:00 PM"),
            "time_not_in_quote",
        ),
        (DatedQuote(value="3rd December", quote="3 December 2026, 5:00 PM"), "bad_value"),
        # The Received line is shown to Claude but is not part of the mail.
        (DatedQuote(value="2026-11-30T23:59", quote="Mon 30 Nov 2026"), "quote_not_in_mail"),
    ],
)
def test_a_wrong_deadline_is_dropped_not_guessed(deadline: DatedQuote, reason: str) -> None:
    result = judged("nimbus_drive", nimbus(deadline=deadline))
    assert result.deadline is None
    assert result.rejected == (f"deadline:{reason}",)
    assert result.form_link and result.event_date  # the rest of the card stands


def test_a_deadline_with_no_time_means_the_end_of_that_day() -> None:
    golden = BY_KEY["kaveri_internship"].golden
    assert golden.deadline is not None
    date_only = golden.model_copy(
        update={"deadline": DatedQuote(value="2026-12-15", quote="Apply by 15/12/2026")}
    )
    invented_time = golden.model_copy(
        update={"deadline": DatedQuote(value="2026-12-15T17:00", quote="Apply by 15/12/2026")}
    )
    assert judged("kaveri_internship", golden).deadline == datetime(
        2026, 12, 15, 23, 59, tzinfo=IST
    )
    assert judged("kaveri_internship", date_only).deadline == datetime(
        2026, 12, 15, 23, 59, tzinfo=IST
    )
    assert judged("kaveri_internship", invented_time).rejected == ("deadline:time_not_in_quote",)


def test_a_deadline_already_passed_is_dropped() -> None:
    answer = BY_KEY["past_deadline"].golden.model_copy(
        update={"deadline": DatedQuote(value="2026-11-30T23:59", quote="closed on 30 Nov 2026")}
    )
    result = judged("past_deadline", answer)
    assert result.deadline is None and result.rejected == ("deadline:before_mail",)
    assert result.keep  # still a card: the drive exists, its date is what was wrong


def test_relative_dates_are_read_from_when_the_mail_arrived() -> None:
    result = judged("tomorrow_deadline", BY_KEY["tomorrow_deadline"].golden)
    assert result.deadline == datetime(2026, 12, 2, 9, 0, tzinfo=IST)
    wrong_day = BY_KEY["tomorrow_deadline"].golden.model_copy(
        update={"deadline": DatedQuote(value="2026-12-03T09:00", quote="by tomorrow 9 AM")}
    )
    assert judged("tomorrow_deadline", wrong_day).rejected == ("deadline:date_not_in_quote",)


def test_an_event_may_have_no_time_but_never_an_invented_one() -> None:
    golden = BY_KEY["see_timetable"].golden
    result = judged("see_timetable", golden)
    assert result.event_date == datetime(2026, 12, 14, 0, 0, tzinfo=IST)
    assert not result.event_has_time
    invented = golden.model_copy(
        update={
            "event_date": DatedQuote(value="2026-12-14T09:00", quote="begin on 14 December 2026")
        }
    )
    assert judged("see_timetable", invented).rejected == ("event_date:time_not_in_quote",)


@pytest.mark.parametrize(
    ("link", "reason"),
    [
        ("http://exam.mockcollege.edu.in/hallticket", "not_https"),
        ("https://forms.gle/SomethingElse", "not_in_mail"),
        ("https://forms.gle@evil.example.net/x", "bad_link"),
        ("javascript:alert(1)", "not_https"),
        ("https://", "bad_link"),
    ],
)
def test_a_link_must_be_https_and_in_the_mail(link: str, reason: str) -> None:
    result = judged("nimbus_drive", nimbus(form_link=link))
    assert result.form_link is None
    assert result.rejected == (f"form_link:{reason}",)


def test_a_link_only_behind_a_button_counts_as_in_the_mail() -> None:
    result = judged("html_only_drive", BY_KEY["html_only_drive"].golden)
    assert result.form_link == "https://forms.gle/DeccanPool27"


def test_copied_words_may_differ_in_spacing_case_and_dashes() -> None:
    answer = BY_KEY["see_timetable"].golden.model_copy(
        update={"title": "see timetable - odd   SEMESTER 2026-27"}
    )
    assert judged("see_timetable", answer).title == "see timetable - odd SEMESTER 2026-27"


def test_an_invented_title_falls_back_to_the_subject() -> None:
    result = judged("forward_of_drive", BY_KEY["forward_of_drive"].golden.model_copy(
        update={"title": "Amazing Nimbus opportunity"}))  # fmt: skip
    assert result.title == "Nimbus Systems Campus Drive – 2027 Batch"  # "Fwd:" removed
    assert "title:not_in_mail" in result.rejected


def test_an_overlong_field_costs_that_field_only() -> None:
    result = judged("nimbus_drive", nimbus(details="Eligibility " * 40))
    assert result.details is None and result.rejected == ("details:too_long",)
    assert result.deadline is not None and result.form_link is not None


def test_other_is_never_a_card_whatever_else_it_carries() -> None:
    sneaky = BY_KEY["injection"].golden.model_copy(update={"title": "URGENT placement update"})
    assert not judged("injection", sneaky).keep
    assert not judged("webinar", OTHER).keep


def test_dates_too_far_ahead_are_refused() -> None:
    when = datetime(2026, 12, 1, 9, 0, tzinfo=IST)
    raw = build_raw(
        sender="TPO <tpo@mockcollege.edu.in>", subject="Drive", received_at=when,
        message_id="<x@y>", plain="Register by 3 December 2028.",
    )  # fmt: skip
    mail = FakeMailbox([FakeMail("0000000000000999", "t", when, raw)]).get("0000000000000999")
    assert mail is not None
    answer = proposal(
        "placement", "Drive", deadline=("2028-12-03T23:59", "Register by 3 December 2028")
    )
    assert check(answer, mail, render(mail).checkable).rejected == ("deadline:too_far",)


def test_only_a_specific_link_can_tie_mails_together() -> None:
    assert canonical_link("https://Forms.GLE/Abc/?utm_source=x&id=7#top") == (
        "https://forms.gle/Abc?id=7"
    )
    assert link_key("https://forms.gle/Abc/") == "https://forms.gle/Abc"
    assert link_key("https://exam.mockcollege.edu.in/") is None  # a portal's front page
    assert link_key("https://[broken") is None and link_key(None) is None


def test_titles_name_the_same_thing_by_their_words() -> None:
    assert same_title("Nimbus Systems Campus Drive", "Reminder: Nimbus Systems Campus Drive")
    assert not same_title("SEE Timetable – Odd Semester", "Revaluation applications – SEE")
    assert not same_title("", "Drive")
