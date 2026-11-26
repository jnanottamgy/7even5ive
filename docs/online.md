# The online server: the app with no laptop

One web service runs everything the phone app needs at one HTTPS address
([`core/seventy5/cloud.py`](../core/seventy5/cloud.py)):

| Path | Served by |
|---|---|
| `/api/*`, `/bot/*` | 7even5ive core (cards, approvals, tools, `/api/health`, the bot webhook, Google's sign-in return, the call outcome webhook) |
| `/v1/*` | PortMax's phone API (portal settings, `runner.js`, page upload) |
| `/mcp` | MCP over HTTP for the student's own Claude Code or Codex (`Authorization: Bearer <token>`) |
| `/oauth/*`, `/.well-known/oauth-*` | how those apps sign in as the student ([`mcp.md`](mcp.md)) |
| `/dev` | the core's development page |
| everything else | the mock college portal the app's WebView logs in to |

PortMax accepts portal pages only from the service's own address: `PUBLIC_URL` (or Render's
`RENDER_EXTERNAL_URL`) when set, else the scheme and host each request arrives at.

**Where the data lives.** With a Supabase `DATABASE_URL` (see [`supabase.md`](supabase.md)),
everything lives in that Postgres database: real accounts (sign up with an email code, username,
profile), their cards, college mail and portal answers, and the shared demo student, whose
morning is refreshed once a day. Without it, SQLite inside the container, reseeded with the demo
morning on every start, and the app offers only the demo. The production plan (Lambda, SQS,
Supabase, AgentCore) is [`deploy.md`](deploy.md).

## Serverless on AWS: Lambda + API Gateway (recommended, about 30 minutes, no command line)

The team's architecture is serverless, so this is the main way to put 7even5ive online.
[`deploy/aws/7even5ive-serverless.yaml`](../deploy/aws/7even5ive-serverless.yaml) puts one HTTPS
address (an API Gateway HTTP API) in front of **two Lambda functions running the same code**
(`core/seventy5/lambda_demo.py`, routed as above): no server to keep running, nothing billed
while idle.

- **ApiFunction** answers `/api`, `/bot`, `/v1`, `/demo`, `/mcp` and `/oauth`, and runs the
  once-a-minute tick. It scales out to as many instances as requests need, so two requests never
  wait for (or are refused because of) each other: its data is in Supabase.
  `ApiOnOneInstance` = `true` keeps it to one instance, only for a stack without Supabase, whose
  data then lives in that instance's `/tmp`.
- **DemoFunction** answers everything else: the demo's mock college portal, which keeps its
  logins in memory, so it is kept to one instance (`PinToOneInstance`, default `true`).

**Supabase must be in the stack's region.** Each request makes several database round trips; at
150 ms a trip (another continent) a first start took over 90 s, past Lambda's limit, and every
request seconds. [`core/template.yaml`](../core/template.yaml) and `core/seventy5/aws.py` are an
earlier plan ([`deploy.md`](deploy.md)), not this deployment.

1. **Get the code zip.** GitHub → **Actions** → **Lambda demo** → the newest green run on the
   branch → **Artifacts** → `7even5ive-lambda-zip`. Unzip the download **once**: inside is
   `7even5ive-lambda.zip`. Keep that file zipped; it is what Lambda runs.
