"""Ask your semester: a question in plain words, answered from the student's own data.

Every fact comes from a gateway tool call -- the same tools, policy and audit an MCP client
(Claude, ChatGPT) gets -- so the in-app box is a live demo of the MCP path, not a side door.

Two modes, and the answer says which one ran (route):
- "claude": with BEDROCK_MODEL_ID or ANTHROPIC_API_KEY set, Claude plans the calls itself
  (up to MAX_TURNS tool rounds). Writes behave as for any MCP client: add_to_calendar comes
  back approval_needed and appears on the phone for a tap.
- "offline": no key. A small keyword router picks the tool and words the answer from its
  result. Honest about its limits: it names what it can answer instead of guessing.
Not: logging the question. Questions are the student's words; only tool names reach the audit.
"""

from __future__ import annotations

import json
import logging
import re
import time
from datetime import datetime, timedelta
from typing import Any

from . import clock
from .config import settings
from .gateway import Denied, Gateway

log = logging.getLogger(__name__)

MAX_TURNS = 5

SYSTEM = """You are 7even5ive, a college student's semester assistant inside their phone app.
Answer only from what the tools return; never invent dates, marks or rules. If the tools do
not have it, say so. Be brief: two or three short sentences or a short list, plain text, no
markdown headings. Use the student's subject names. Times are IST.
For attendance questions, the attendance tool's per-subject message is exact bunk math: quote
it rather than redoing it. To act on an item (a reminder, a calendar entry) use its id from
due_this_week. add_to_calendar needs the student's tap: say it is waiting on their phone."""

# Tools Claude may call: the gateway's own allow/ask list, described for the model.
TOOLS: list[dict[str, Any]] = [
    {"name": "due_this_week", "description": "Deadlines, exams and events due in the next 7 days, soonest first, with ids.",
     "input_schema": {"type": "object", "properties": {}}},
    {"name": "attendance", "description": "Attendance per subject, worst first, with exact bunk math: can_skip_now, must_attend, next class dates and a ready sentence.",
     "input_schema": {"type": "object", "properties": {}}},
    {"name": "timetable", "description": "The weekly class timetable: day, start, end, subject code, room.",
     "input_schema": {"type": "object", "properties": {}}},
    {"name": "marks", "description": "Internal marks per subject code and component (CIE-1, quizzes, lab).",
     "input_schema": {"type": "object", "properties": {}}},
    {"name": "results", "description": "Past semester grades per subject, SGPA and CGPA.",
     "input_schema": {"type": "object", "properties": {}}},
    {"name": "materials", "description": "Notes, slides and manuals filed for the student, optionally for one subject.",
     "input_schema": {"type": "object", "properties": {"subject": {"type": "string"}}}},
    {"name": "opportunities", "description": "Internships, events and notices from college mail that passed the spam filter.",
     "input_schema": {"type": "object", "properties": {}}},
    {"name": "list_reminders", "description": "Reminders the student has set.",
     "input_schema": {"type": "object", "properties": {}}},
    {"name": "set_reminder", "description": "Remind the student before a filed, dated item (id from due_this_week).",
     "input_schema": {"type": "object", "properties": {
         "item_id": {"type": "integer"}, "before_minutes": {"type": "integer"}},
         "required": ["item_id"]}},
    {"name": "add_to_calendar", "description": "Add a filed item to Google Calendar. Needs the student's tap on their phone.",
     "input_schema": {"type": "object", "properties": {"item_id": {"type": "integer"}},
                      "required": ["item_id"]}},
]


def answer(gateway: Gateway, student_id: int, question: str) -> dict[str, Any]:
    if settings.bedrock_model_id or settings.anthropic_api_key:
        try:
            return _claude(gateway, student_id, question)
        except Exception as err:  # the model is optional: fall back rather than fail the student
            log.warning("ask: model failed, answering offline", extra={"error": type(err).__name__})
    return _offline(gateway, student_id, question)


# --- Claude -------------------------------------------------------------------------------


