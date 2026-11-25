# The online server: the app with no laptop

One web service runs everything the phone app needs at one HTTPS address
([`core/seventy5/cloud.py`](../core/seventy5/cloud.py)):

| Path | Served by |
|---|---|
| `/api/*`, `/bot/*` | 7even5ive core (cards, approvals, tools, `/api/health`, the bot webhook) |
| `/v1/*` | PortMax's phone API (portal settings, `runner.js`, page upload) |
| `/dev` | the core's development page |
| everything else | the mock college portal the app's WebView logs in to |

PortMax accepts portal pages only from the service's own address: `PUBLIC_URL` (or Render's
`RENDER_EXTERNAL_URL`) when set, else the scheme and host each request arrives at. State is SQLite inside the container, reseeded with the demo morning
on every start; there is no real student data. This is the prototype's demo server. The
production plan (Lambda, SQS, Supabase, AgentCore) is [`deploy.md`](deploy.md).

## Put it online on AWS (about 15 minutes, no command line)

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
