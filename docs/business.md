# Business model

Pricing is shown in the deck, not in the film. Numbers are to be validated in the RIT pilot.

## Tiers

| Tier | What the student or college gets | Price |
|---|---|---|
| Basic | Deadlines from WhatsApp forwards, Classroom and college mail; attendance warnings with bunk math; approvals and the activity log | Free |
| Plus | Urgent voice calls, the 7 AM voice briefing, voice notes to text (ElevenLabs) | ₹79–99 a month, or per semester (to validate) |
| Pro: bring your own AI | The 7even5ive MCP connector: use Claude Code, Codex, Cursor, Claude, ChatGPT or any MCP client with your college data, safely, through our gateway | Higher tier (to validate; see open items) |
| Colleges (B2B) | Official read-only data feed instead of portal scraping; anonymised class-level attendance-risk view | Per student per year (to validate) |
| Partners | Opt-in, labelled offers matched to events, never to profiles: placement prep, exam coaching, laptops | Commission per signup |

**We never sell or share student data. Partners pay for placement, not for profiles.**

Open: which tier the MCP connector belongs to (see [`decisions.md`](decisions.md)).

## Market

- About 4.3 crore higher-education students in India (AISHE 2021-22).
- Year-1 target: 5 Bengaluru colleges, RIT first.
- Colleges are the second customer.

## Go-to-market

- Pilot with our own class first.
- Student ambassadors (people, not a product feature), paid commission on paid referrals.
- Placement season and exam weeks as the hook: the two moments the pain peaks.
- If several colleges share one portal vendor, one PortMax spec covers all of them.

## Key costs

| Cost | Note |
|---|---|
| Model (Bedrock) | Measured per student on stage and in the pilot, never estimated |
| ElevenLabs | Voice is a paid-tier feature |
| AWS | Serverless: nothing runs while idle; apply for student and startup credits |
| Meta (WhatsApp) | Inbound forwards are free; business-initiated alerts cost roughly ₹0.12–0.15 each, so routine alerts go to the app |
| Google security assessment | Required for production read access to Gmail |
| Ambassador commissions | Paid only on conversion |

## Unit economics

```
Cost per active student / month = model calls × cost per call + voice minutes × rate
                                  + WhatsApp alerts × rate + infra share
Contribution per paid student   = price − cost per active student − payment fees
Free students covered per paid  = contribution per paid student ÷ cost per free student
```

## Growth

| Phase | Milestone |
|---|---|
| 0–6 months | RIT pilot, Free + Plus, measured unit economics |
| 6–18 months | 5–10 Bengaluru colleges, first college deal, partner revenue |
| 18+ months | MCP connector at scale, developer API for portal connectors, more cities |
