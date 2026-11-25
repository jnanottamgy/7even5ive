from __future__ import annotations

from datetime import datetime, timedelta

import pytest

from mailfilter.config import Settings
from mailfilter.errors import NotConnected
from mailfilter.fake import STUDENT_ADDRESS, FakeMailbox
from mailfilter.run import check_mailbox
from mailfilter.samples import fake_mails, golden_judge
from mailfilter.store import CardDraft, Store
from mailfilter.timekit import IST
from mailfilter.tools import briefing_lines, due_soon, gmail_link, opportunities_answer
from tests.conftest import MONDAY, STUDENT, Clock


def at(day: int, hour: int, minute: int = 0) -> datetime:
    return datetime(2026, 11 if day >= 28 else 12, day, hour, minute, tzinfo=IST)


@pytest.fixture
def week(store: Store, settings: Settings, clock: Clock) -> Store:
    store.connect(STUDENT, STUDENT_ADDRESS, MONDAY)
    check_mailbox(store, FakeMailbox(fake_mails(), now=clock), golden_judge(), STUDENT, settings,
                  now=clock)  # fmt: skip
    return store


def titles(answer_data: list[object]) -> list[str]:
    return [card.title for card in answer_data]  # type: ignore[attr-defined]


def test_open_cards_soonest_first_and_past_ones_left_out(week: Store, settings: Settings) -> None:
    answer = opportunities_answer(week, STUDENT, at(4, 1), settings)
    names = titles(list(answer.data))
    assert len(names) == 15  # the Lumen talk and the preference form are over
    assert "Pre-placement talk: Lumen Fintech" not in names
    assert names[:3] == [
        "Deccan Robotics – Pool Campus Drive",
        "Nimbus Systems Campus Drive",
        "Revaluation applications – SEE June/July 2026",
    ]
    assert names[-4:] == [  # undated last, the most recent mail first
        "Supplementary SEE results announced",
        "Aster Bank drive: registrations closed",
        "Vertex Motors drive schedule",
        "SEE hall tickets available",
    ]
    assert (
        len(opportunities_answer(week, STUDENT, at(4, 1), settings, include_past=True).data) == 17
    )


def test_filters_by_kind_and_by_days(week: Store, settings: Settings) -> None:
    internships = opportunities_answer(week, STUDENT, at(4, 1), settings, kind="internship")
    assert {card.kind for card in internships.data} == {"internship"}
    assert len(internships.data) == 4
    soon = opportunities_answer(week, STUDENT, at(4, 1), settings, within_days=2)
    assert titles(list(soon.data)) == [
        "Deccan Robotics – Pool Campus Drive",
        "Nimbus Systems Campus Drive",
        "Revaluation applications – SEE June/July 2026",
    ]


def test_a_card_reads_in_india_time_with_a_plain_sentence(week: Store, settings: Settings) -> None:
    answer = opportunities_answer(week, STUDENT, at(4, 1), settings)
    nimbus = next(card for card in answer.data if card.title == "Nimbus Systems Campus Drive")
    assert nimbus.deadline == at(5, 23, 59) and nimbus.deadline.utcoffset() == timedelta(hours=5.5)
    assert nimbus.summary == (
        "Placement: Nimbus Systems Campus Drive. Last date Sat 5 Dec, 11:59 PM. "
        "Date Mon 7 Dec, 10 AM."
    )
    assert nimbus.gmail_link == (
        "https://mail.google.com/mail/?authuser=student@mockcollege.edu.in"
        "#search/rfc822msgid%3Animbus_reminder%40mockcollege.edu.in"
    )
    timetable = next(card for card in answer.data if card.kind == "exam_notice"
                     and card.title.startswith("SEE Timetable"))  # fmt: skip
    assert timetable.summary.endswith("No last date in the mail. Date Mon 14 Dec.")
    assert answer.connection == "connected" and answer.next_check_at == at(4, 13)


def test_stale_when_a_check_was_missed(week: Store, settings: Settings) -> None:
    assert not opportunities_answer(week, STUDENT, at(4, 16), settings).stale
    assert opportunities_answer(week, STUDENT, at(4, 19), settings).stale  # 18 h since


