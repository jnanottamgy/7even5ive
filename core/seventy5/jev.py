"""Jev: TypeSafe's decision model, via OpenRouter. It ticks boxes and nothing more.

Why: Jev bills input only (~$0.00003 a call) and returns a pick with a confidence, so it
can answer "what is this, which subject, is it spam" without paying an LLM to write.
Not: Jev reading dates or titles -- it cannot write text, so anything dated goes on to
the LLM. Not: rules, regex or fuzzy matching in front of it (decided: they misread intent).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Mapping, Protocol

import httpx

from .config import settings

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class Choice:
    instructions: str
    options: dict[str, str]  # option -> what it means


@dataclass(frozen=True)
class YesNo:
    instructions: str


Question = Choice | YesNo


@dataclass(frozen=True)
class Picked:
    option: str
    confidence: float


@dataclass(frozen=True)
class Likely:
    yes: float


@dataclass
class Decisions:
    """Only answers that came back usable. A missing key means "unsure" to every caller."""

    answers: dict[str, Picked | Likely] = field(default_factory=dict)
    input_tokens: int = 0


class JevError(RuntimeError):
    """Any failure. The caller hands the item to the LLM instead -- Jev never blocks."""


class Decider(Protocol):
    def decide(self, state: dict[str, Any], questions: dict[str, Question]) -> Decisions: ...


def _wire(q: Question) -> dict[str, Any]:
    if isinstance(q, Choice):
        return {"type": "choice", "instructions": q.instructions, "criteria": q.options}
    return {"type": "noul", "instructions": q.instructions}


def _prob(value: object) -> float | None:
    if isinstance(value, bool) or not isinstance(value, int | float):
        return None
    return float(value) if 0.0 <= value <= 1.0 else None


def _parse(q: Question, raw: object) -> Picked | Likely | None:
    if not isinstance(raw, Mapping):
        return None
    if isinstance(q, Choice):
        option = raw.get("choice")
        if option not in q.options:
            return None
        conf = _prob(raw.get("confidence"))
        if conf is None and isinstance(raw.get("probabilities"), Mapping):
            conf = _prob(raw["probabilities"].get(option))
        return Picked(str(option), conf or 0.0)
    yes = _prob(raw.get("noul"))
    return Likely(yes) if yes is not None else None


class JevDecider:
    def __init__(self, client: httpx.Client | None = None) -> None:
        self._client = client or httpx.Client(timeout=settings.jev_timeout_seconds)

    def decide(self, state: dict[str, Any], questions: dict[str, Question]) -> Decisions:
        payload = {
            "model": settings.jev_model,
            "state": state,
            "questions": {k: _wire(q) for k, q in questions.items()},
        }
        try:
            resp = self._client.post(
                settings.jev_url, json=payload,
                headers={"Authorization": f"Bearer {settings.jev_api_key}"},
            )
            resp.raise_for_status()
            body = resp.json()
        except (httpx.HTTPError, ValueError) as err:
            # Logs carry the model only: the state is the student's words.
            log.warning("jev call failed", extra={"model": settings.jev_model})
            raise JevError(str(type(err).__name__)) from err
        raw = body.get("answers") if isinstance(body, Mapping) else None
        if not isinstance(raw, Mapping):
            raise JevError("no answers")
        answers = {k: a for k, q in questions.items() if (a := _parse(q, raw.get(k)))}
        usage = body.get("usage") or {}
        return Decisions(answers, int(usage.get("input_tokens") or 0))


class UnsureDecider:
    """Stand-in with no key: always unsure, so every item goes to the LLM. Safe by design."""

    def decide(self, state: dict[str, Any], questions: dict[str, Question]) -> Decisions:
        return Decisions()


class ScriptedDecider:
    """Test double: returns the queued answers in order (then the last one again)."""

    def __init__(self, *replies: dict[str, Picked | Likely] | Exception) -> None:
        self.replies = list(replies)
        self.calls: list[dict[str, Any]] = []

    def decide(self, state: dict[str, Any], questions: dict[str, Question]) -> Decisions:
        self.calls.append({"state": state, "questions": list(questions)})
        reply = self.replies.pop(0) if len(self.replies) > 1 else self.replies[0]
        if isinstance(reply, Exception):
            raise reply
        return Decisions({k: v for k, v in reply.items() if k in questions})


def get_decider() -> Decider:
    return JevDecider() if settings.jev_api_key else UnsureDecider()
