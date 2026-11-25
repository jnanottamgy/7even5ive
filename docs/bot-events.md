# WhatsApp bot → 7even5ive: event format

The bot pushes every message a student sends it to 7even5ive, which never polls the bot.
When the bot has already filed the message, send its **decision** too: 7even5ive checks it in
code (the subject must be one of the student's subjects, the date must be real) and files it
without calling a model. Leave `decision` out when the bot was unsure, and 7even5ive's own
cascade (Jev, then the LLM) decides. The file itself stays with the bot; 7even5ive fetches it
over the bot's MCP tool by `file_id`.

## Request

```
POST /bot/webhook
Content-Type: application/json
X-75-Timestamp: 1764067200            # unix seconds, when the bot sent it
X-75-Signature: <hex>                 # see below
```

```json
{
  "from": "919900000001",             // student's number: 91 + 10 digits, no +
  "message_id": "wamid.HBgM...",      // WhatsApp's id; 7even5ive dedupes on it
  "text": "DBMS Assignment 3 due Fri 11:59 pm",
  "attachment": "DBMS_Unit3_notes.pdf", // optional: file name only
  "file_id": "f_8812",                // optional: the bot's id for that file, fetched later over MCP
  "group": "CSE 3B Announcements",     // optional: where it was forwarded from
  "decision": {                        // optional: what the bot already decided
    "kind": "deadline",                // deadline | exam | material | event | notice | chitchat
    "subject": "Database Management Systems",  // exactly as in the student's subject list
    "title": "DBMS Assignment 3",      // optional for materials (the file name is used)
    "due_at": "2026-11-27T23:59+05:30" // ISO 8601, IST; required for deadline, exam, event
  }
}
```

## Signature

```
signature = hex( HMAC_SHA256( BOT_WEBHOOK_SECRET, f"{timestamp}." + raw_body_bytes ) )
```

- Sign the **exact bytes** you send. Re-serialising the JSON changes them.
- 7even5ive rejects a timestamp more than 300 s away from its clock, so a captured request
  cannot be replayed later.
- `BOT_WEBHOOK_SECRET` is shared out of band, never committed.

Python, for reference:

```python
import hashlib, hmac, json, time, httpx
body = json.dumps(event).encode()
ts = int(time.time())
sig = hmac.new(SECRET.encode(), f"{ts}.".encode() + body, hashlib.sha256).hexdigest()
httpx.post(URL, content=body, headers={"X-75-Timestamp": str(ts), "X-75-Signature": sig})
```

## Responses

| status | meaning | bot should |
|---|---|---|
| 200 `{"ok": true, "duplicate": false}` | queued | nothing |
| 200 `{"ok": true, "duplicate": true}` | already seen this `message_id` | nothing (safe to retry) |
| 200 `{"ok": true}` | number is not a 7even5ive student | nothing; 7even5ive stores no row |
| 401 | bad or stale signature | check the secret and clock |

7even5ive answers within milliseconds and does the work afterwards, so retries on a timeout are
safe: the `message_id` makes the second one a no-op.
