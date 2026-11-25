# Mail filter

Reads a student's college mail twice a day and keeps only **placements, internships and
exam-cell notices**, each as a card with its deadline, event date, form link and a link back to
the mail. Everything else is left alone. Gmail access is read-only; nothing is ever sent,
deleted or marked as read.

The plan, and why each piece is the way it is: [`../docs/mailfilter.md`](../docs/mailfilter.md).

## How it fits together

- **When:** at 1 PM and 9 PM India time (EventBridge, `mailfilter schedule` prints the cron
  expressions) and when the student presses "check now" (5-minute cooldown). Each check reads
  every mail since the last one, oldest first; a two-hour overlap catches mail Gmail lists late,
  and mail already judged is skipped by id. Gmail's change history brings in mail the student
  rescues from spam or trash (it keeps its old date, so no date window would find it), and mail
  that could not be judged is retried by id at the next checks.
- **Reading:** `gmail.py` lists ids (`after:` in exact seconds, because a plain date means
  midnight Pacific time) and fetches each mail raw; `mime.py` turns it into text with every link,
  including those behind "click here", and attachment names only. Sent mail, drafts, spam and
  trash are never judged.
- **Judging:** Claude Haiku 5.5 on Amazon Bedrock in Mumbai (`judge.py`) answers in a fixed JSON
  shape. **Code then checks every field against the mail** (`checks.py`, `dates.py`): copied
  words must be in the mail, a date must be one its quote names, at the time it names (23:59 when
  none), not before the mail arrived; a form link must be https and in the mail. A field that
  fails is dropped, never guessed.
- **The Jev slot** (`sorter.py`): a sorter may drop obvious junk before Claude reads it, only as
  "other" and only at 90% confidence or more. Off until Jev is compared with Claude on the sample
  mails.
- **Cards** (`store.py`): the same opportunity seen again (a reminder, a forward) updates one
  card: matched on the same form link from the same company (a shared placement-portal link
  alone never merges two drives), else the same conversation and title, else the same company
  and role. Per field, the newest news wins; a forward counts from the date of the mail it
  forwards, so it can carry an extension but never bring back a replaced date. Mail bodies are
  never stored.
- **Never losing a mail** (`run.py`): the next check starts after mail that is settled only. Claude
  or Gmail down, one mail that cannot be judged (retried at three checks, then given up), more
  mail than one check takes, a crash, a disconnect mid-check, two checks overlapping (a lease
  renewed before every mail; only its holder can move the start): each is covered by a test.
- **Serving:** `get_opportunities` through a Lambda behind AgentCore Gateway
  (`adapters/lambda_handler.py`) or locally over MCP; `tools.py` also writes the 7 AM briefing
  lines and lists what is due within a day for the urgent call. No model writes any of it.

## Develop

```bash
uv sync
uv run pytest            # offline, about 15 s; the real-model eval is skipped
uv run ruff check . && uv run ruff format --check .
uv run mypy
```

## Try it offline

The 30 sample mails (`samples.py`, all invented) through the whole pipeline, with the answers a
correct judge would give:

```bash
MAILFILTER_DATABASE_URL=sqlite:///mailfilter-demo.db uv run mailfilter demo
MAILFILTER_DATABASE_URL=sqlite:///mailfilter-demo.db uv run mailfilter cards --include-past
```

With the repository's `.mcp.json`, Claude Code then answers "any placement deadlines this week?".

## Connect a demo Gmail account

1. In the team's Google Cloud project: enable the Gmail API; set the OAuth consent screen to
   **Testing** and add the demo accounts as test users (at most 100; their sign-in lapses after
   7 days, then run `connect` again); create an OAuth client of type **Desktop app**.
2. `export MAILFILTER_GOOGLE_CLIENT_ID=... MAILFILTER_GOOGLE_CLIENT_SECRET=...`
3. `uv run mailfilter connect --student demo` opens Google's sign-in (read-only Gmail, PKCE,
   loopback redirect), stores the refresh token in `.mailfilter-tokens.json` (mode 0600, never
   committed) and reads that day's mail.
4. `uv run mailfilter check --student demo` checks again; `disconnect` revokes and deletes all.

Bedrock needs AWS credentials with access to the Haiku model in `ap-south-1` (override with
`MAILFILTER_MODEL` and `MAILFILTER_AWS_REGION`). Production keeps Google tokens in AgentCore
Identity instead of the file; until that is wired, the check Lambda refuses with
`token_source_not_configured`.

## Score Claude on the sample mails

```bash
uv run mailfilter eval                                   # or:
RUN_EVALS=1 uv run pytest tests/test_real_model.py -v -s
```

Scored on what ends up on the card (kind, deadline, event date, link), never on wording.