2. **Check the Lambda quota.** AWS console (the stack's region) → **Service Quotas** →
   **AWS services** → **AWS Lambda** → **Concurrent executions**. Keeping the mock portal to one
   instance reserves one, and AWS always keeps 100 unreserved, so this must be **at least 101**
   (102 with `ApiOnOneInstance`). If it is lower, **Request increase** to 1000 (free) and wait
   for the approval, or deploy with `PinToOneInstance` = `false`: everything works, except that
   the demo portal's login may fail now and then.
3. **Upload the zip to S3**, in the region you deploy to: **S3** → **Create bucket** (any unique
   name, e.g. `7even5ive-mumbai-<your initials>`) → open it → **Upload** → `7even5ive-lambda.zip`.
4. **Create the stack.** **CloudFormation** → **Create stack** → **With new resources** →
   **Upload a template file** → `deploy/aws/7even5ive-serverless.yaml` → **Next**. Stack name
   e.g. `sevenfiveserverless`; **CodeBucket** = the bucket's name → **Next** → **Next** → tick
   **I acknowledge that AWS CloudFormation might create IAM resources** → **Submit**.
5. When it says **CREATE_COMPLETE** (a minute or two), open **Outputs** → **HealthCheck**. The
   first call takes a few seconds, then it answers `{"service":"7even5ive","version":1}`.
6. Put **AppUrl** in `android/gradle.properties` as `sevenfive.defaultServer`; GitHub builds
   the APK.
7. Once the app works on it, **delete the EC2 stack** below, if you made one: it is the
   always-on server this replaces.

### Keys, restarts, the background tick, and older stacks

- **Keys** live in Parameter Store under `/7even5ive-demo/` (the `SettingsPath` parameter), as
  SecureStrings in the stack's region; each function reads them when it starts. The full list
  and how to get each: [`keys.md`](keys.md). Without one, its feature runs on a stand-in. If
  Parameter Store can't be read at all (a permission, throttling), the start fails and the log
  names the kind of error: the function never quietly runs as the offline demo.
- **After adding or changing a key**, make both functions start fresh: **Lambda** → each
  function (`…-ApiFunction-…` and `…-DemoFunction-…`) → **Configuration** → **Environment
  variables** → **Edit** → **Add environment variable** `RELOAD` (or change its value) = the
  current date and time → **Save**. A save that changes nothing may not restart anything.
- **Background jobs**: Lambda has no always-on process, so `TickRule` (EventBridge) invokes
  ApiFunction once a minute with `{"seventy5": "tick"}`. It fires due reminders and urgent calls,
  checks college mail at 1 PM and 9 PM and syncs Classroom; each job starts only what fits in
  the time Lambda has left. A tick that fails is not retried: the next comes a minute later, and
  every job is safe to run again. `TickEnabled` = `false` turns it off.
- **Outputs**: besides `AppUrl` and `HealthCheck`, the stack prints `McpUrl` (for Claude Code and
  Codex: [`mcp.md`](mcp.md)), `GoogleRedirectUri` (paste into the Google OAuth client),
  `CallWebhookUrl` (ElevenLabs' post-call webhook) and `BotWebhookUrl` (the WhatsApp bot's
  `SEVENTY5_WEBHOOK_URL`).
- **A stack made from an older template must be updated to this one**: **CloudFormation** → the
  stack → **Update** → **Replace current template** → upload `deploy/aws/7even5ive-serverless.yaml`
  → keep the parameters (set `CodeKey` to the new zip's name, below) → tick the IAM
  acknowledgement → **Submit**. Before 26 Nov's template nothing read Parameter Store and no tick
  fired; until this one, everything ran on one pinned function, which answers HTTP 500 whenever
  two requests overlap. The address (`AppUrl`) does not change.

**Update the code:** upload the new zip to the bucket **under a new name** (e.g.
`7even5ive-lambda-2026-11-27.zip`), then **CloudFormation** → the stack → **Update** → **Use
current template** → set **CodeKey** to that name → **Next** → **Next** → **Submit**: both
functions get it. (A new file under the old name changes nothing: CloudFormation sees the same
parameters.)
**Look inside:** **CloudWatch** → **Log groups** → `/aws/lambda/<stack>-ApiFunction-…` (the app
and the tick) or `…-DemoFunction-…` (the mock portal). One JSON line per event, ids and counts
only; the start prints `integrations (live / stand-in):`. **Cost:** Lambda, API Gateway and S3
at this traffic sit within the free credits; nothing runs while nobody uses it.
**Test it locally first** (what was done before shipping it): `core/build_lambda_zip.py`, then
the zip in AWS's Lambda base image with the filesystem read-only except `/tmp`, reached through
[`deploy/aws/local_api_gateway.py`](../deploy/aws/local_api_gateway.py); and
[`deploy/aws/lambda_smoke.py`](../deploy/aws/lambda_smoke.py), which CI runs on every change.

**Approvals in the online demo:** the server starts with none waiting (they last 15 minutes).
Ask your AI to add a deadline to the calendar, or call
`POST <AppUrl>/api/tools/add_to_calendar` with `{"args":{"item_id":1}}`, and the card appears.

## Or one always-on server: EC2 + CloudFront (about 15 minutes, no command line)

[`deploy/aws/7even5ive-demo.yaml`](../deploy/aws/7even5ive-demo.yaml) is one CloudFormation
stack: an **EC2** server (Amazon Linux 2023, fixed **Elastic IP**) that builds this public
repository with Docker and runs it, behind **CloudFront** for HTTPS. No SSH key: the console's
Session Manager opens a shell if needed.

1. Download the template: open it on GitHub → **Download raw file**.
2. AWS console → region **Asia Pacific (Mumbai)** (top right) → **CloudFormation** →
   **Create stack** → **With new resources** → **Upload a template file** → choose it → **Next**.
3. Stack name `7even5ive-demo`. Leave the parameters as they are → **Next** → **Next**.
4. Tick **I acknowledge that AWS CloudFormation might create IAM resources** → **Submit**.
5. Wait for **CREATE_COMPLETE** (5–15 minutes; CloudFront is the slow part). Open the
   **Outputs** tab: `AppUrl` is the address, `HealthCheck` the check.
6. Open `HealthCheck`. The server builds the image after the stack finishes, so allow another
   ~5–10 minutes until it answers `{"service":"7even5ive","version":1}`.
7. Put `AppUrl` in `android/gradle.properties` as `sevenfive.defaultServer`.

**Update to the latest code:** EC2 → Instances → `7even5ive-demo` → **Reboot**. Every start
pulls the branch, rebuilds and runs it (a few minutes).
**Look inside:** EC2 → the instance → **Connect** → **Session Manager** →
`sudo journalctl -u sevenfive -f`.
**Cost:** an always-on t3.small, its public IPv4 address and CloudFront's free tier: roughly
US$20 a month at the time of writing (a t3.micro roughly halves the server part). Check
current prices; new accounts' free credits cover it. **Delete the stack** after the event and
everything it made goes with it.

## Or on Render (free, about 5 minutes)

1. Sign in at <https://render.com> with GitHub, and allow it to see this repository.
2. **New → Blueprint** → choose this repository → **Apply**. [`render.yaml`](../render.yaml)
   creates one free web service in Singapore from the [`Dockerfile`](../Dockerfile).
3. Wait for **Live** (the first build takes a few minutes). Open
   `https://<your-service>.onrender.com/api/health`: it should say `{"service":"7even5ive",…}`.
4. Put that address in `android/gradle.properties` as `sevenfive.defaultServer`. Every APK
   built after that opens straight onto the online server, with no setup on the phone.
5. Keep it awake: the free plan sleeps after 15 idle minutes and takes up to a minute to wake.
   In GitHub: Settings → Secrets and variables → Actions → **Variables** → New:
   `SEVENFIVE_URL` = the address. [`keep-awake.yml`](../.github/workflows/keep-awake.yml) then
   pings it every 10 minutes. (Render's paid plan never sleeps.)

## Check it

```bash
BASE=https://<your-service>.onrender.com node android/e2e/portal-e2e.js
```

Logs in to the mock portal, runs the fetch plan, uploads the pages and checks the cards, all
through the one address.
