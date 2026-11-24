# YouTube upload: 7even5ive (Round 1 video)

**Title**
7even5ive: Your Semester, on Autopilot | wHACKiest 2026 · Track 1: Make MCP Matter

**Thumbnail:** `brand/7even5ive_youtube_thumbnail.png` (1280×720)

**Description** (paste as is)

7even5ive is an MCP server that centralises a student's college life (WhatsApp, college mail, Google Classroom and the college portal) and organises the chaos into academic data: deadlines, notes, attendance and placement mail. Forward a message on WhatsApp and Claude on Amazon Bedrock reads it first, while code checks every answer against your real data. SHELF, the WhatsApp library we built for ourselves, files every PDF you forward by subject and hands back the one you ask for in seconds. And because it's an MCP server, you can plug it into Claude Code, Codex, Cursor or any MCP client and ask about your semester.

How it is built
• Amazon Bedrock AgentCore Gateway is the one door for every MCP tool call, from our workers, the voice agent or your own AI. Cedar policies deny by default, a Lambda interceptor checks where every value came from, and anything someone else would see needs your tap, which mints a one-time token signed over the exact action.
• Serverless on AWS: WhatsApp Cloud API webhooks into SQS (with a dead-letter queue), Lambda workers, EventBridge for the 7 AM briefing, and Claude on Amazon Bedrock (India). Gmail is read-only.
• ElevenLabs: Agents for the urgent voice call, Scribe for voice notes in Kannada, Hindi and English, and text-to-speech for the morning briefing.
• Supabase (Postgres with row-level security, Realtime and Auth, Mumbai region).
• Portal Forge learns a college portal once, writes an OpenAPI spec, and the gateway turns it into tools. Built on the open-source reverse-api-engineer.

Team: Jnanottam GY · Kartik · Mohammed Zaid
Code: https://github.com/jnanottamgy/7even5ive

0:00 75%: the line that decides your exams
0:18 Four apps, zero connection
0:31 The night before an exam, and the placement mail nobody opens
0:53 Track 1: Make MCP Matter. Meet 7even5ive, the MCP server
1:22 A WhatsApp forward becomes a deadline (Claude on Bedrock, checked by code)
1:55 SHELF, our notes library, and college mail filtered
2:22 When it's urgent, it calls you (ElevenLabs)
3:03 Control: one door for every MCP call (AgentCore Gateway)
3:54 Serverless on AWS
4:24 Portal Forge

**Settings:** Visibility **Unlisted** or Public (whatever Devnovate asks for), "No, it's not made for kids", category Science & Technology.

**Music note:** the main cut uses the "Flashing Lights" instrumental you supplied. YouTube's Content ID will very likely claim it. Upload it as Unlisted first and open YouTube Studio → Content → the video's *Restrictions* column after a few minutes:
- "Copyright claim" with no block → fine, the video still plays for judges.
- "Blocked" (in any country, especially India) → upload `7even5ive_royalty_free_music.mp4` instead. It is the same cut with an original music bed.
