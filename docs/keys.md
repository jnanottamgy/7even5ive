# Keys and accounts: the handover checklist

Everything runs without any of these: each missing key leaves a stand-in, and the server's log
says which (`integrations (live / stand-in):`, printed at every start; CloudWatch on Lambda).
Add them in any order; each one switches its feature on at the next cold start.

## Where they go

**The serverless stack (Lambda):** AWS console, **in the stack's own region** (Mumbai,
`ap-south-1`, for a new stack; the first demo stack is in Sydney, `ap-southeast-2`) → **Systems
Manager** → **Parameter Store** → **Create parameter** → name `/7even5ive-demo/<NAME>`, type
**SecureString**, the value → **Create**. Each function reads every parameter under that path
when it starts ([`lambda_demo.py`](../core/seventy5/lambda_demo.py)). To pick them up at once:
**Lambda** → each of the two functions → **Configuration** → **Environment variables** →
**Edit** → add or change a variable `RELOAD` = the current date and time → **Save** (a save that
changes nothing may not restart anything).

**A laptop or Render:** the same names in `core/.env` (git ignores it) or the host's settings.

Never commit a key, never put one in the template, the APK or a chat.

## The checklist

| # | Name(s) | What it unlocks | Without it |
|---|---|---|---|
| 1 | `APPROVAL_SECRET` | Signs one-time approval tokens (Approve on the phone) | A public development secret: on a deployed server approvals are refused |
| 2 | `TOKEN_ENCRYPTION_KEY` | Encrypts stored Google refresh tokens | A public development key: on a deployed server Connect Google is refused |
| 3 | `BOT_WEBHOOK_SECRET` | The WhatsApp bot's signed events reach 7even5ive; students can link WhatsApp | A public development secret: only the demo student's events are accepted, and WhatsApp can't be linked |
| 4 | `LIBRARY_URL`, `LIBRARY_SERVICE_TOKEN` | Files shows each linked student's library from the bot; their deadlines are pulled in when they link | Real accounts: "the bot isn't connected"; the demo always shows its invented library |
| 6 | `ANTHROPIC_API_KEY` *or* `BEDROCK_MODEL_ID` | Claude for the cascade and for judging real college mail | Recorded demo answers; real mail can't be read |
| 7 | `JEV_API_KEY` | Jev's cheap first look (type, subject, spam) | Everything goes to Claude |
| 8 | `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET` | Connect Google: real Gmail, Calendar, Classroom | Demo mailbox; the calendar stays in 7even5ive |
| 9 | `ELEVENLABS_API_KEY` | Briefing voice; needed by 10 and 11 | The phone reads the briefing itself |
| 10 | `ELEVENLABS_ASSISTANT_AGENT_ID` | The in-app voice assistant | The app says voice isn't set up |
| 11 | `ELEVENLABS_AGENT_ID`, `ELEVENLABS_PHONE_NUMBER_ID`, `CALL_PROVIDER`, `ELEVENLABS_WEBHOOK_SECRET`, `DEMO_STUDENT_PHONE` | The urgent call rings a real phone, and its outcome comes back | Calls are recorded, not rung |
| 12 | `FCM_SERVICE_ACCOUNT_JSON` (server) + four `sevenfive.fcm*` values (app) | Reminders and missed-call notices arrive at once, even on an idle phone | A pull every 15 minutes that Android delays while the phone is idle: a reminder can come hours late |
| 13 | `DATABASE_URL` (Supabase's transaction pooler) | Data that lasts: accounts, cards, mail, portal answers | SQLite in `/tmp`: everything starts over at each cold start |
| 14 | `SUPABASE_URL`, `SUPABASE_PUBLISHABLE_KEY`, `SUPABASE_SECRET_KEY` (+ `SUPABASE_JWT_SECRET` only for a legacy-secret project) | Real accounts: sign up with an email code, username, profile, delete account | Only the shared demo account |
| 15 | `BOT_WHATSAPP_NUMBER` | The app's **Link WhatsApp** opens WhatsApp with the code typed | The app shows the code to send |
| — | `ELEVENLABS_VOICE_ID`, `ELEVENLABS_API`, `BEDROCK_REGION`, `MAILFILTER_MODEL`, `LLM_MODEL`, `CALL_QUIET_START`, `CALL_QUIET_END`, `CALL_MAX_PER_DAY`, `CALL_LEAD_MINUTES`, `MAIL_CHECK_TIMES`, `PUBLIC_URL` | Tuning (optional) | Sensible defaults ([`config.py`](../core/seventy5/config.py)) |

The stack's **Outputs** tab lists the addresses the steps below ask for: `AppUrl`, `McpUrl`,
`GoogleRedirectUri`, `CallWebhookUrl` and `BotWebhookUrl`.

## How to get each one

**1, 2. Secrets of our own.** Any long random string each, e.g. from
`python -c "import secrets; print(secrets.token_urlsafe(48))"`. Changing
`TOKEN_ENCRYPTION_KEY` later means students connect Google again.

**3, 4. The WhatsApp bot (SHELF).** First the bot needs its side of the link, which is not on
GitHub yet: Kartik's branch `seventy5-link` of the bot (`Kartikkatwe/academic-assistant`), pushed,
merged and deployed ([`library-link.md`](library-link.md), "What the bot must do"). Then make two
random strings, A and B. On the bot (its `.env`, then redeploy): `SEVENTY5_SERVICE_TOKEN=A`,
`SEVENTY5_WEBHOOK_SECRET=B`, `SEVENTY5_WEBHOOK_URL=<BotWebhookUrl>`. Here:
`LIBRARY_URL=<the bot's public base URL>`, `LIBRARY_SERVICE_TOKEN=A`, `BOT_WEBHOOK_SECRET=B`.
The demo student's number is invented and never a real person's (its token is public); to show
a live WhatsApp forward, use your own account with WhatsApp linked.

**6. Claude.** Either an Anthropic API key (simplest), or Bedrock.
- **Anthropic API:** [platform.claude.com](https://platform.claude.com) → **Billing** (credits
  or a card) → **API keys** → **Create key**: linked to a service account if your organization
  has one (a personal key stops working when its owner leaves), **Workspace: Default** (a key
  not scoped to one workspace needs a header this server doesn't send), **Expiration: never**
  (it can't be changed later) → copy it (`sk-ant-api…`). Put it in `ANTHROPIC_API_KEY`. Both the cascade and the mail judge then use
  Claude Haiku 5.5, model id `claude-haiku-5-5` (the default `LLM_MODEL`).
- **Bedrock:** Bedrock (the stack's region) → **Model catalog** → **Claude Haiku 5.5** → fill
  in Anthropic's use-case form if asked → as an AWS admin, send one message in the playground
  (the first use makes the account's Marketplace subscription, which the function's role can't
  do itself). Then `BEDROCK_MODEL_ID=anthropic.claude-haiku-5-5` (and `BEDROCK_REGION` if Bedrock
  is in another region than the stack). The cascade and the mail judge both call Bedrock's
  Messages API with that id; the SDK signs those requests for the service `bedrock-mantle`, which
  the stack grants (`bedrock-mantle:*`). `MAILFILTER_MODEL` only if the judge should differ.

**7. Jev.** An OpenRouter key with access to `typesafe/jev-1.14`.

**8. Google.** Google Cloud console → a project → **APIs & Services**:
1. **Library**: enable the Gmail API, Google Calendar API and Google Classroom API.
2. **OAuth consent screen**: External, **Testing**; add each demo student's Google address
   as a test user (up to 100; a Testing sign-in lasts 7 days). Scopes: `gmail.readonly`,
   `calendar.events`, `classroom.courses.readonly`, `classroom.coursework.me.readonly`,
   `openid`, `email`. Real students need Google's verification (decision 54).
3. **Credentials** → **Create credentials** → **OAuth client ID** → **Web application** →
   **Authorized redirect URIs**: the stack's `GoogleRedirectUri` output exactly.
4. Copy the client ID and secret into `GOOGLE_CLIENT_ID` and `GOOGLE_CLIENT_SECRET`.
A college Google Workspace may block outside apps; then the fallback is a Gmail forwarding
filter (decision 55).

**9. ElevenLabs.** [elevenlabs.io](https://elevenlabs.io) → **Developers** → **API keys** →
create one with at least **Text to Speech** and **ElevenAgents: Write** (the set-up commands
create agents) → `ELEVENLABS_API_KEY`. Optionally pick a voice: its id goes in
`ELEVENLABS_VOICE_ID`, both in Parameter Store (the briefing) and in `core/.env` when you run
the two set-up commands below (the agents get their voice then).

**10. The voice assistant.** On a laptop with **Python 3.12 or newer** (portmax and the mail
filter need it), with the key in `core/.env`:
`cd core && .venv/bin/python -m seventy5.voice setup-assistant`. It creates the agent and its
twelve client tools and prints the id for `ELEVENLABS_ASSISTANT_AGENT_ID`: put it in Parameter
Store **and** in `core/.env`, so running it again (after changing the prompt) updates that agent
instead of making a second one. The agent records no voice and keeps conversations 30 days.
[`voice.md`](voice.md).

**11. The urgent call.** [`call.md`](call.md) has the full steps. In short: import a phone
number into ElevenLabs (Twilio for the demo, or Exotel for an Indian caller id), copy its id
into `ELEVENLABS_PHONE_NUMBER_ID`, set `CALL_PROVIDER` (`twilio` or `exotel`), run
`.venv/bin/python -m seventy5.calls setup-agent` for `ELEVENLABS_AGENT_ID` (keep it in
`core/.env` too), add a post-call webhook in ElevenLabs pointing at `CallWebhookUrl` (with call
initiation failures, if it asks which events) and put its secret in `ELEVENLABS_WEBHOOK_SECRET`.
`DEMO_STUDENT_PHONE` (`+91XXXXXXXXXX`) is the phone the demo account's calls ring; a real student's
calls ring the number they linked. Leave it unset when nobody is presenting (anyone trying the
demo can ring it, twice a day at most; unset it, then restart, as above).

**12. Firebase (needed for on-time reminders).** Firebase console → add a project → add an
Android app with package `com.sevenfive.app`. From **Project settings** → **General** → the app:
the App ID, the Web API key (in `google-services.json` it is `current_key`), the Project ID and
the Project number go in `android/gradle.properties` as
`sevenfive.fcmAppId`, `sevenfive.fcmApiKey`, `sevenfive.fcmProjectId`, `sevenfive.fcmSenderId`
(not secrets); rebuild the APK. **Service accounts** → **Generate new private key**: the whole
JSON goes in `FCM_SERVICE_ACCOUNT_JSON` (a SecureString; it fits the 4 KB limit).

**13, 14, 15. Supabase and accounts.** Step by step in [`supabase.md`](supabase.md): the
project in the **same region as the stack**, the transaction pooler's URI as `DATABASE_URL`, the
three keys, the two email templates with the code, and your own SMTP before real students.

## The app

`android/gradle.properties`: `sevenfive.defaultServer` = `AppUrl` (already the current
stack's), the four optional Firebase values, and nothing secret. The Supabase project's address
and publishable key are not in the APK: the app asks the server (`/api/auth/config`), so adding
Supabase needs no new APK. The APK is rebuilt by GitHub Actions on every push that touches
`android/` (release `apk-latest`).

## The student's own AI (MCP)

Nothing to set up: the connector signs students in with their 7even5ive account. On a laptop,
`claude mcp add --transport http --scope user 7even5ive <McpUrl>` (then `/mcp` → Authenticate) or
`codex mcp add 7even5ive --url <McpUrl>`, and sign in in the browser. The app shows the commands
(**Settings** → **Connect Claude Code or Codex**). Apps that can only send a fixed header use a
personal token from the same screen; the demo's public token works as a header for
presentations. Every tool goes through the gateway. Details: [`mcp.md`](mcp.md).
