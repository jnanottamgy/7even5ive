# Business model

**Rules-first is what makes a free tier affordable.** Most deadlines are extracted by plain code,
so a free student costs very little to serve. Paid students cover free ones.

## Tiers

| Tier | What the student or college gets | Price |
|---|---|---|
| Basic | Deadlines from Gmail and Classroom, attendance warnings, approvals, activity log | Free |
| Plus | Unlimited week planner, voice briefings, voice notes → deadlines, SHELF (WhatsApp) included | ₹79–99 a month, or per semester (to validate) |
| Pro: bring your own agent | A personal MCP endpoint behind our gateway: use Claude, ChatGPT or any MCP client with your college data, safely | Higher tier (to validate) |
| Colleges (B2B) | Official read-only data feed, anonymised class-level attendance-risk view, announcements that reach students | Per student per year (to validate) |
| Partners | Opt-in, labelled offers matched to events, never to profiles: placement prep, exam coaching, student banking, laptops | Commission per signup |

**We never sell or share student data. Partners pay for placement, not for profiles.**

## Market

- About 4.3 crore higher-education students in India (AISHE 2021-22).
- Year-1 target: 5 Bengaluru colleges, RIT first.
- Colleges are the second customer.

## Go-to-market

- RIT pilot after the hackathon.
- Class-rep ambassadors, paid commission on paid referrals.
- Club events and placement season as the hook.
- SHELF's existing WhatsApp reach.
- If several colleges share one portal vendor, one connector covers all of them.

## Key costs

| Cost | Note |
|---|---|
| LLM (Bedrock) | Kept low by rules-first; measured, not estimated |
| ElevenLabs | Voice is a paid-tier feature |
| AWS | Usage-based; apply for student and startup credits |
| Meta (WhatsApp) | Per-message fees, SHELF features only |
| Google security assessment | Required yearly for production Gmail access |
| Ambassador commissions | Paid only on conversion |

## Unit economics

```
Cost per active student / month = LLM calls × cost per call + voice minutes × rate + infra share
Contribution per paid student   = price − cost per active student − payment fees
Free students covered per paid  = contribution per paid student ÷ cost per free student
```

N, the number of free students each paid student covers, comes from measured costs after the
benchmark. It is never estimated.

## Growth

| Phase | Milestone |
|---|---|
| 0–6 months | RIT pilot, Free + Plus, measured unit economics |
| 6–18 months | 5–10 Bengaluru colleges, first college deal, partner revenue |
| 18+ months | Pro tier, developer API for portal connectors, more cities |
