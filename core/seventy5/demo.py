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
import time
from datetime import timedelta
from typing import Any

from . import clock
from .config import settings
from .jev import Decisions, Likely, Picked
from .llm import LLMError, Proposal

# The five theory subjects of PortMax's mock college, so 75 and the portal agree on names.
SUBJECTS = ["Computer Networks", "Database Management Systems",
            "Design and Analysis of Algorithms", "Operating Systems", "Probability and Statistics"]
PORTAL_ID = "demo"
PHONE, TOKEN = "919900000001", "demo-student-token"


def _at(days: int, hour: int, minute: int = 0) -> str:
    day = clock.now() + timedelta(days=days)
    return clock.iso(day.replace(hour=hour, minute=minute, second=0, microsecond=0))


def messages() -> list[dict[str, Any]]:
    """(source, message, what Jev says, what the LLM says) -- the LLM part only if reached."""
    friday = (4 - clock.now().weekday()) % 7 or 7
    return [
        {"source": "whatsapp", "text": "DBMS Assignment 3 due Fri 11:59 pm",
         "jev": {"kind": ("deadline", .95), "subject": ("Database Management Systems", .93)},
         "llm": Proposal("deadline", "Database Management Systems", "DBMS Assignment 3", _at(friday, 23, 59))},
        {"source": "whatsapp", "text": "DBMS unit 3 notes", "attachment": "DBMS_Unit3_notes.pdf",
         "jev": {"kind": ("material", .96), "subject": ("Database Management Systems", .94)}},
        {"source": "whatsapp", "text": "CIE-2 for DCN on Monday, units 3 and 4",
         "jev": {"kind": ("exam", .91), "subject": ("Computer Networks", .62)},
         "llm": Proposal("exam", "Computer Networks", "DCN CIE-2 (units 3 and 4)",
                         _at((7 - clock.now().weekday()) % 7 or 7, 9))},
        {"source": "whatsapp", "text": "ok 👍", "jev": {"kind": ("chitchat", .97)}},
        {"source": "whatsapp", "text": "DCN lab manual, print it",
         "attachment": "DCN_Lab_Manual.docx",
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
                         _at((5 - clock.now().weekday()) % 7 or 7, 10))},
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
    db = app.db
    with db.tx() as c:
        for table in ("audit", "calendar", "pending_approvals", "used_approvals", "items",
                      "events", "subjects", "students"):
            c.execute(f"DELETE FROM {table}")
        cur = c.execute("INSERT INTO students(name, wa_phone, mcp_token, branch, year, interests,"
                        " portal_id) VALUES (?,?,?,?,?,?,?)",
                        ("Demo Student", PHONE, TOKEN, "CSE", 3, "hackathons, backend, AI",
                         PORTAL_ID))
        sid = int(cur.lastrowid or 0)
        c.executemany("INSERT INTO subjects(student_id, name) VALUES (?,?)",
                      [(sid, s) for s in SUBJECTS])
    seed_portal()
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

    lines = []
    for i, m in enumerate(messages(), 1):
        if m["source"] == "whatsapp":
            body = json.dumps({"from": PHONE, "message_id": f"wamid.demo{i}", "text": m["text"],
                               "attachment": m.get("attachment")}).encode()
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


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")  # Windows consoles default to cp1252
    from fastapi.testclient import TestClient

    from .api import create
    from .app import build

    live = bool(settings.jev_api_key and (settings.anthropic_api_key or settings.bedrock_model_id))
    script = messages()
    app = build(
        jev=None if live else FixtureDecider({m["text"]: m["jev"] for m in script}),
        llm=None if live else FixtureLLM({m["text"]: m["llm"] for m in script if "llm" in m}),
    )
    sid = seed(app)
    api = create(app)
    client = TestClient(api)
    print(f"mode: {'LIVE Jev + Claude' if live else 'offline, recorded answers'}\n")
    print("source    route     outcome      message")
    print("\n".join(play(app, client, sid)))

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

        uvicorn.run(api, host="127.0.0.1", port=int(os.environ.get("PORT", "8000")))


if __name__ == "__main__":
    main()
