"""The demo: one invented student, a morning's messages, and the whole loop end to end.

    python -m seventy5.demo            # replay, print what happened, then serve on :8000
    python -m seventy5.demo --no-serve

With JEV_API_KEY and ANTHROPIC_API_KEY set, Jev and Claude really decide. Without them,
recorded answers are replayed (FixtureDecider / FixtureLLM) so the demo runs offline;
the printout says which mode ran. Every message here is invented -- no real chats.
"""

from __future__ import annotations

import json
import os
import sys
import threading
import time
from datetime import timedelta
from typing import Any

from . import clock
from .config import settings
from .db import token_hash
from .jev import Decisions, Likely, Picked
from .llm import LLMError, Proposal

# The five theory subjects of PortMax's mock college, so 75 and the portal agree on names.
SUBJECTS = ["Computer Networks", "Database Management Systems",
            "Design and Analysis of Algorithms", "Operating Systems", "Probability and Statistics"]
PORTAL_ID = "demo"
# DEMO_PHONE: the number your bot knows you by (91 + 10 digits), so its events reach this
# student. The default is invented.
PHONE = "".join(ch for ch in os.environ.get("DEMO_PHONE", "919900000001") if ch.isdigit())
# The demo student's token: public on purpose (it is in the app, behind "Try the demo"). The
# database keeps only its hash, like any personal token. Real accounts sign in with Supabase.
TOKEN = "demo-student-token"
# The job row that remembers when the demo morning was last seeded (seeded_today).
SEED_JOB = "demo-seed"


def student_id(db: Any) -> int | None:
    row = db.student_by_token(TOKEN)
    return int(row["id"]) if row is not None else None


def is_demo(db: Any, sid: int) -> bool:
    """The shared demo student: everyone who taps "Try the demo" is this one student."""
    row = db.student(sid)
    return row is not None and row["token_hash"] == token_hash(TOKEN)


def seeded_today(db: Any) -> bool:
    job = db.job(SEED_JOB)
    if job is None or student_id(db) is None:
        return False
    return str(job["last_run_at"])[:10] == clock.iso(clock.now())[:10]


def _next(weekday: int, hour: int, minute: int = 0) -> str:
    """The next such weekday and time after now (Mon=0). Always within the coming 7 days, so the
    demo's "due Fri" sits in "due this week" whatever day and hour the demo runs."""
    now = clock.now()
    days = (weekday - now.weekday()) % 7
    at = (now + timedelta(days=days)).replace(hour=hour, minute=minute, second=0, microsecond=0)
    if at <= now:
        at += timedelta(days=7)
    return clock.iso(at)


def _at(days: int, hour: int, minute: int = 0) -> str:
    day = clock.now() + timedelta(days=days)
    return clock.iso(day.replace(hour=hour, minute=minute, second=0, microsecond=0))


def messages() -> list[dict[str, Any]]:
    """(source, message, what Jev says, what the LLM says) -- the LLM part only if reached."""
    return [
        # The bot already filed this one: 7even5ive checks its answer and files it, no model.
        {"source": "whatsapp", "text": "DBMS Assignment 3 due Fri 11:59 pm",
         "decision": {"kind": "deadline", "subject": "Database Management Systems",
                      "title": "DBMS Assignment 3", "due_at": _next(4, 23, 59)},
         "jev": {"kind": ("deadline", .95), "subject": ("Database Management Systems", .93)},
         "llm": Proposal("deadline", "Database Management Systems", "DBMS Assignment 3", _next(4, 23, 59))},
        {"source": "whatsapp", "text": "DBMS unit 3 notes", "attachment": "DBMS_Unit3_notes.pdf",
         "decision": {"kind": "material", "subject": "Database Management Systems"},
         "jev": {"kind": ("material", .96), "subject": ("Database Management Systems", .94)}},
        {"source": "whatsapp", "text": "CIE-2 for DCN on Monday, units 3 and 4",
         "jev": {"kind": ("exam", .91), "subject": ("Computer Networks", .62)},
         "llm": Proposal("exam", "Computer Networks", "DCN CIE-2 (units 3 and 4)",
                         _next(0, 9))},
        {"source": "whatsapp", "text": "ok 👍", "jev": {"kind": ("chitchat", .97)}},
        {"source": "whatsapp", "text": "DCN lab manual, print it",
         "attachment": "DCN_Lab_Manual.docx",
         "decision": {"kind": "material", "subject": "Computer Networks"},
         "jev": {"kind": ("material", .9), "subject": ("Computer Networks", .88)}},
        {"source": "gmail", "text": "OFFICIAL NOTICE from \"MSRIT T&P Cell\": mandatory "
                                    "placement registration, pay Rs 499 by tonight",
         "jev": {"kind": ("notice", .7), "spam": .97, "relevant": .2}},
        {"source": "gmail", "text": "Internship desk: stipend up to Rs 15,000. Registration "
                                    "fee Rs 2,999.",
         "jev": {"kind": ("event", .6), "spam": .94, "relevant": .3}},
        {"source": "gmail", "text": "Open hackathon at IISc this Saturday 10 am, teams of 3, "
                                    "open to 2nd and 3rd year CSE",
         "jev": {"kind": ("event", .9), "subject": ("Miscellaneous", .9), "spam": .04,
                 "relevant": .88},
         "llm": Proposal("event", "Miscellaneous", "IISc open hackathon",
                         _next(5, 10))},
        {"source": "classroom", "text": "New assignment: OS mini project",
         "classroom": {"title": "OS mini project (10 marks)", "due_at": _at(3, 23, 59)},
         "jev": {"kind": ("deadline", .93), "subject": ("Operating Systems", .97)}},
    ]


