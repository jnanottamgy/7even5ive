"""The cascade: the bot's decision -> Classroom's own date -> Jev -> LLM.

Why the bot first: a WhatsApp message the bot already filed (kind, subject, date) needs
no second classification; code checks the bot's answer and files it. Mail, Classroom and
anything the bot was unsure of go on through Jev and the LLM.
Every item is filed or goes to the LLM.

Why this order: the Classroom API already knows a due date (free and exact); Jev is next
because it costs ~nothing and answers "what is it / which subject / is it spam"; the LLM
runs last, only to read a date and title or when Jev is unsure.
Not: a third outcome such as "drop when unsure". Dropping (chit-chat, spam) needs Jev at
0.9; anything less confident goes to the LLM, because losing a real deadline is worse
than paying for one call.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from . import clock
from .config import settings
from .db import Database
from .jev import Choice, Decider, JevError, Likely, Picked, YesNo
from .llm import KINDS, LLM, LLMError, Proposal

log = logging.getLogger(__name__)

DATED = {"deadline", "exam", "event"}
KIND_HELP = {
    "deadline": "something the student must submit by a date",
    "exam": "a test, quiz or CIE",
    "material": "notes, slides, a lab manual, a question paper",
    "event": "a fest, workshop, talk or internship drive",
    "notice": "any other official announcement",
    "chitchat": "memes, thanks, 'ok', stickers: nothing to keep",
}


@dataclass
class Outcome:
    route: str  # bot | classroom | jev | jev+llm | llm | review
    status: str  # filed | filtered | skipped | needs_review
    item_id: int | None = None
    jev_tokens: int = 0


def _questions(subjects: list[str], source: str, student: Any) -> dict[str, Any]:
    q: dict[str, Any] = {
        "kind": Choice("What is this message?", KIND_HELP),
        "subject": Choice(
            "Which of the student's subjects is it about?",
            {**{s: s for s in subjects}, "Miscellaneous": "none of the subjects"},
        ),
    }
    if source == "gmail":
        q["spam"] = YesNo("Is this spam: a paid internship or training, a pay-to-join offer, "
                          "or mail pretending to be the college placement cell?")
        q["relevant"] = YesNo(
            f"Would a {student['branch']} student in year {student['year']} interested in "
            f"{student['interests']} want to see this?"
        )
    return q


def _confident(answer: Any, at: float) -> str | None:
    return answer.option if isinstance(answer, Picked) and answer.confidence >= at else None


def _yes(answer: Any) -> float | None:
    return answer.yes if isinstance(answer, Likely) else None


def _display_title(payload: dict[str, Any]) -> str:
    # Display only, not classification: a filed material shows its file name, else the
    # message's first line. Jev decided what it is; this just labels the card.
    if payload.get("attachment"):
        return str(payload["attachment"])
    return str(payload.get("text", "")).strip().splitlines()[0][:90] if payload.get("text") else ""


def _parse_due(value: str | None) -> str | None:
    if not value:
        return None
    try:
        at = datetime.fromisoformat(value)
    except ValueError:
        return None
    if at.tzinfo is None:
        at = at.replace(tzinfo=clock.IST)
    return clock.iso(at)


def gate(p: Proposal, subjects: list[str]) -> str | None:
    """Every LLM value checked before a write. Returns the reason it failed, or None."""
    if p.kind not in KINDS:
        return "unknown kind"
    if p.subject not in (*subjects, "Miscellaneous"):
        return "subject not in the student's list"
    if p.kind != "chitchat" and not p.title:
        return "no title"
    if p.kind in DATED and _parse_due(p.due_at) is None:
        return "dated item without a readable date"
    return None


class Cascade:
    def __init__(self, db: Database, jev: Decider, llm: LLM) -> None:
        self.db, self.jev, self.llm = db, jev, llm

    def run(self, event_id: int) -> Outcome:
        ev = self.db.event(event_id)
        payload: dict[str, Any] = json.loads(ev["payload"])
        student = self.db.student(ev["student_id"])
        from .tools import subjects as subjects_of

        subjects = subjects_of(self.db, student["id"])
        source = ev["source"]
        base = {"student_id": student["id"], "event_id": event_id, "source": source,
                "created_at": clock.iso(clock.now())}

        # -1. A deadline the bot saved, changed or deleted: applied as it is, no model.
        if str(payload.get("type", "")).startswith("deadline."):
            from . import sync

            return sync.apply(self.db, student["id"], event_id, payload)

        # 0. The bot already decided: it filed this message itself. Check its answer in code
        # (no model call) and file it as it is; only a failed check falls through to Jev.
        if (bot := self._from_bot(payload, subjects)) is not None:
            if bot.kind == "chitchat":
                return Outcome("bot", "skipped")
            item = self.db.insert_item(**base, kind=bot.kind, subject=bot.subject,
                                       title=bot.title, due_at=_parse_due(bot.due_at),
                                       route="bot", relevance=None)
            return Outcome("bot", "filed", item)

        state = {"source": source, "text": payload.get("text", ""),
                 "attachment": payload.get("attachment")}
        try:
            d = self.jev.decide(state, _questions(subjects, source, student))
            answers, tokens = d.answers, d.input_tokens
        except JevError:
            answers, tokens = {}, 0

        file_at, drop_at = settings.jev_file_confidence, settings.jev_drop_confidence
        kind = _confident(answers.get("kind"), file_at)
        subject = _confident(answers.get("subject"), file_at)
        relevance = _yes(answers.get("relevant"))

        # 1. Classroom: the API's own due date wins; Jev only names the subject.
        cr = payload.get("classroom")
        if cr and cr.get("due_at") and subject:
            item = self.db.insert_item(**base, kind="deadline", subject=subject,
                                       title=cr["title"], due_at=_parse_due(cr["due_at"]),
                                       route="classroom", relevance=relevance)
            return Outcome("classroom", "filed", item, tokens)

        # 2. Jev drops only with high confidence.
        spam = _yes(answers.get("spam"))
        if spam is not None and spam >= drop_at:
            item = self.db.insert_item(**base, kind="notice", subject="Miscellaneous",
                                       title=_display_title(payload), due_at=None,
                                       status="filtered", route="jev", relevance=relevance)
            return Outcome("jev", "filtered", item, tokens)
        if _confident(answers.get("kind"), drop_at) == "chitchat":
            return Outcome("jev", "skipped", None, tokens)

        # 3. Jev files undated items alone.
        if kind in {"material", "notice"} and subject and _display_title(payload):
            item = self.db.insert_item(**base, kind=kind, subject=subject,
                                       title=_display_title(payload), due_at=None,
                                       route="jev", relevance=relevance)
            return Outcome("jev", "filed", item, tokens)

        # 4. The LLM: with Jev's hints when it was sure, from scratch when it was not.
        hints = {k: v for k, v in (("kind", kind), ("subject", subject)) if v and kind != "chitchat"}
        route = "jev+llm" if hints else "llm"
        try:
            p = self.llm.propose(payload.get("text", "") or _display_title(payload), subjects,
                                 clock.now().strftime("%A %d %B %Y"), hints)
        except LLMError as err:
            return self._review(base, payload, f"llm: {err}", tokens)

        if (reason := gate(p, subjects)) is not None:
            return self._review(base, payload, reason, tokens)
        if p.kind == "chitchat":
            return Outcome(route, "skipped", None, tokens)
        status = "filtered" if p.spam else "filed"
        item = self.db.insert_item(**base, kind=p.kind, subject=p.subject, title=p.title,
                                   due_at=_parse_due(p.due_at), status=status, route=route,
                                   relevance=relevance)
        return Outcome(route, status, item, tokens)

    @staticmethod
    def _from_bot(payload: dict[str, Any], subjects: list[str]) -> Proposal | None:
        d = payload.get("decision")
        if not isinstance(d, dict):
            return None
        p = Proposal(kind=str(d.get("kind", "")), subject=str(d.get("subject", "")),
                     title=str(d.get("title") or _display_title(payload)).strip(),
                     due_at=d.get("due_at"))
        if (reason := gate(p, subjects)) is not None:
            # Usually the two systems' subject lists drifting apart; our cascade decides.
            log.info("bot decision refused", extra={"reason": reason})
            return None
        return p

    def _review(self, base: dict[str, Any], payload: dict[str, Any], reason: str,
                tokens: int) -> Outcome:
        # Never silent: an item nobody could read becomes a card the student can fix.
        log.info("needs review", extra={"reason": reason})
        item = self.db.insert_item(**base, kind="notice", subject="Miscellaneous",
                                   title=_display_title(payload) or "Unreadable message",
                                   due_at=None, status="needs_review", route="review",
                                   relevance=None)
        return Outcome("review", "needs_review", item, tokens)
