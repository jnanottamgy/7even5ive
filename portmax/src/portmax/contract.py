"""The five tools and the shapes every college's data must fit.

These models are the boundary: whatever architecture serves the tools only ever sees these shapes,
never a portal's HTML. Validators reject data that cannot be true (more classes attended than
held), so a page that parses into nonsense surfaces as `PortalChanged` instead of a wrong number a
student would act on.
"""

from __future__ import annotations

from datetime import UTC, date, datetime, time
from enum import StrEnum
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

# A rounded percentage on the portal (73% for 22 of 30 = 73.33) must still pass, and some portals
# truncate rather than round, so one percentage point of slack.
PERCENT_TOLERANCE = 1.0

ToolName = Literal["get_attendance", "get_timetable", "get_marks", "get_results", "get_profile"]
TOOLS: tuple[ToolName, ...] = (
    "get_attendance",
    "get_timetable",
    "get_marks",
    "get_results",
    "get_profile",
)

# Tools computed from saved portal answers rather than read from the portal. The five portal
# tools above stay the whole contract with portals; a derived tool never adds a page to fetch.
DerivedToolName = Literal["get_attendance_plan"]
DERIVED_TOOLS: tuple[DerivedToolName, ...] = ("get_attendance_plan",)
AnyToolName = ToolName | DerivedToolName
ALL_TOOLS: tuple[AnyToolName, ...] = (*TOOLS, *DERIVED_TOOLS)

SubjectCode = Annotated[str, Field(min_length=2, max_length=20, pattern=r"^[A-Z0-9][A-Z0-9 _-]*$")]


class Model(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class AttendanceRow(Model):
    subject_code: SubjectCode
    subject_name: str = Field(min_length=1, max_length=120)
    attended: int = Field(ge=0)
    held: int = Field(ge=0)
    percent: float = Field(ge=0, le=100)
    planned: int | None = Field(default=None, ge=0, description="Classes planned this semester")
    as_of: date | None = Field(default=None, description="The portal's own last-updated date")

    @model_validator(mode="after")
    def _consistent(self) -> AttendanceRow:
        if self.attended > self.held:
            raise ValueError(f"{self.subject_code}: attended {self.attended} > held {self.held}")
        if self.planned is not None and self.held > self.planned:
            raise ValueError(f"{self.subject_code}: held {self.held} > planned {self.planned}")
        if self.held:
            computed = self.attended / self.held * 100
            if abs(computed - self.percent) > PERCENT_TOLERANCE:
                raise ValueError(
                    f"{self.subject_code}: portal says {self.percent}% "
                    f"but {self.attended}/{self.held} is {computed:.1f}%"
                )
        return self


class Weekday(StrEnum):
    MON = "Mon"
    TUE = "Tue"
    WED = "Wed"
    THU = "Thu"
    FRI = "Fri"
    SAT = "Sat"
    SUN = "Sun"


class TimetableSlot(Model):
    day: Weekday
    start: time
    end: time
    subject_code: SubjectCode
    room: str | None = Field(default=None, max_length=40)

    @model_validator(mode="after")
    def _ordered(self) -> TimetableSlot:
        if self.start >= self.end:
            raise ValueError(
                f"{self.day} {self.subject_code}: starts {self.start} >= ends {self.end}"
            )
        return self


class MarkRow(Model):
    subject_code: SubjectCode
    component: str = Field(min_length=1, max_length=40, description="CIE-1, CIE-2, Quiz, Lab ...")
    scored: float = Field(ge=0)
    maximum: float = Field(gt=0)

    @model_validator(mode="after")
    def _within_maximum(self) -> MarkRow:
        if self.scored > self.maximum:
            raise ValueError(
                f"{self.subject_code} {self.component}: {self.scored} > {self.maximum}"
            )
        return self


class ResultRow(Model):
    semester: int = Field(ge=1, le=12)
    subject_code: SubjectCode
    credits: float = Field(ge=0, le=30)
    grade: str = Field(min_length=1, max_length=3)
    grade_points: float | None = Field(default=None, ge=0, le=10)


class SemesterSummary(Model):
    semester: int = Field(ge=1, le=12)
    sgpa: float | None = Field(default=None, ge=0, le=10)
    cgpa: float | None = Field(default=None, ge=0, le=10)


class Results(Model):
    subjects: list[ResultRow]
    semesters: list[SemesterSummary]


class Profile(Model):
    """Only what matching needs. No name, date of birth, phone or photo, ever."""

    usn: str = Field(min_length=5, max_length=16, pattern=r"^[0-9A-Z]+$")
    branch: str = Field(min_length=2, max_length=60)
    semester: int = Field(ge=1, le=12)
    section: str | None = Field(default=None, max_length=8)


class Answer(Model):
    """What every tool returns: the data plus where and when it came from."""

    college: str
    connector_version: str
    fetched_at: datetime
    stale: bool = Field(description="True when the last refresh is older than the freshness window")


class AttendanceAnswer(Answer):
    tool: Literal["get_attendance"] = "get_attendance"
    data: list[AttendanceRow]


class TimetableAnswer(Answer):
    tool: Literal["get_timetable"] = "get_timetable"
    data: list[TimetableSlot]


class MarksAnswer(Answer):
    tool: Literal["get_marks"] = "get_marks"
    data: list[MarkRow]


class ResultsAnswer(Answer):
    tool: Literal["get_results"] = "get_results"
    data: Results


class ProfileAnswer(Answer):
    tool: Literal["get_profile"] = "get_profile"
    data: Profile


ToolAnswer = AttendanceAnswer | TimetableAnswer | MarksAnswer | ResultsAnswer | ProfileAnswer

ANSWER_MODELS: dict[ToolName, type[Answer]] = {
    "get_attendance": AttendanceAnswer,
    "get_timetable": TimetableAnswer,
    "get_marks": MarksAnswer,
    "get_results": ResultsAnswer,
    "get_profile": ProfileAnswer,
}

TOOL_DESCRIPTIONS: dict[AnyToolName, str] = {
    "get_attendance": (
        "The student's attendance per subject from their college portal: classes attended, "
        "classes held, the percentage, and classes planned for the semester where the portal "
        "shows it. Includes when it was last refreshed."
    ),
    "get_timetable": "The student's weekly class timetable: day, start, end, subject and room.",
    "get_marks": "Internal marks per subject and component (CIE-1, CIE-2, quizzes, lab).",
    "get_results": "Semester results: grades and credits per subject, with SGPA and CGPA.",
    "get_profile": "USN, branch, semester and section. Never the student's name or birth date.",
    "get_attendance_plan": (
        "Bunk math for every subject, worst first: how many classes the student can miss and "
        "stay at the college's minimum (75% unless the college says otherwise), or how many they "
        "must attend in a row to get back, with the dates of their next classes and the outlook "
        "for the rest of the semester. Each subject comes with a ready sentence for the student."
    ),
}


def utc_now() -> datetime:
    return datetime.now(UTC)