def test_not_connected_is_an_error_not_an_empty_list(store: Store, settings: Settings) -> None:
    with pytest.raises(NotConnected):
        opportunities_answer(store, "nobody", at(4, 1), settings)


def test_due_soon_is_what_the_urgent_call_is_for(week: Store) -> None:
    due = due_soon(week, STUDENT, at(4, 1), timedelta(hours=24))
    assert [row.title for row in due] == ["Deccan Robotics – Pool Campus Drive"]


def test_the_briefing_says_what_is_new_and_what_closes_soon(
    store: Store, settings: Settings, clock: Clock
) -> None:
    store.connect(STUDENT, STUDENT_ADDRESS, MONDAY)
    mailbox = FakeMailbox(fake_mails(), now=clock)
    for moment in (at(30, 13), at(30, 21), at(1, 13), at(1, 21), at(2, 13), at(2, 21)):
        clock.set(moment)
        check_mailbox(store, mailbox, golden_judge(), STUDENT, settings, now=clock)
    lines = briefing_lines(store, STUDENT, at(3, 7), settings)
    new = [line for line in lines if line.startswith("New from college mail:")]
    soon = [line for line in lines if line.startswith("Closing soon:")]
    assert soon == [
        "Closing soon: Placement: Deccan Robotics – Pool Campus Drive. Last date Fri 4 Dec, 11 AM."
    ]
    assert any("Helix Cloud Off-Campus Drive" in line for line in new)  # found Wednesday
    assert not any("Kaveri" in line for line in new)  # found Monday: not new any more
    assert not any("last checked" in line for line in lines)


def test_the_briefing_tells_the_student_when_mail_needs_them(
    store: Store, settings: Settings
) -> None:
    store.connect(STUDENT, STUDENT_ADDRESS, MONDAY)
    assert briefing_lines(store, STUDENT, at(1, 7), settings) == [
        "College mail was last checked: not yet."
    ]
    store.mark(STUDENT, "needs_reconnect", "invalid_grant")
    assert briefing_lines(store, STUDENT, at(1, 7), settings)[0].startswith(
        "Your college mail needs reconnecting"
    )
    store.mark(STUDENT, "college_blocked", "domain_policy")
    assert "Google settings stop 7even5ive" in briefing_lines(store, STUDENT, at(1, 7), settings)[0]
    assert briefing_lines(store, "nobody", at(1, 7), settings) == []


def test_many_new_cards_are_capped_at_five_lines(week: Store, settings: Settings) -> None:
    lines = briefing_lines(week, STUDENT, at(4, 7), settings)
    assert sum(line.startswith("New from college mail:") for line in lines) == 5
    assert "And 10 more new from college mail in the app." in lines


def test_gmail_link_without_an_address_or_message_id() -> None:
    assert gmail_link(None, None, "18c0abc") == "https://mail.google.com/mail/u/0/#all/18c0abc"


def test_an_older_authoritative_mail_only_fills_gaps(store: Store) -> None:
    def draft(when: datetime, deadline: datetime | None, role: str | None) -> CardDraft:
        return CardDraft(
            kind="placement", title="Drive", organisation="Org", role=role, deadline=deadline,
            event_date=None, event_has_time=False, form_link="https://forms.gle/x",
            link_key="https://forms.gle/x", details=None, received_at=when, news_at=when,
            forwarded=False, message_id=f"m{when:%d%H}", rfc822_id=None, thread_id="t",
        )  # fmt: skip

    now = at(3, 9)
    store.connect(STUDENT, STUDENT_ADDRESS, MONDAY)
    store.record_mail(
        STUDENT, "m0221", at(2, 21), "carded", None, now, draft(at(2, 21), at(9, 17), None)
    )
    store.record_mail(
        STUDENT, "m0109", at(1, 9), "carded", None, now, draft(at(1, 9), at(5, 17), "SDE")
    )
    [card] = store.cards(STUDENT)
    assert card.deadline == at(9, 17)  # the newer mail's date stands
    assert card.role == "SDE"  # the older mail filled what was missing
    assert card.first_received_at == at(1, 9) and card.last_received_at == at(2, 21)
    assert card.message_id == "m0221" and card.mails == 2
