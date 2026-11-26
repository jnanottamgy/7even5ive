# Linking the WhatsApp bot's library to 7even5ive

The bot (its own service, its own Postgres and R2 storage) stays the **one library**.
7even5ive never copies it:

| Direction | What | When |
|---|---|---|
| Bot → 7even5ive (push) | `deadline.created`, `deadline.updated`, `deadline.deleted` | After the bot commits a change |
| 7even5ive → bot (pull) | Library tree, one shelf of files, one file's link, upcoming deadlines | Files tab opened, file tapped, service start |
| App → 7even5ive | Everything; the app never holds the bot's key | — |

Why: a copy would need a backfill, an event for every rename, re-filing and deletion, and a
second place holding students' files. Reading through means Files always shows exactly what
the bot has, and a file goes from R2 straight to the phone through a link that expires in
five minutes.

## The pull API (on the bot)

Read-only, `GET` only. Every request carries `Authorization: Bearer <service key>` and
`X-Student-Phone: 91XXXXXXXXXX` (a header, so the number stays out of URLs and logs). Anything
not authorised is a plain 404.

| Endpoint | Returns |
|---|---|
| `/seventy5/v1/library` | `{"subjects": [{"id", "name", "shelves": [{"shelf": "material"\|"pyq"\|"info", "label", "files"}]}], "unsorted": n}` |
| `/seventy5/v1/files?subject_id=&shelf=&offset=` (or `?unsorted=true`) | `{"files": [{"id", "kind": "file"\|"note", "title", "filename", "mime_type", "shelf", "subject_id", "created_at"}], "next_offset"}` |
| `/seventy5/v1/files/{id}/open` | `{"kind": "file", "url", "expires_in": 300, "filename", "mime_type"}` or `{"kind": "note", "title", "text"}` |
| `/seventy5/v1/deadlines` | `{"deadlines": [{"id", "title", "description", "due_at", "subject"}]}` (upcoming only) |

Code: the bot repo, branch `seventy5-link`: `app/routers/seventy5.py`,
`app/storage.py` (`link`), tests in `tests/integration/test_seventy5.py`.

## The deadline events (to 7even5ive)

`POST <7even5ive>/bot/webhook`, signed like every bot event (HMAC-SHA256 over
`"<timestamp>." + body`, headers `X-75-Timestamp`, `X-75-Signature`):

```json
{ "type": "deadline.updated", "event_id": "9f2c…", "version": 1764134400123456789,
  "from": "91XXXXXXXXXX",
  "deadline": { "id": 12, "title": "Assignment 3", "description": null,
                "due_at": "2026-11-28T18:29:00+00:00", "subject": "DBMS" } }
```

`deadline.deleted` carries only `{"id": 12}`.

- **Caught everywhere:** the bot watches its ORM, so a deadline made, edited or deleted from
  any code path is reported (`app/services/seventy5.py`).
- **Only what was committed:** delivery reads each row back after the commit, so a change
  rolled back inside a turn is never sent.
- **Never twice, never stale:** `event_id` is fixed at capture (a retry is dropped); 7even5ive
  keeps the highest `version` per deadline, so a late, older update loses.
- **Reminders follow:** a moved deadline moves its reminders (same time before); a deleted one
  cancels them.
- **Nothing lost for long:** 7even5ive backfills every upcoming deadline and the subject list
  when it starts, which repairs any event missed while it was down.

Code: `core/seventy5/library.py` (client), `core/seventy5/sync.py` (events and backfill),
`core/seventy5/tools.py` (`list_library`, `list_library_files`, `open_file`).

## Settings

**On the bot** (its `.env` on your AWS server, then redeploy):

```
SEVENTY5_SERVICE_TOKEN=<long random string A>
SEVENTY5_WEBHOOK_URL=<7even5ive AppUrl>/bot/webhook
SEVENTY5_WEBHOOK_SECRET=<long random string B>
SEVENTY5_PHONES=91XXXXXXXXXX          # your number; only linked students are served or reported
```

**On the 7even5ive demo server**: AWS console → Systems Manager → Parameter Store, **in the
stack's own region** (the serverless demo is in Sydney, `ap-southeast-2`) → create each as a
**SecureString** under `/7even5ive-demo/`. Both the serverless stack (read at every cold start)
and the EC2 stack (read at every boot) use this path. `SEVENTY5_WEBHOOK_URL` is the stack's
`BotWebhookUrl` output.

| Name | Value |
|---|---|
| `/7even5ive-demo/LIBRARY_URL` | the bot's public base URL (no trailing slash) |
| `/7even5ive-demo/LIBRARY_SERVICE_TOKEN` | string A |
| `/7even5ive-demo/BOT_WEBHOOK_SECRET` | string B |
| `/7even5ive-demo/APPROVAL_SECRET` | another long random string |
| `/7even5ive-demo/DEMO_PHONE` | your number, `91XXXXXXXXXX` |

Serverless: they apply at the next cold start (Lambda → the function → Configuration →
Environment variables → Edit → Save starts fresh instances). EC2: reboot the instance. They
never appear in the template, the console or the logs. **An EC2 stack created before this
change** wrote its start script at first boot, so delete and recreate it once (about 15
minutes).

Without these settings everything still runs: Files shows an invented demo library and no
deadlines are backfilled.

## Check it

1. Forward a deadline to the bot on WhatsApp. Within seconds, pull to refresh in the app: the
   card is on *This week*, tagged `bot`.
2. Tell the bot "move it to Monday": the card moves, and any reminder moves with it.
3. Open *Files*: your subjects, the three shelves, your files. Tap a PDF: it opens.
4. Delete the deadline in the bot: the card disappears and its reminder is cancelled.
