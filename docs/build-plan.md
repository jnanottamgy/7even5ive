# Build plan

## Scope for the 24 hours

| Must work | Stretch | Cut (future scope) |
|---|---|---|
| Flow 1: email → deadline → Calendar | Bunk meter and attendance warning | Native Android app and home-screen widget |
| Flow 2: week plan → Approve → Calendar | ElevenLabs voice notes and briefing | Placement eligibility |
| Flow 3: prompt injection blocked | Jev pre-filter | Revision quiz |
| Policy engine + activity log + live counter | Portal Forge generating the portal tools | Real portal login on stage |
| portal-mcp (hand-written, mock portal), Gmail, Calendar | WhatsApp forwards via SHELF | |
| Phone web app: Today, Approvals, Activity, push | Claude Desktop MCP demo | |

**Rule:** if a flow isn't working by its end hour, cut it and move on. Two flows that work beat
three that half-work.

## Owners

| Person | Owns |
|---|---|
| Kartik | Brain: extraction cascade, planner, policy engine, Gmail/Calendar wiring |
| Jnanottam | Phone web app: notifications, Today, Approvals, Activity log |
| Zaid | Mock portal, portal-mcp, Portal Forge, demo data, ElevenLabs features |

Portal Forge is a stretch goal: the hand-written portal-mcp is built first, and Forge replaces it
only if its tools pass verification by hour 14.

## Hour by hour

| Hours | Goal | Done means |
|---|---|---|
| 0–4 | Skeleton | FastAPI up, portal-mcp answering, app shows Today |
| 4–10 | Flow 1 | A sent email produces a notification in under 15 s; Add puts it in Calendar |
| 10–16 | Flow 2 | Solver builds a clash-free plan; Approve writes it to Calendar |
| 16–20 | Flow 3 + policy | Injection email blocked; log and live counter visible |
| 20–22 | Polish | Voice features if time |
| 22–24 | Freeze | Backup video recorded, demo rehearsed twice, no new code |

## Before hack day (if the organisers allow preparation)

- Google Cloud project, OAuth in testing mode, demo accounts added as test users
- Mock portal with a made-up student
- 20–30 sample professor emails and class-group messages to tune the extraction rules
- Phone web app showing one push notification on an Android phone
