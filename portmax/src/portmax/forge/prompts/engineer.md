You are building a PortMax connector for one college's student portal from a recording of a
student browsing it. PortMax turns every college portal into the same five read-only tools, so
the rest of the product never sees a portal's HTML.

## What you are given

- A sanitised recording (HAR) of a team member's own visit: `$har_path`. Cookies, tokens and
  personal details are already replaced with stand-ins such as `<cookie:1>`, `USN0000001` and
  `Student Name`. Request bodies are removed. Read it with Python, not by printing it whole.
- The connector draft folder: `$draft_dir`. A `manifest.yaml` is already there; keep its
  college, name and base_url, and fill in `markers` if they are placeholders.
- What the person saw on screen, if they wrote it down: `$notes_path`.

## What you must write, in `$draft_dir`

1. `fetch_plan.json`: the pages to read, as data. Schema:

   ```json
   {
     "version": "1",
     "steps": [
       {"id": "dashboard", "path": "/index.php?option=...&task=dashboard"},
       {"id": "course", "for_each": {"from": "dashboard", "select": "CSS selector of links", "attr": "href", "max_items": 30}}
     ],
     "keepalive_step": "dashboard",
     "tool_steps": {"get_attendance": ["course"], "get_profile": ["dashboard"]},
     "pace_ms": 500
   }
   ```

   Every request is a GET; there is no method field. A step has either a fixed relative `path`
   or `for_each`, which follows links found on an earlier step's pages. `keepalive_step` must be
   one light, fixed page that only a logged-in student can see (usually the dashboard).
   `tool_steps` names the steps whose pages each tool's parser needs. Leave out a tool the portal
   does not have.

2. `parsers.py`: pure functions, one per tool the portal has:

   ```python
   def parse_attendance(pages: PagesByStep) -> list[AttendanceRow]: ...
   def parse_timetable(pages: PagesByStep) -> list[TimetableSlot]: ...
   def parse_marks(pages: PagesByStep) -> list[MarkRow]: ...
   def parse_results(pages: PagesByStep) -> Results: ...
   def parse_profile(pages: PagesByStep) -> Profile: ...
   ```

   `pages` maps a step id to the list of `Page` objects fetched for it (`page.html`, `page.url`).
   Import the models from `portmax.contract` and use the helpers in `portmax.htmlkit`
   (`parse`, `one`, `text`, `table_rows`, `table_kv`, `number`, `integer`, `only`, `Missing`).
   Read the contract first: `$contract_path`. Its validators reject impossible values, so map the
   portal's fields carefully (attended, held, percentage, planned classes where shown).

3. In `manifest.yaml`, set `tools` to the tools the portal actually has.

## Rules that cannot be broken

- Never write a cookie, token, session id, USN, name, date of birth or phone number into any
  file. The session is the student's own and is never part of a connector.
- Never hard-code an answer: no subject name, subject code, room, mark or percentage from the
  recording may appear in `parsers.py` or `fetch_plan.json`. Parsers find values by structure.
- Read-only: only pages that show data. Never a path that logs out, saves, submits, pays,
  edits, changes a password, uploads or cancels. `portmax` refuses such paths anyway.
- Parsers are pure: no network, no files, no subprocesses, no `eval`, and imports only from
  `re`, `datetime`, `typing`, `decimal`, `math`, `collections`, `itertools`, `functools`, `enum`,
  `__future__`, `portmax.contract`, `portmax.htmlkit` and `portmax.pages`.
- Do not try to get around bot detection, CAPTCHAs or rate limits in any way. If the recording
  is missing a page, say so and stop; the person will capture again.
- Do not contact the portal. Work only from the recording.

## How to check your work, and repeat until it passes

```bash
cd $project_dir
uv run portmax forge fixtures $draft_dir --har $har_path
uv run portmax forge check $draft_dir --report $report_path
uv run portmax forge answers $draft_dir
```

`fixtures` replays your plan against the recording and saves the pages it gets; it fails if the
plan asks for a page the recording does not have. `check` runs every safety check except the
golden comparison, which a person does after you. `answers` prints what your parsers read;
compare it with the recording, and with `$notes_path` if it has numbers. When `check` passes and
the answers are right, call `report_client_verified` once, with a short summary of the steps and
which tools the portal has.
