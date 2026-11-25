# The online server: the app with no laptop

One web service runs everything the phone app needs at one HTTPS address
([`core/seventy5/cloud.py`](../core/seventy5/cloud.py)):

| Path | Served by |
|---|---|
| `/api/*`, `/bot/*` | 7even5ive core (cards, approvals, tools, `/api/health`, the bot webhook) |
| `/v1/*` | PortMax's phone API (portal settings, `runner.js`, page upload) |
| `/dev` | the core's development page |
| everything else | the mock college portal the app's WebView logs in to |

PortMax accepts portal pages only from the service's own address (`RENDER_EXTERNAL_URL` on
Render, or `PUBLIC_URL`). State is SQLite inside the container, reseeded with the demo morning
on every start; there is no real student data. This is the prototype's demo server. The
production plan (Lambda, SQS, Supabase, AgentCore) is [`deploy.md`](deploy.md).

## Put it online (Render, free, about 5 minutes)

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
