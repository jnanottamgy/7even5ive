# WhatsApp bot → 75: event format

The bot pushes every message a student sends it to 75. 75 never polls the bot.

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
  "message_id": "wamid.HBgM...",      // WhatsApp's id; 75 dedupes on it
  "text": "DBMS Assignment 3 due Fri 11:59 pm",
  "attachment": "DBMS_Unit3_notes.pdf", // optional: file name only
  "group": "CSE 3B Announcements"      // optional: where it was forwarded from
}
```

## Signature

```
signature = hex( HMAC_SHA256( BOT_WEBHOOK_SECRET, f"{timestamp}." + raw_body_bytes ) )
```

- Sign the **exact bytes** you send. Re-serialising the JSON changes them.
- 75 rejects a timestamp more than 300 s away from its clock, so a captured request
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
| 200 `{"ok": true}` | number is not a 75 student | nothing; 75 stores no row |
| 401 | bad or stale signature | check the secret and clock |

75 answers within milliseconds and does the work afterwards, so retries on a timeout are
safe: the `message_id` makes the second one a no-op.