# The whole question must be answered before API Gateway gives up on the phone (30 s): each
# model call is one short try, and past the budget the offline answer is given instead.
ASK_BUDGET_SECONDS = 22.0
CALL_TIMEOUT_SECONDS = 10.0


def _client() -> tuple[Any, str]:
    """The same Claude as the cascade (llm.ClaudeLLM): Bedrock's Messages API (the Mantle
    client) when BEDROCK_MODEL_ID is set, else the Anthropic API. No SDK retries: a retry
    would spend the budget twice."""
    import anthropic  # lazy: offline mode never needs it

    if settings.bedrock_model_id:
        return (anthropic.AnthropicBedrockMantle(aws_region=settings.bedrock_region,
                                                 timeout=CALL_TIMEOUT_SECONDS, max_retries=0),
                settings.bedrock_model_id)
    return (anthropic.Anthropic(api_key=settings.anthropic_api_key,
                                timeout=CALL_TIMEOUT_SECONDS, max_retries=0),
            settings.llm_model)


def _claude(gateway: Gateway, sid: int, question: str) -> dict[str, Any]:
    client, model = _client()
    deadline = time.monotonic() + ASK_BUDGET_SECONDS
    today = clock.now().strftime("%A %d %B %Y, %H:%M")
    messages: list[dict[str, Any]] = [{"role": "user", "content": f"Now: {today} IST\n\n{question}"}]
    used: list[str] = []
    for _ in range(MAX_TURNS):
        left = deadline - time.monotonic()
        if left < 3:
            raise TimeoutError("ask budget spent")  # answer() gives the offline answer
        msg = client.messages.create(
            timeout=min(CALL_TIMEOUT_SECONDS, left - 1), model=model, max_tokens=600,
            system=[{"type": "text", "text": SYSTEM, "cache_control": {"type": "ephemeral"}}],
            tools=TOOLS, messages=messages,
        )
        calls = [b for b in msg.content if getattr(b, "type", "") == "tool_use"]
        if not calls:
            text = "".join(getattr(b, "text", "") for b in msg.content).strip()
            return {"answer": text or "I couldn't find that in your data.", "route": "claude",
                    "tools": used}
        # Only the fields the API takes back (a dumped block carries extra nulls).
        echo: list[dict[str, Any]] = []
        for b in msg.content:
            if getattr(b, "type", "") == "text":
                echo.append({"type": "text", "text": b.text})
            elif getattr(b, "type", "") == "tool_use":
                echo.append({"type": "tool_use", "id": b.id, "name": b.name, "input": b.input})
        messages.append({"role": "assistant", "content": echo})
        results = []
        for call in calls:
            used.append(call.name)
            try:
                out: Any = gateway.call(sid, call.name, dict(call.input))
            except Denied as err:
                out = {"status": "denied", "reason": str(err)}
            results.append({"type": "tool_result", "tool_use_id": call.id,
                            "content": json.dumps(out, default=str)[:12000]})
        messages.append({"role": "user", "content": results})
    return {"answer": "That needed too many steps. Try asking one thing at a time.",
            "route": "claude", "tools": used}


# --- offline ------------------------------------------------------------------------------

DAYS = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]
SHORT = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]

HELP = ("I'm answering offline (no AI key on this server), so I know a few kinds of "
        "question: \"Can I skip Friday?\", \"What's due this week?\", \"How is my DBMS "
        "attendance?\", \"What are my CIE marks?\", \"What's my CGPA?\", \"What classes do I "
        "have tomorrow?\", \"Any OS notes?\"")


def _has(q: str, *words: str) -> bool:
    return any(re.search(rf"\b{re.escape(w)}", q) for w in words)


