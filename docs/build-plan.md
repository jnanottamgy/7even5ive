# Build plan (hack day, 1–2 Dec, RIT)

## Scope for the 24 hours

| Must work | Stretch | Cut |
|---|---|---|
| Forward on WhatsApp → Claude on Bedrock reads it → code checks → card → Add to Calendar | ElevenLabs urgent call and 7 AM briefing | Week planner (removed) |
| SHELF: forward PDFs → filed by subject; "dbms unit 3 notes" → the file | | Instagram, Telegram |
| MCP connector: Claude Code or Claude Desktop asks "what's due this week?" through AgentCore Gateway | ElevenLabs Scribe for voice notes | iOS app (Android only) |
| Control: injected forward blocked by the interceptor; approval token breaks when one character changes | PortMax generating the portal tools (pipeline built; the model step needs one live run) | Class-rep features (not a feature) |
| Mock portal + read-only portal tools → attendance warning with bunk math (built ahead in `portmax/`: `get_attendance_plan`) | Jev intent classifier, if its picks match Claude's on our evals | Reading deadlines out of PDFs |
| Web app: Today, cards, approvals, activity log | | |
| Android app: the student logs in to the portal inside it, and it keeps the login alive (decisions 19, 20, 28) | | |
| College mail filter: placements, internships and exam notices as cards, checked at 1 PM and 9 PM (built ahead in `mailfilter/`, decision 36) | | |

**Rule:** if a flow isn't working by its end hour, cut it and move on. Two flows that work beat
three that half-work.

## Owners (proposed, confirm on the day)

| Person | Owns |
|---|---|
| Kartik | Understanding (Bedrock + checks), SHELF integration, WhatsApp Cloud API |
| Jnanottam | Web app, AgentCore Gateway + Cedar + interceptor, the MCP connector demo |
| Zaid | Mock portal and portal tools, PortMax, ElevenLabs (call, briefing, Scribe), demo data |

**Open:** who builds the Android app, and whether it also takes over the web app's screens; who
owns the mail filter.

## Hour by hour

| Hours | Goal | Done means |
|---|---|---|
| 0–4 | Skeleton | Supabase schema up, gateway serving one read tool, web app shows Today |
| 4–10 | Forward → card | A forwarded message becomes a checked card in under 15 s; Add puts it in Calendar |
| 10–14 | SHELF + MCP connector | Files filed and found; Claude Code answers from 7even5ive through the gateway |
| 14–18 | Control + attendance | Injection blocked and logged; token tamper fails; bunk-math warning from the mock portal |
| 18–21 | Voice + mail | Mail filter live on a demo account; ElevenLabs call and briefing |
| 21–22 | Polish | |
| 22–24 | Freeze | Backup video recorded, demo rehearsed twice, no new code |

## Before hack day (if the organisers allow preparation)

- AWS account with Bedrock (India region) access and AgentCore enabled; credits applied for
- Google Cloud project, OAuth in testing mode, demo accounts added as test users; Gmail API
  enabled and a Desktop OAuth client for `mailfilter connect`
- WhatsApp Cloud API test number
- Mock portal with a made-up student (built: `portmax mock serve`)
- PortMax (mock portal, the five tools, bunk math, the forge pipeline) and the mail filter are
  built ahead of the day; declare them if wHACKiest's rules ask about earlier work
- 20–30 real (anonymised) class-group messages and mails as an eval set, including Jev comparisons