class FixtureDecider:
    def __init__(self, script: dict[str, dict[str, Any]]) -> None:
        self.script = script

    def decide(self, state: dict[str, Any], questions: dict[str, Any]) -> Decisions:
        said = self.script.get(state.get("text", ""), {})
        answers: dict[str, Picked | Likely] = {}
        for key, value in said.items():
            if key in questions:
                answers[key] = Picked(*value) if isinstance(value, tuple) else Likely(value)
        return Decisions(answers, input_tokens=180)


class FixtureLLM:
    def __init__(self, script: dict[str, Proposal]) -> None:
        self.script = script

    def propose(self, text: str, subjects: list[str], today: str,
                hints: dict[str, str]) -> Proposal:
        if text not in self.script:
            raise LLMError("unscripted")
        return self.script[text]


def seed(app: Any) -> int:
    """The demo student, back to the start of the demo morning. Only the demo student's rows
    change: on Supabase the same database holds every real account. Its phones (wake-ups) and
    call settings stay; its cards, reminders, calls, mail and approvals start over."""
    from . import mail

    db = app.db
    existing = db.student_by_token(TOKEN)
    # The demo's number, unless a real account linked it (WhatsApp proved it is theirs then):
    # the invented morning must never land in a real student's cards.
    owner = db.student_by_phone(PHONE)
    phone = PHONE if owner is None or (existing is not None and owner["id"] == existing["id"]) else None
    profile = {"name": "Demo Student", "wa_phone": phone, "branch": "CSE", "year": 3,
               "interests": "hackathons, backend, AI", "portal_id": PORTAL_ID,
               "college": "mockcollege"}
    with db.tx() as c:
        if existing is None:
            cols = ", ".join([*profile, "token_hash", "created_at"])
            marks = ", ".join("?" for _ in range(len(profile) + 2))
            cur = c.execute(f"INSERT INTO students({cols}) VALUES ({marks}) RETURNING id",
                            (*profile.values(), token_hash(TOKEN), clock.iso(clock.now())))
            sid = int(cur.fetchone()["id"])
        else:
            sid = int(existing["id"])
            from .db import STUDENT_TABLES

            for table in STUDENT_TABLES:
                if table != "devices":
                    c.execute(f"DELETE FROM {table} WHERE student_id=?", (sid,))
            sets = ", ".join(f"{k}=?" for k in profile)
            c.execute(f"UPDATE students SET {sets} WHERE id=?", (*profile.values(), sid))
        for name in SUBJECTS:
            c.execute("INSERT INTO subjects(student_id, name) VALUES (?,?)", (sid, name))
    seed_portal()
    mail.reset_demo(sid)
    return sid


def seed_portal() -> None:
    """What a morning refresh of PortMax's mock college would have saved (its golden answers)."""
    from importlib.resources import files

    from .tools import portal_store

    golden = files("portmax.connectors.mockcollege") / "golden"
    answers = {tool: json.loads((golden / f"{tool}.json").read_text(encoding="utf-8"))
               for tool in ("get_attendance", "get_timetable")}
    portal_store().save_answers(PORTAL_ID, "mockcollege", "1.0.0", clock.now(), answers)


def play(app: Any, client: Any, sid: int) -> list[str]:
    from .ingress import accept, sign

    from .library import configured

    lines = []
    linked = configured()
    # A real account linked the demo's number: its forwards would land in that account.
    owns_phone = app.db.student(sid)["wa_phone"] == PHONE
    for i, m in enumerate(messages(), 1):
        if (linked or not owns_phone) and m["source"] == "whatsapp":
            # A real bot is linked: its own deadlines arrive by backfill and events, so the
            # invented forwards would only duplicate them. Mail and Classroom stay invented.
            continue
        if m["source"] == "whatsapp":
            # No decision = the bot was unsure, so 7even5ive's own cascade decides.
            body = json.dumps({"from": PHONE, "message_id": f"wamid.demo{i}", "text": m["text"],
                               "attachment": m.get("attachment"),
                               "decision": m.get("decision")}).encode()
            ts = int(time.time())
            r = client.post("/bot/webhook", content=body,
                            headers={"x-75-timestamp": str(ts), "x-75-signature": sign(body, ts)})
            r.raise_for_status()
        else:
            payload = {k: m[k] for k in ("text", "attachment", "classroom") if k in m}
            accept(app.db, app.queue, sid, m["source"], f"demo{i}", payload)
            app.work()
        out = app.last[-1] if app.last else None
        label = f"{out.route:9} {out.status:12}" if out else "-"
        lines.append(f"{m['source']:9} {label} {m['text'][:60]}")
    return lines