def _aliases(name: str, code: str) -> set[str]:
    words = [w for w in re.split(r"[^a-z]+", name.lower()) if w and w not in {"and", "of"}]
    initials = "".join(w[0] for w in words)
    out = {name.lower(), code.lower(), initials}
    if "networks" in words:
        out |= {"cn", "dcn", "networks"}
    if "statistics" in words:
        out |= {"p&s", "pns", "probability", "stats"}
    if "operating" in words:
        out |= {"os"}
    if "algorithms" in words:
        out |= {"daa", "algorithms", "ada"}
    if "database" in words:
        out |= {"dbms", "database"}
    return out


def _subject_in(q: str, subjects: list[dict[str, Any]]) -> dict[str, Any] | None:
    for s in subjects:
        for alias in _aliases(s["subject_name"], s["subject_code"]):
            if re.search(rf"(?<![a-z]){re.escape(alias)}(?![a-z])", q):
                return s
    return None


def _day_in(q: str) -> int | None:
    """0-6 for a weekday named in the question (today/tomorrow included)."""
    now = clock.now()
    if _has(q, "today"):
        return now.weekday()
    if _has(q, "tomorrow"):
        return (now + timedelta(days=1)).weekday()
    for i, d in enumerate(DAYS):
        if _has(q, d, d[:3]):
            return i
    return None


def _call(gateway: Gateway, sid: int, tool: str, used: list[str], **args: Any) -> Any:
    used.append(tool)
    return gateway.call(sid, tool, args)["result"]


def _when(iso: str) -> str:
    return datetime.fromisoformat(iso).strftime("%a %d %b, %I:%M %p").replace(" 0", " ")


def _skip_day(gateway: Gateway, sid: int, day: int, used: list[str]) -> str:
    att = _call(gateway, sid, "attendance", used)
    tt = _call(gateway, sid, "timetable", used)
    if not att.get("connected"):
        return "Your portal isn't connected yet, so I can't do the bunk math. Connect it in Attendance."
    slots = [s for s in tt.get("data", []) if s["day"] == SHORT[day]] if tt.get("connected") else []
    if not slots:
        return f"You have no classes on {DAYS[day].title()}, so there's nothing to skip."
    by_code = {s["subject_code"]: s for s in att["subjects"]}
    counts: dict[str, int] = {}
    for s in slots:
        counts[s["subject_code"]] = counts.get(s["subject_code"], 0) + 1
    lines, risky = [], 0
    for code, n in counts.items():
        s = by_code.get(code)
        if s is None:
            continue  # a lab or a subject the portal has no attendance for
        after = s["attended"] / (s["held"] + n) * 100 if s["held"] + n else 0.0
        ok = after >= s["minimum_percent"]
        risky += not ok
        lines.append(f"• {s['subject_name']}: {s['percent']:.1f}% → {after:.1f}% "
                     f"({'still fine' if ok else 'below ' + format(s['minimum_percent'], 'g') + '%'})")
    head = (f"Skipping {DAYS[day].title()} is safe for every subject." if risky == 0 else
            f"Skipping {DAYS[day].title()} drops {risky} subject{'s' if risky > 1 else ''} "
            f"below the minimum.")
    return head + "\n" + "\n".join(lines)


