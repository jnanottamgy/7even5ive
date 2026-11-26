# The urgent call (ElevenLabs)

For the one thing a student must not miss: shortly before it is due, their phone rings and a
short voice reminds them. Code: [`core/seventy5/calls.py`](../core/seventy5/calls.py); tests:
[`core/tests/test_calls.py`](../core/tests/test_calls.py); decision P4 in [`plan.md`](../plan.md).

## What the student does

1. On a dated card, **Remind me** → **Call me 2 hours before**.
2. The first time, a consent screen says exactly what happens (below) and nothing is turned on
   until they tap **Turn on and call me**. Settings → **Urgent call** has the same switch,
   the quiet hours, **Test call now** and the last few calls.
3. Turning calls off keeps their call reminders, as notifications.

## The rules (checked in code, in this order)

1. Consent on, with its time recorded, and a real number on file. The demo's invented number
   is never dialled; `DEMO_STUDENT_PHONE` is the phone that rings for the demo student.
2. Not in quiet hours: 22:00–08:00 India time by default, the student's own if they set them.
3. At most 2 calls a day (`CALL_MAX_PER_DAY`) and one per item, ever.
4. The item is still open: not done, not deleted, not already past.

Anything refused becomes **one notification** saying why ("we didn't call because it's within
your quiet hours"). Never silence, never two messages.

## The call itself

- **First sentence**, filled in by code: "Hi Demo, it's 7even5ive. Your DBMS lab record for
  Database Management Systems is due today at 5:00 PM, about 2 hours from now."
- **After that** the agent answers only from those facts and what else is due today. Titles are
  cleaned (no braces, markup or control characters; 80 characters) and read as names.
- **Its only tools are ElevenLabs' own**: hang up, and hang up on a voicemail without leaving a
  message. It cannot look anything up, change, send or mark anything.
- **90 seconds** at most (`CALL_MAX_SECONDS`), on Claude Haiku 5.5 run by ElevenLabs
  (`ELEVENLABS_AGENT_LLM`).
- **The outcome** comes back on ElevenLabs' signed post-call webhook: answered, missed or
  voicemail. Missed or voicemail sends one notification, never a second call. An unsigned or
  stale webhook is refused.

## Setting it up

1. **ElevenLabs key** in Parameter Store (`ELEVENLABS_API_KEY`), see [`keys.md`](keys.md).
2. **A phone number in ElevenLabs** → **ElevenAgents** → **Phone numbers** → **Import**:
   - *Twilio* (the demo; a foreign caller id): a Twilio number and its account SID and token.
     On a Twilio trial, first verify the student's phone in Twilio (trial accounts only call
     verified numbers). `CALL_PROVIDER=twilio`.
   - *Exotel* (an Indian caller id, for real students): imported natively by ElevenLabs.
     `CALL_PROVIDER=exotel`. (Any other SIP trunk, e.g. Plivo: `CALL_PROVIDER=sip`.)
   Copy the imported number's id into `ELEVENLABS_PHONE_NUMBER_ID`.
3. **The agent**, as code: on a laptop with the key in `core/.env`,
   `cd core && .venv/bin/python -m seventy5.calls setup-agent` → put the printed id in
   `ELEVENLABS_AGENT_ID`. Re-run after changing the prompt (it updates in place).
   `show-agent` prints the exact configuration that is sent.
4. **The outcome webhook**: ElevenLabs → **ElevenAgents** → **Settings** → **Post-call
   webhook** → URL = the stack's `CallWebhookUrl` output, authentication HMAC → copy the secret
   into `ELEVENLABS_WEBHOOK_SECRET`.
5. **The phone to ring**: `DEMO_STUDENT_PHONE=+91XXXXXXXXXX`.
6. In the app: Settings → Urgent call → turn on → **Test call now** rings at once about the
   soonest thing due, under every rule above.

The server log's startup report shows `live  ElevenLabs urgent call: via twilio` once 1–3 are
in place; until then calls are recorded and listed in Settings, not rung.

## On the serverless demo

Lambda has no always-on process, so an EventBridge rule runs the reminders job once a minute
(`TickRule` in [`7even5ive-serverless.yaml`](../deploy/aws/7even5ive-serverless.yaml)); a call
reminder fires within a minute of its time.