def recorded_answers() -> tuple[FixtureDecider, FixtureLLM]:
    script = messages()
    return (FixtureDecider({m["text"]: m["jev"] for m in script}),
            FixtureLLM({m["text"]: m["llm"] for m in script if "llm" in m}))


def live_models() -> bool:
    return bool(settings.jev_api_key and (settings.anthropic_api_key or settings.bedrock_model_id))


_morning_lock = threading.Lock()


def morning(app: Any) -> tuple[int, list[str]]:
    """Seed the demo student and replay the morning: (sid, log lines).

    The replay runs on its own copy of the app: the same database and outbox, but its own queue
    and a cascade of its own, with the recorded answers (or, with DEMO_LIVE_REPLAY=1 on a laptop,
    the live models). The live app's models are never swapped, so a real student's message
    arriving during a demo reset is decided as always. One morning at a time: two resets at once
    would interleave their deletes and inserts. Only when the whole morning is in is it recorded
    as today's (seeded_today), so a cold start cut short tries again at the next one.
    On a cold Lambda start a live replay would spend its 29 s and money on invented messages,
    which is why recorded answers are the default."""
    from fastapi.testclient import TestClient

    from . import mail, sync
    from .api import create
    from .app import App
    from .cascade import Cascade
    from .jobqueue import Queue

    with _morning_lock:
        if live_models() and os.environ.get("DEMO_LIVE_REPLAY") == "1":
            jev, llm = app.cascade.jev, app.cascade.llm
        else:
            jev, llm = recorded_answers()
        replay = App(db=app.db, queue=Queue(), cascade=Cascade(app.db, jev, llm),
                     gateway=app.gateway, last=[], sender=app.sender, caller=app.caller)
        sid = seed(replay)
        lines = play(replay, TestClient(create(replay)), sid)
        if app.db.student(sid)["wa_phone"]:
            lines += sync.backfill(app.db, sid)
        lines += mail.startup(app.db, sid)
        app.db.job_ran(SEED_JOB, clock.iso(clock.now()), None)
        return sid, lines


def refresh_if_stale(app: Any) -> bool:
    """The daily job: a new demo morning when today's hasn't been made yet. True if it was."""
    if seeded_today(app.db):
        return False
    morning(app)
    return True


def prepare(db_url: str | None = None, run_jobs: bool = False,
            daily: bool = False) -> tuple[Any, Any, int, bool, list[str]]:
    """Build the app, seed the student and replay the morning: (app, api, sid, live, lines).

    Shared by the local demo and the cloud service, so both start from the same morning.
    run_jobs: the served API runs the background loop itself (the laptop demo). The online
    service leaves it off and runs the loop in its router.
    daily: keep a demo morning already seeded today (the online service on Supabase, where a
    cold start must not wipe what someone is showing); without it, always start over.
    """
    from .api import create
    from .app import build

    live = live_models()
    recorded = recorded_answers()
    app = build(db_url) if live else build(db_url, jev=recorded[0], llm=recorded[1])
    api = create(app, run_jobs=run_jobs)
    if daily and seeded_today(app.db):
        sid = student_id(app.db)
        assert sid is not None
        return app, api, sid, live, ["demo      today's demo morning kept (seeded earlier today)"]
    sid, lines = morning(app)
    return app, api, sid, live, lines


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")  # Windows consoles default to cp1252
    app, api, sid, live, lines = prepare(run_jobs="--no-serve" not in sys.argv)
    print(f"mode: {'LIVE Jev + Claude' if live else 'offline, recorded answers'}\n")
    print("source    route     outcome      message")
    print("\n".join(lines))

    print("\nMCP-style calls through the gateway:")
    gw = app.gateway
    due = gw.call(sid, "due_this_week")["result"]
    for d in due:
        print(f"  due  {d['due_at']}  {d['subject']}: {d['title']}  (#{d['id']})")
    for row in gw.call(sid, "attendance")["result"]["subjects"]:
        print(f"  att  {row['subject_name'][:30]:30} {row['percent']:5}%  {row['message']}")
    print("  add_to_calendar ->", gw.call(sid, "add_to_calendar", {"item_id": due[0]["id"]})["status"])
    try:
        gw.call(sid, "send_email", {"to": "x"})
    except Exception as err:
        print("  send_email      -> denied:", err)
    print(f"\nWeb app: http://localhost:8000/#{TOKEN}")
    if "--no-serve" not in sys.argv:
        import uvicorn

        # HOST=0.0.0.0 lets a phone on the same Wi-Fi (or the emulator at 10.0.2.2) reach it.
        uvicorn.run(api, host=os.environ.get("HOST", "127.0.0.1"), port=int(os.environ.get("PORT", "8000")))


if __name__ == "__main__":
    main()