def _offline(gateway: Gateway, sid: int, question: str) -> dict[str, Any]:
    q = question.lower()
    used: list[str] = []

    def done(text: str) -> dict[str, Any]:
        return {"answer": text, "route": "offline", "tools": used}

    try:
        att = None
        if _has(q, "skip", "bunk", "miss", "attendance", "attend", "absent", "leave"):
            day = _day_in(q)
            if day is not None and _has(q, "skip", "bunk", "miss", "leave", "absent"):
                return done(_skip_day(gateway, sid, day, used))
            att = _call(gateway, sid, "attendance", used)
            if not att.get("connected"):
                return done("Your portal isn't connected yet. Connect it in the Attendance tab.")
            subject = _subject_in(q, att["subjects"])
            if subject is not None:
                return done(f"{subject['subject_name']}: {subject['percent']:.1f}% "
                            f"({subject['attended']}/{subject['held']}). {subject['message']}")
            worst = att["subjects"][:3]
            return done("Worst first:\n" + "\n".join(
                f"• {s['subject_name']} {s['percent']:.1f}%: {s['message']}" for s in worst))

        if _has(q, "cgpa", "sgpa", "gpa", "result", "grade"):
            res = _call(gateway, sid, "results", used)
            if not res.get("connected"):
                return done("No results saved yet. Refresh your portal in the Attendance tab.")
            sems = sorted(res["data"]["semesters"], key=lambda s: s["semester"])
            last = sems[-1]
            return done(f"CGPA {last['cgpa']} after semester {last['semester']} (SGPA "
                        f"{last['sgpa']}). " + " · ".join(
                            f"Sem {s['semester']}: SGPA {s['sgpa']}" for s in sems))

        if _has(q, "mark", "cie", "score", "internal", "quiz"):
            mk = _call(gateway, sid, "marks", used)
            if not mk.get("connected"):
                return done("No marks saved yet. Refresh your portal in the Attendance tab.")
            att = _call(gateway, sid, "attendance", used)
            names = {s["subject_code"]: s["subject_name"] for s in att.get("subjects", [])}
            rows = mk["data"]
            subject = _subject_in(q, att.get("subjects", []))
            if subject is not None:
                rows = [r for r in rows if r["subject_code"] == subject["subject_code"]]
            if not rows:
                return done("No marks for that subject yet.")
            return done("\n".join(
                f"• {names.get(r['subject_code'], r['subject_code'])} {r['component']}: "
                f"{r['scored']:g}/{r['maximum']:g}" for r in rows[:10]))

        if _has(q, "class", "timetable", "schedule", "lecture", "period"):
            tt = _call(gateway, sid, "timetable", used)
            if not tt.get("connected"):
                return done("No timetable saved yet. Refresh your portal in the Attendance tab.")
            day = _day_in(q)
            day = clock.now().weekday() if day is None else day
            att = _call(gateway, sid, "attendance", used)
            names = {s["subject_code"]: s["subject_name"] for s in att.get("subjects", [])}
            slots = sorted((s for s in tt["data"] if s["day"] == SHORT[day]), key=lambda s: s["start"])
            if not slots:
                return done(f"No classes on {DAYS[day].title()}.")
            return done(f"{DAYS[day].title()}:\n" + "\n".join(
                f"• {s['start'][:5]} {names.get(s['subject_code'], s['subject_code'])}"
                + (f", {s['room']}" if s.get("room") else "") for s in slots))

        if _has(q, "note", "material", "slide", "pdf", "manual", "paper"):
            mats = _call(gateway, sid, "materials", used)
            att = _call(gateway, sid, "attendance", used)
            subject = _subject_in(q, att.get("subjects", []))
            if subject is not None:
                mats = [m for m in mats if m["subject"] == subject["subject_name"]]
            if not mats:
                return done("Nothing filed for that yet. Forward notes to the bot, or share them to the app.")
            return done("In Materials:\n" + "\n".join(f"• {m['title']} ({m['subject']})" for m in mats[:8]))

        if _has(q, "due", "deadline", "exam", "test", "submit", "assignment", "week", "pending"):
            due = _call(gateway, sid, "due_this_week", used)
            if not due:
                return done("Nothing due in the next 7 days.")
            return done("Due this week:\n" + "\n".join(
                f"• {d['title']} ({d['subject']}): {_when(d['due_at'])}" for d in due))

        if _has(q, "internship", "event", "hackathon", "opportunit", "mail"):
            ops = _call(gateway, sid, "opportunities", used)
            if not ops:
                return done("Nothing from college mail that fits you right now.")
            return done("From your mail, best match first:\n" + "\n".join(
                f"• {o['title']}" for o in ops[:5]))

        if _has(q, "remind"):
            return done("Tap Remind me on the card in This week: 1 day, 3 hours or 1 hour "
                        "before. (With an AI key on the server I can set it from here.)")
    except Denied as err:
        return done(f"The gateway refused that: {err}")
    return done(HELP)
