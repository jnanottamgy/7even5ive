# YouTube upload: 7even5ive (Round 1 video)

**Title**
7even5ive: Your Semester, on Autopilot | wHACKiest 2026 · Track 1: Make MCP Matter

**Thumbnail:** `brand/7even5ive_youtube_thumbnail.png` (1280×720)

**Description** (paste as is)

7even5ive is a proactive campus agent for Indian college students. You forward it what lands in your WhatsApp class group (or your class rep forwards it once, for the whole section), it reads your college portal and Google Classroom, warns you before your attendance falls under 75%, tells you exactly how many classes you need to attend, and calls you when something is urgent. It always asks before it touches anyone else, so a fake "exam cancelled" forward can never be posted to your class.

How it is built
• Amazon Bedrock AgentCore Gateway is the only door for every MCP tool call. Cedar policies deny by default, a Lambda interceptor checks where every value came from, and each approval mints a one-time token signed over the exact action.
• Serverless on AWS: WhatsApp Cloud API webhooks into SQS (with a dead-letter queue), Lambda workers, EventBridge for the 7 AM briefing, and Claude Haiku on Amazon Bedrock (India), used only when the rules engine is unsure.
• ElevenLabs: Agents for the outbound voice call (connected to the gateway as an MCP client), Scribe for voice notes in Kannada, Hindi and English, and text-to-speech for the morning briefing.
• Supabase (Postgres with row-level security, Realtime and Auth, Mumbai region).
• Portal Forge learns a college portal once, writes an OpenAPI spec, and the gateway turns it into tools. Built on the open-source reverse-api-engineer.

Team: Jnanottam GY · Kartik · Mohammed Zaid
Code: https://github.com/jnanottamgy/campus-copilot

0:00 75%: the line that decides your exams
0:18 Five apps, zero connection
0:33 Meet 7even5ive
0:46 A WhatsApp forward becomes a deadline (rules first, AI only when unsure)
1:23 When it's urgent, it calls you (ElevenLabs)
2:02 Control: fake forwards can't reach your class (AgentCore Gateway)
2:53 Serverless on AWS
3:24 Portal Forge and the live cost counter
3:45 How it sustains itself

**Settings:** Visibility **Unlisted** or Public (whatever Devnovate asks for), "No, it's not made for kids", category Science & Technology.

**Music note:** the main cut uses the "Flashing Lights" instrumental you supplied. YouTube's Content ID will very likely claim it. Upload it as Unlisted first and open YouTube Studio → Content → the video's *Restrictions* column after a few minutes:
- "Copyright claim" with no block → fine, the video still plays for judges.
- "Blocked" (in any country, especially India) → upload `7even5ive_royalty_free_music.mp4` instead. It is the same cut with an original music bed.
