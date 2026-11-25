# PortMax

One college portal in, five read-only tools out, the same shape for every college:
`get_attendance`, `get_timetable`, `get_marks`, `get_results`, `get_profile`.

The plan, and why each piece is the way it is: [`../docs/portmax.md`](../docs/portmax.md).

## How it fits together

- **Forge time, once per college, by our team.** A team member records their own visit to the
  portal (`forge capture`). The recording is scrubbed of cookies and personal details
  (`forge sanitize`). reverse-api-engineer, run with PortMax's own prompt, writes a draft
  connector (`forge engineer`): a fetch plan (`fetch_plan.json`, data) and pure parsers
  (`parsers.py`). The draft's plan is replayed against the recording to make fixtures
  (`forge fixtures`), a person checks the answers against the portal screen (`forge answers`,
  `forge accept`), and `forge verify` gates `forge publish`.
- **Run time, every student.** The student logs in on the portal's own page inside the Android
  app. The app injects `runner/portmax-runner.js`, which runs the fetch plan in that session and
  uploads the pages (`POST /v1/pages`); the server parses them, keeps only the answers and drops
  the pages. A keep-alive reads one page at the longest interval the portal's idle timeout
  allows, and every few hours runs the whole plan. The tools answer from saved data through a
  Lambda behind AgentCore Gateway (`adapters/lambda_handler.py`), or locally over MCP.

## Develop

```bash
uv sync                      # add --extra forge for the engineer step
uv run pytest                # -m "not browser" skips the real-Chromium tests
uv run ruff check . && uv run ruff format --check .
uv run mypy
```

## Try it against the mock portal

```bash
uv run portmax mock serve --fixed-captcha     # http://127.0.0.1:8765, CAPTCHA is PM42X
                                              # USN 1MC24CS042, born 14-08-2005, digits 2345

PORTMAX_DATABASE_URL=sqlite:///portmax-demo.db uv run portmax mock seed --student demo
```

The seed connects a demo student to the mock portal; the repository's `.mcp.json` then lets
Claude Code ask "what's my DBMS attendance?" through `portmax mcp`.

## Forge a real college

Only with your own account, at your own pace, and never on a portal that has not agreed to it.

```bash
uv sync --extra forge
uv run portmax forge capture captures/mycollege --url https://portal.example.edu/
uv run portmax forge sanitize captures/mycollege/raw.har --usn ... --name "..." \
    --dob YYYY-MM-DD --phone ... --delete-raw
mkdir -p drafts/mycollege   # write its manifest.yaml (copy the mock's and edit)
ANTHROPIC_API_KEY=... uv run portmax forge engineer drafts/mycollege \
    --har captures/mycollege/sanitized.har --report captures/mycollege/sanitize-report.json
uv run portmax forge answers drafts/mycollege        # check against the portal screen
uv run portmax forge accept drafts/mycollege
uv run portmax forge verify drafts/mycollege --report captures/mycollege/sanitize-report.json
uv run portmax forge publish drafts/mycollege --report captures/mycollege/sanitize-report.json
```

## Layout

| Path | What it is |
| --- | --- |
| `src/portmax/contract.py` | The five tools' shapes and their sanity rules |
| `src/portmax/plan.py`, `executor.py` | The GET-only fetch plan and its Python runner |
| `src/portmax/runner/portmax-runner.js` | The same runner for the Android WebView |
| `src/portmax/connectors/<college>/` | `manifest.yaml`, `fetch_plan.json`, `parsers.py`, `fixtures/`, `golden/` |
| `src/portmax/ingest.py`, `store.py`, `tools.py` | Pages in, answers saved, pages dropped; tools from saved answers |
| `src/portmax/api.py` | The API the app talks to |
| `src/portmax/adapters/` | Lambda (production, behind AgentCore Gateway) and MCP (development) |
| `src/portmax/wakeups.py` | Which phones to wake so their keep-alive lands inside the timeout |
| `src/portmax/forge/` | capture, sanitize, engineer, fixtures, verify, publish |
| `src/portmax/mock_portal/` | A made-up college portal with real session rules, for tests and demos |
