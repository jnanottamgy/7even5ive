# 7even5ive core

Everything at your fingertips, using MCP. 75 is a campus agent that turns a student's
WhatsApp class groups, college email, Google Classroom and portal into deadlines,
materials, attendance warnings and real opportunities, and serves them to the student's
phone and to their own Claude or ChatGPT over MCP, behind one gateway with one set of rules.

wHACKiest 2026 · Track 1: Make MCP Matter.

## Run it (no accounts needed)

```bash
cd core
python -m venv .venv && .venv/Scripts/pip install -r requirements.txt   # Windows; installs ../portmax too
python -m seventy5.demo          # replays a morning's messages, then serves :8000
python -m pytest -q
```

Open the link it prints (`http://localhost:8000/#demo-student-token`).

Every external service has a stand-in, so the demo runs offline: without keys, Jev's and
the LLM's answers are replayed from `seventy5/demo.py` and the printout says so. Copy
`.env.example` to `.env` and add `JEV_API_KEY` plus `BEDROCK_MODEL_ID` (or
`ANTHROPIC_API_KEY`) to run them live. `.env` is git-ignored; never commit keys.

## MCP

```bash
SEVENTY5_TOKEN=demo-student-token python -m seventy5.mcp_server          # stdio
python -m seventy5.mcp_server --http                                     # :8001, Bearer token
```

Tools: `due_this_week`, `materials`, `attendance`, `opportunities`, `add_to_calendar`.

## How it works

```
WhatsApp bot ─signed event─┐
Gmail / Classroom ─────────┼─> ingress (verify, dedupe) ─> queue ─> cascade ─> database
Portal (every morning) ────┘                                         │
                                                                     ▼
       phone · Claude · ChatGPT · voice agent ──> gateway ──> tools (read DB / ask to write)
```

- **Cascade** (`cascade.py`): Classroom's own due date → **Jev** (what is it, which subject,
  is it spam, is it relevant) → **LLM** (reads dates and titles, or decides when Jev was
  unsure). Every item is filed or goes to the LLM. Jev drops chit-chat or spam only at
  0.9 confidence. Every LLM value is gated against the student's real data before a write.
- **Gateway** (`gateway.py`): inbound auth → interceptor (a write may only use rows 75
  filed itself, plus a one-time approval token) → deny-by-default policy → audit log.
  Gmail is read-only; nothing writes outside 75 without the student tapping Approve.
- **Attendance** comes from PortMax's `get_attendance_plan` (`tools.attendance`).

| file | |
|---|---|
| `seventy5/ingress.py` | HMAC + timestamp check, idempotency keys |
| `seventy5/cascade.py` | Classroom → Jev → LLM, and the gate |
| `seventy5/jev.py` · `llm.py` | the two models, each with an offline stand-in |
| `seventy5/gateway.py` | policy, approvals, provenance, audit |
| `seventy5/tools.py` | what every client can ask |
| `seventy5/mcp_server.py` · `api.py` | MCP and HTTP faces of the same tools |
| [`../docs/bot-events.md`](../docs/bot-events.md) | the event format the WhatsApp bot posts |

All demo data is invented.
