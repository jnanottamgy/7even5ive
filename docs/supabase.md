# Supabase: the database and real accounts

Two things come from one Supabase project:

- **The database.** Everything the service keeps (the core's cards and accounts, PortMax's portal
  answers, the mail filter's records) moves from SQLite files in Lambda's `/tmp`, which start over
  at every cold start, to one Postgres database that keeps them.
- **Accounts.** Students sign up with their email and a password, confirm it with a 6-digit code
  from their inbox, and choose a username and profile, Instagram style. "Try the demo" still
  opens the shared demo student, with no account.

Without the project nothing breaks: the server says `stand-in` for both in its startup log, keeps
SQLite, and the app offers only the demo. About 20 minutes, no command line.

## 1. Create the project

[supabase.com](https://supabase.com) → **New project**.

- **Region: the same region as the Lambda.** Every request makes several database round trips;
  across regions a first start passes Lambda's time limit. For a stack in Mumbai: **Need a
  specific region?** → **South Asia (Mumbai)** (not "Asia-Pacific", which can mean Singapore).
  The region can't be changed later.
- **Database password:** **Generate a password**, letters and digits only (an `@`, `/` or `%`
  breaks the database URL below), kept in your password manager. It goes into the database URL
  and nowhere else.

## 2. The database → `DATABASE_URL`

Project → **Connect** → **Transaction pooler** → copy the URI and put the database password in
place of the bracketed password placeholder (no brackets). On the Pro plan, turn on **Use IPv4
connection** first (its dedicated pooler is IPv6 only). It looks like
`postgresql://postgres.<ref>:<password>@aws-<n>-<region>.pooler.supabase.com:6543/postgres`.

Parameter Store: `/7even5ive-demo/DATABASE_URL`, **SecureString**.

- Use the **transaction pooler** (port 6543), not the direct connection: Lambda reaches the
  internet over IPv4, and the direct connection is IPv6-only unless the project buys the IPv4
  add-on. The code is built for this pooler (no prepared statements, no pipelining, a connection
  dropped while Lambda was frozen is noticed and replaced); the test suite runs through a
  transaction-mode pooler to prove it.
- PortMax and the mail filter use the same database by themselves (their tables are named
  `portmax_*` and `mail_*`). Don't set `PORTMAX_DATABASE_URL` or `MAILFILTER_DATABASE_URL`.
- At the first start the service creates its tables, turns **row level security** on for every
  one of them and removes the grants Supabase gives its Data API, so the publishable key (which
  ships in apps) can't read a single row. The log says `row level security set on N tables` once.
- The demo student lives in the same database. Its morning is refreshed once a day (not at every
  cold start), and the demo's reset touches only the demo student's rows.

## 3. The keys → `SUPABASE_URL`, `SUPABASE_PUBLISHABLE_KEY`, `SUPABASE_SECRET_KEY`

Project → **Project Settings** → **API Keys**:

| Parameter (SecureString) | Value | Secret? |
|---|---|---|
| `SUPABASE_URL` | the project URL, `https://<ref>.supabase.co` | no |
| `SUPABASE_PUBLISHABLE_KEY` | the **publishable** key, `sb_publishable_…` | no: the app gets it from `/api/auth/config` |
| `SUPABASE_SECRET_KEY` | **Create new secret key**, `sb_secret_…` | **yes**: it bypasses row level security |

The secret key is used for two things only: deleting an account's login, and signing in with a
username (the server looks up the email). Without it, accounts work but **Delete account**
answers "isn't set up on this server yet" and nothing is deleted. Older projects' `anon` and
`service_role` keys work too (`SUPABASE_ANON_KEY`, `SUPABASE_SERVICE_ROLE_KEY`); the new keys
are better.

## 4. How the server checks sessions (usually nothing to do)

**Project Settings** → **JWT Keys**. New projects sign sessions with an asymmetric key
(ES256): the server reads the public key from the project's JWKS address by itself. Nothing to
set.

If the page shows the **legacy JWT secret** in use, either press **Migrate JWT secret**, then
**Rotate keys** (recommended; nobody is signed out), or copy the legacy secret into
`SUPABASE_JWT_SECRET`. With neither, the server asks Supabase to check each new session; that
works, but it is slower and counts against Supabase's limits.

## 5. Authentication settings

**Authentication** → **Sign In / Providers**: **User Signups** → **Confirm email** on; **Email**
→ enabled, **Email OTP Length** 6 (the default; 6 to 10 work).

**Your own email sender, first.** Projects on the Free plan made since June 2026 can't edit the
email templates until the project sends through your own SMTP, and Supabase's default templates
send a link, never the code the app asks for. Supabase's built-in email also reaches only the
members of your Supabase organization, two emails an hour. So: **Authentication** → **Emails** →
**SMTP Settings** → turn on custom SMTP with Resend, Amazon SES, Brevo or ZeptoMail (verify your
sender address with them first). Custom SMTP starts at 30 emails an hour (**Authentication** →
**Rate Limits**).

**Authentication** → **Emails** → **Templates**. The app works with codes, not links, so two
templates must show the code (`{{ .Token }}`). Replace each body with:

**Confirm sign up**, subject `Your 7even5ive code: {{ .Token }}`:

```html
<h2>Welcome to 7even5ive</h2>
<p>Your code is:</p>
<p style="font-size:28px;font-weight:700;letter-spacing:6px">{{ .Token }}</p>
<p>Enter it in the app to finish signing up. If you didn't sign up, ignore this email.</p>
```

**Reset password**, subject `Your 7even5ive password code: {{ .Token }}`:

```html
<h2>Choose a new password</h2>
<p>Your code is:</p>
<p style="font-size:28px;font-weight:700;letter-spacing:6px">{{ .Token }}</p>
<p>Enter it in the app with your new password. If you didn't ask, ignore this email.</p>
```

For a quick demo without SMTP, turning **Confirm email** off also works: sign-up then signs in
at once (password reset still needs email).

**Recommended:** **Authentication** → **Rate Limits** → **IP address forwarding** on. A
username sign-in goes through the server; with forwarding on (and the secret key set) it counts
against the student's own address. With it off, every username sign-in counts against the
server's one address, so a burst of wrong passwords can make username sign-in wait a few
minutes for everyone (the app then says to log in with the email, which goes straight from the
phone to Supabase and is never affected).

## 6. Linking WhatsApp (optional) → `BOT_WHATSAPP_NUMBER`

Needs the bot's real webhook secret (`BOT_WEBHOOK_SECRET`, [`keys.md`](keys.md) step 3): with
the development secret, which is public, anyone could sign a "LINK" message from any number, so
the server refuses to link and accepts only the demo student's events. Then the bot's own
WhatsApp number, `91XXXXXXXXXX`. In the app, **Settings** → **Link WhatsApp**
shows a code (`LINK 75-ABC234`) and opens WhatsApp with it typed. The bot forwards it like any
message; its signed webhook proves which number sent it, and that number becomes the student's.
That number is also the one an urgent call rings. Without the parameter the app still shows the
code to send, without the button.

## 7. Restart and check

1. Lambda → each of the two functions → **Configuration** → **Environment variables** →
   **Edit** → add or change `RELOAD` = the current date and time → **Save**.
2. CloudWatch, at the next start: `live  Database: Supabase Postgres` and
   `live  Accounts (sign up, log in): Supabase Auth, JWKS (ES256/RS256)`.
3. `<AppUrl>/api/auth/config` in a browser: `"enabled": true` with your project URL.
4. In the app: **Sign up** → the code from the email → choose a username → the home screen, empty
   and yours. **Settings** → **Account** shows `@username`. Log out, log in with the username.

## How it fits together

```
phone ──(sign up · code · log in · refresh · reset)──► Supabase Auth   (publishable key)
  │                                                        │ issues the session (JWT, ~1 hour)
  └──(every request, Authorization: Bearer <JWT>)──► 7even5ive ──(checks it: JWKS)──► student
```

- **The phone talks to Supabase itself**, so its own address counts against Supabase's per-address
  limits; through one server, every student would share the server's.
- **The server checks every access token**: signature, expiry (30 seconds of leeway), issuer
  (this project), audience and role `authenticated`, not anonymous. Then the student is found by
  the token's user id. A signed-in user without a profile gets `403 profile_required` everywhere
  but `/api/me`; the app opens the profile setup.
- **The session on the phone** is sealed with a key in the Android Keystore. It is refreshed a
  minute before it ends, and once more if the server says it ended; one refresh at a time
  (Supabase rotates refresh tokens). A refresh Supabase refuses signs the student out; being
  offline never does.
- **Usernames** are unique and lowercase: 3 to 30 letters, numbers, dots or underscores; a few
  are reserved. The database's unique index decides, so two students can't both get one.
- **Claude Code and Codex (MCP).** They sign in as the student with OAuth, in the browser, on
  this same account ([`mcp.md`](mcp.md)): their tokens work for `/mcp` only, never for the app's
  API or the account, and Settings can disconnect each. A personal token (shown once; the server
  keeps only its SHA-256) is there for MCP apps that can only send a fixed header.
- **The demo account** is shared by everyone who taps **Try the demo**, so its token is public.
  It can't connect Google or WhatsApp, get a token, sign in an MCP app, change its profile or be
  deleted, and only it can run the demo tour (at most 3 resets a minute). Its WhatsApp number is
  invented and its Files library is the invented one: it never reaches a real person's library,
  forwards or phone. Its paid voice is capped (voice sessions and new briefing clips per address
  and per day). Its morning is refreshed at 5 AM each day. One thing it can do on purpose: the
  urgent call. With `DEMO_STUDENT_PHONE` set, anyone trying the demo can ring that phone, at most
  `CALL_MAX_PER_DAY` times a day (a demo reset doesn't reset the count); leave it unset when you
  aren't presenting.
- **Delete account** (Settings, typing DELETE) revokes Google, forgets the college mail read,
  removes the portal answers and every row, then the login itself (the secret key). Its session,
  still valid for up to an hour, is turned away from then on. The app then forgets everything on
  the phone: session, cards, the portal login and its storage, notifications.

## When something is wrong

| What you see | Why, and what to do |
|---|---|
| The app: "Accounts aren't set up on this server yet" | `SUPABASE_URL` or `SUPABASE_PUBLISHABLE_KEY` missing; restart after adding |
| The app: "Can't reach 7even5ive" on the login screen | The server address (tap **Server** at the bottom) or the phone's network |
| No email arrives after **Sign up** | No custom SMTP: built-in mail only reaches your Supabase organization, two an hour (step 5); check spam |
| The email has a link, not a code | The templates weren't changed; on a new Free project they can't be until SMTP is on (step 5) |
| "Can't check your sign-in right now" (503) | The JWKS address unreachable, or a legacy-secret project with no `SUPABASE_JWT_SECRET` (step 4) |
| The server never finishes starting, or every request takes seconds | Supabase and the Lambda are in different regions (step 1): it must be the same region |
| Every request fails right after adding `DATABASE_URL` | A password with `@`, `/` or `%` in the URL: use letters and digits only (step 1) |
| **Delete account**: "isn't set up on this server yet" | `SUPABASE_SECRET_KEY` missing; nothing was deleted |
| The startup log says `stand-in  Database` | `DATABASE_URL` missing or not `postgresql://`; the data starts over at each cold start |

Tested here: the whole server suite on SQLite, on Postgres 16, and on Postgres behind PgBouncer
in transaction mode (Supabase's pooler mode), plus the Lambda package started twice against
that pooler. Not tested here: a real Supabase project (no account from this environment), so do
step 7 once the parameters are in.
