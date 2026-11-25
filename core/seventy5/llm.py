"""The LLM step: reads the date and title, or decides everything when Jev was unsure.

Why: Claude Haiku 5.5 with one forced tool call, so the answer is always the same JSON
shape, and the subject is an enum of the student's real subjects -- it cannot invent one.
The system prompt is static and marked for caching, so repeat calls pay ~10% for it.
Not: free-text parsing of the reply. Not: letting the model write to the database --
it only proposes; cascade.gate() checks every value first.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Protocol

from .config import settings

log = logging.getLogger(__name__)

KINDS = ("deadline", "exam", "material", "event", "notice", "chitchat")

SYSTEM = """You file messages for an Indian college student.
You get one message (from a WhatsApp class group, college email or Google Classroom),
the student's subject list, today's date in IST, and sometimes hints that a cheaper
model already decided (kind and subject). Trust the hints unless the message clearly
contradicts them.

Return exactly one call to `file_item`:
- kind: deadline (something to submit), exam (a test or CIE), material (notes, slides,
  manuals, papers), event (a fest, workshop, talk, internship drive), notice (anything
  else official), chitchat (memes, thanks, "ok", stickers -- nothing to file).
- subject: one of the listed subjects, or "Miscellaneous" when none fits.
- title: short, in the message's own words. Never invent details.
- due_at: ISO 8601 with +05:30 for deadlines, exams and events. Resolve "Fri", "tomorrow",
  "next Monday" against today. If no time is given, use 23:59 for deadlines and 09:00
  otherwise. null when the message gives no date at all.
- spam: true for paid "internships", pay-to-join training, or mail pretending to be the
  college placement cell. Real internships, events and college notices are not spam.
"""


@dataclass(frozen=True)
class Proposal:
    kind: str
    subject: str
    title: str
    due_at: str | None
    spam: bool = False


class LLMError(RuntimeError):
    pass


class LLM(Protocol):
    def propose(self, text: str, subjects: list[str], today: str,
                hints: dict[str, str]) -> Proposal: ...


def _tool(subjects: list[str]) -> dict[str, Any]:
    return {
        "name": "file_item",
        "description": "File one message as a card for the student.",
        "input_schema": {
            "type": "object",
            "properties": {
                "kind": {"type": "string", "enum": list(KINDS)},
                "subject": {"type": "string", "enum": [*subjects, "Miscellaneous"]},
                "title": {"type": "string"},
                "due_at": {"type": ["string", "null"]},
                "spam": {"type": "boolean"},
            },
            "required": ["kind", "subject", "title", "due_at", "spam"],
        },
    }


class ClaudeLLM:
    def __init__(self) -> None:
        import anthropic  # lazy: the offline demo never needs it

        # Why Bedrock first: the team has AWS credits and no Anthropic key, and it keeps
        # the model inside the AWS account the rest of 75 runs in.
        if settings.bedrock_model_id:
            self._client = anthropic.AnthropicBedrock(aws_region=settings.aws_region)
            self._model = settings.bedrock_model_id
        else:
            self._client = anthropic.Anthropic(api_key=settings.anthropic_api_key)
            self._model = settings.llm_model

    def propose(self, text: str, subjects: list[str], today: str,
                hints: dict[str, str]) -> Proposal:
        hint_line = ", ".join(f"{k}={v}" for k, v in hints.items()) or "none"
        user = (f"Today: {today}\nSubjects: {', '.join(subjects)}\nHints: {hint_line}\n\n"
                f"Message:\n{text}")
        try:
            msg = self._client.messages.create(
                model=self._model,
                max_tokens=300,
                system=[{"type": "text", "text": SYSTEM, "cache_control": {"type": "ephemeral"}}],
                tools=[_tool(subjects)],
                tool_choice={"type": "tool", "name": "file_item"},
                messages=[{"role": "user", "content": user}],
            )
        except Exception as err:  # the SDK's errors all derive from APIError; keep it broad
            log.warning("llm call failed", extra={"model": settings.llm_model})
            raise LLMError(type(err).__name__) from err
        for block in msg.content:
            if getattr(block, "type", "") == "tool_use":
                data = dict(block.input)
                return Proposal(
                    kind=str(data.get("kind", "")), subject=str(data.get("subject", "")),
                    title=str(data.get("title", "")).strip(), due_at=data.get("due_at"),
                    spam=bool(data.get("spam", False)),
                )
        raise LLMError("no tool call")


class NoKeyLLM:
    """Stand-in with no API key: refuses, so the item becomes a 'needs review' card."""

    def propose(self, text: str, subjects: list[str], today: str,
                hints: dict[str, str]) -> Proposal:
        raise LLMError("no LLM key configured")


class ScriptedLLM:
    """Test and demo double: answers from a dict keyed by the exact message text."""

    def __init__(self, answers: dict[str, Proposal]) -> None:
        self.answers = answers
        self.calls: list[dict[str, Any]] = []

    def propose(self, text: str, subjects: list[str], today: str,
                hints: dict[str, str]) -> Proposal:
        self.calls.append({"text": text, "hints": hints})
        if text not in self.answers:
            raise LLMError("unscripted")
        return self.answers[text]


def get_llm() -> LLM:
    return ClaudeLLM() if settings.bedrock_model_id or settings.anthropic_api_key else NoKeyLLM()
