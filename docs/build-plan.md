# Build plan (hack day, 1–2 Dec, RIT)

## Scope for the 24 hours

| Must work | Stretch | Cut |
|---|---|---|
| Forward on WhatsApp → Claude on Bedrock reads it → code checks → card → Add to Calendar | College mail filter (read-only Gmail, demo account) | Week planner (removed) |
| SHELF: forward PDFs → filed by subject; "dbms unit 3 notes" → the file | ElevenLabs urgent call and 7 AM briefing | Instagram, Telegram |
| MCP connector: Claude Code or Claude Desktop asks "what's due this week?" through AgentCore Gateway | ElevenLabs Scribe for voice notes | Native Android app |
| Control: injected forward blocked by the interceptor; approval token breaks when one character changes | PortMax generating the portal tools | Class-rep features (not a feature) |
| Mock portal + read-only portal tools → attendance warning with bunk math | Jev intent classifier, if its picks match Claude's on our evals | Reading deadlines out of PDFs |
| Web app: Today, cards, approvals, activity log | | |

**Rule:** if a flow isn't working by its end hour, cut it and move on. Two flows that work beat
three that half-work.

## Owners (proposed, confirm on the day)

| Person | Owns |
|---|---|
| Kartik | Understanding (Bedrock + checks), SHELF integration, WhatsApp Cloud API |
| Jnanottam | Web app, AgentCore Gateway + Cedar + interceptor, the MCP connector demo |
| Zaid | Mock portal and portal tools, PortMax, ElevenLabs (call, briefing, Scribe), demo data |

## Hour by hour

| Hours | Goal | Done means |
|---|---|---|
| 0–4 | Skeleton | Supabase schema up, gateway serving one read tool, web app shows Today |
| 4–10 | Forward → card | A forwarded message becomes a checked card in under 15 s; Add puts it in Calendar |
| 10–14 | SHELF + MCP connector | Files filed and found; Claude Code answers from 7even5ive through the gateway |
| 14–18 | Control + attendance | Injection blocked and logged; token tamper fails; bunk-math warning from the mock portal |
| 18–21 | Voice | ElevenLabs call and briefing (stretch: mail filter) |
| 21–22 | Polish | |
| 22–24 | Freeze | Backup video recorded, demo rehearsed twice, no new code |

## Before hack day (if the organisers allow preparation)

- AWS account with Bedrock (India region) access and AgentCore enabled; credits applied for
- Google Cloud project, OAuth in testing mode, demo accounts added as test users
- WhatsApp Cloud API test number
- Mock portal with a made-up student
- 20–30 real (anonymised) class-group messages and mails as an eval set, including Jev comparisons
