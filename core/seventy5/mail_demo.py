"""The demo's college mailbox: invented mail from today, and what a correct judge says about it.

Why not the mail filter's own thirty samples: their dates are fixed in late 2026, so a demo a
week later would show nothing but past deadlines. These mails are written at startup with dates
relative to the present, and each answer quotes the mail's own words, so the mail filter's code
checks (the quote is in the mail, the date is the one the quote names, the link is in the mail)
pass exactly as they would on real mail.

Batch one arrived earlier today: a placement drive, an internship, an exam notice and two mails
that are rightly left out. Batch two arrives when the student first taps "Check now", so the
demo shows a check finding something new.
Every name, company and link is invented (example domains, a mock college).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta

from mailfilter.contract import OTHER, DatedQuote, Proposal
from mailfilter.fake import FakeMail, build_raw

from . import clock

TPO = "Training & Placement Office <placements@mockcollege.edu.in>"
COE = "Controller of Examinations <coe@mockcollege.edu.in>"
NIMBUS_LINK = "https://forms.gle/NimbusDrive2027"
ORBITLY_LINK = "https://careers.orbitly.example.com/intern-2027"
ZENTRY_LINK = "https://forms.gle/ZentryLabsIntern"


@dataclass(frozen=True)
class DemoMail:
    mail: FakeMail
    sender: str
    subject: str
    answer: Proposal

    @property
    def marker(self) -> str:
        """The lines that identify this mail in what the judge is shown (as the samples do)."""
        return f"\nFrom: {self.sender}\nSubject: {self.subject}\n"


def _long(day: date) -> str:
    return f"{day.day} {day:%B} {day.year}"


def _weekday(day: date) -> str:
    return f"{day:%A}, {_long(day)}"


def _mail(number: int, received: datetime, sender: str, subject: str, plain: str,
          answer: Proposal) -> DemoMail:
    raw = build_raw(sender=sender, subject=subject, received_at=received,
                    message_id=f"<demo-{number}-{received:%Y%m%d}@mockcollege.edu.in>",
                    plain=plain, html=None, charset="utf-8", headers=[], attachments=[])
    message_id = f"d{received:%Y%m%d}{number:04d}"
    return DemoMail(FakeMail(message_id, f"t{message_id}", received, raw, frozenset({"INBOX"})),
                    sender, subject, answer)


def _received(now: datetime, minutes_ago: int) -> datetime:
    """Earlier today, never before midnight: a newly connected mailbox is read from midnight."""
    local = now.astimezone(clock.IST)
    midnight = local.replace(hour=0, minute=0, second=0, microsecond=0)
    return max(local - timedelta(minutes=minutes_ago), midnight + timedelta(minutes=1))


def first_batch(now: datetime) -> list[DemoMail]:
    today = now.astimezone(clock.IST).date()
    register, test = today + timedelta(days=3), today + timedelta(days=5)
    apply_by, exams = today + timedelta(days=6), today + timedelta(days=9)
    nimbus = _mail(
        1, _received(now, 200), TPO, "Nimbus Systems Campus Drive – 2027 Batch",
        "Dear Students,\n\nNimbus Systems is visiting our campus for the 2027 batch.\n\n"
        "Role: Graduate Engineer Trainee\nCTC: 8 LPA\n"
        "Eligibility: CGPA 7.0 and above, no active backlogs.\n\n"
        f"Register here: {NIMBUS_LINK} on or before {_weekday(register)}, 5:00 PM.\n"
        f"Online test on {_long(test)} at 10:00 AM.\n\nRegards,\nTraining & Placement Office",
        Proposal(kind="placement", title="Nimbus Systems Campus Drive",
                 organisation="Nimbus Systems", role="Graduate Engineer Trainee",
                 deadline=DatedQuote(value=f"{register.isoformat()}T17:00",
                                     quote=f"on or before {_weekday(register)}, 5:00 PM"),
                 event_date=DatedQuote(value=f"{test.isoformat()}T10:00",
                                       quote=f"Online test on {_long(test)} at 10:00 AM"),
                 form_link=NIMBUS_LINK,
                 details="Eligibility: CGPA 7.0 and above, no active backlogs."))
    orbitly = _mail(
        2, _received(now, 150), "Orbitly Careers <campus@orbitly.example.com>",
        "Backend Engineering Internship 2027 – Orbitly",
        "Orbitly is hiring interns for summer 2027.\n\nPosition: Backend Engineering Intern\n"
        "Stipend: Rs 30,000 per month for 10 weeks\n"
        f"Apply by {apply_by:%d/%m/%Y} at {ORBITLY_LINK}",
        Proposal(kind="internship", title="Backend Engineering Internship 2027",
                 organisation="Orbitly", role="Backend Engineering Intern",
                 deadline=DatedQuote(value=f"{apply_by.isoformat()}T23:59",
                                     quote=f"Apply by {apply_by:%d/%m/%Y}"),
                 event_date=None, form_link=ORBITLY_LINK,
                 details="Stipend: Rs 30,000 per month for 10 weeks"))
    cie = _mail(
        3, _received(now, 120), COE, "CIE-3 Schedule – 5th Semester",
        "Dear Students,\n\nThe third Continuous Internal Evaluation (CIE-3) for the 5th semester "
        f"will begin on {_long(exams)}. Subject-wise slots will be shared by your departments.",
        Proposal(kind="exam_notice", title="CIE-3 Schedule – 5th Semester",
                 organisation="Controller of Examinations", role=None, deadline=None,
                 event_date=DatedQuote(value=exams.isoformat(),
                                       quote=f"will begin on {_long(exams)}"),
                 form_link=None, details=None))
    webinar = _mail(
        4, _received(now, 90), "CareerBoost <news@careerboost.example.com>",
        "Free webinar: Crack product interviews in 30 days",
        "Join our free webinar this Saturday at 7 PM. Save your seat: "
        "https://careerboost.example.com/webinar", OTHER)
    newsletter = _mail(
        5, _received(now, 60), "Campus Chronicle <chronicle@mockcollege.edu.in>",
        "The Campus Chronicle – this month",
        "This month: the robotics team's win, a new canteen menu and alumni stories.", OTHER)
    return [nimbus, orbitly, cie, webinar, newsletter]


def second_batch(now: datetime) -> list[DemoMail]:
    today = now.astimezone(clock.IST).date()
    closes = today + timedelta(days=2)
    received = now.astimezone(clock.IST) - timedelta(seconds=30)
    return [_mail(
        6, received, TPO, "Zentry Labs – Hackathon Internship Track",
        "Dear Students,\n\nZentry Labs offers a paid internship track for its winter hackathon.\n"
        "Role: Software Engineering Intern\n"
        f"Register at {ZENTRY_LINK} on or before {_weekday(closes)}, 6:00 PM.",
        Proposal(kind="internship", title="Zentry Labs – Hackathon Internship Track",
                 organisation="Zentry Labs", role="Software Engineering Intern",
                 deadline=DatedQuote(value=f"{closes.isoformat()}T18:00",
                                     quote=f"on or before {_weekday(closes)}, 6:00 PM"),
                 event_date=None, form_link=ZENTRY_LINK, details=None))]
