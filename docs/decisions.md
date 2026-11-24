# Decisions

The source of truth when any other document, diagram, PDF or slide disagrees. Newest first.

## 2026-11-24: the direction for Round 1 and hack day

| # | Decision | Why |
|---|---|---|
| 1 | **Name: 7even5ive** (said "Seven Five"). | 75% is the attendance line every Indian student knows. |
| 2 | **It is an MCP server that centralises college life** and organises the chaos into academic data (deadlines, notes, attendance, placement mail). | Track 1 asks for MCP that regular people use every day. "Less magic, more utility." |
| 3 | **It does not make plans.** No week planner, no study blocks, no OR-Tools solver. | Students can't add or move classes; the useful job is organising what already exists. The planner Lambda is replaced by a library Lambda. |
| 4 | **Personal software. No class-rep feature**, no section feed, no "forward once for the whole section". | Each student forwards and owns their own data. (Class reps may still help spread it as people, not as a feature.) |
| 5 | **LLM-first understanding.** Claude on Amazon Bedrock reads every message first; code checks each answer against the student's real data. The rules-first cascade, confidence thresholds and "handled by rules %" counter are dropped. | Accuracy and intent identification matter more than shaving model calls; SHELF's experience is that a model proposing and code gating works. |
| 6 | **Jev is being explored**, not committed: a faster intent classifier for the simplest messages. Mention it only vaguely. | Early access, no measurements yet. |
| 7 | **The bot does not read PDFs for deadlines.** Deadlines come from message text, Classroom and mail. PDFs are stored and filed by caption, filename and subject in SHELF. | Honest about what we can do reliably. |
| 8 | **SHELF is the library (storage area)** inside 7even5ive, not an optional extra. | It is the part we have already built and use as students; the notes hunt is the most felt pain. |
| 9 | **Four sources: WhatsApp, college mail, Google Classroom, college portal.** Instagram is not connected; Telegram is not used. | Instagram has no usable API for this; Telegram was blocked in India in June 2026 over exam leaks. |
| 10 | **College mail is read-only** (Gmail API) and filtered to placements, internships and exam-cell notices. Those show up in the library, the morning briefing and the urgent call. | Placement deadlines are the costliest thing students miss. Read-only keeps the risk low. |
| 11 | **The MCP connector is a headline feature:** students plug 7even5ive into Claude Code, Codex, Cursor, Claude, ChatGPT or any MCP client, through AgentCore Gateway. | It is what makes it an MCP product, not an app with an MCP label. |
| 12 | **One door for every tool call: AgentCore Gateway** with Cedar deny-by-default, a Lambda interceptor that checks where every value came from, and one-time approval tokens signed over the exact action. No submit, pay or delete tools exist. | Prompt injection arrives in forwards; control is enforced in infrastructure, not in a prompt. |
| 13 | **Example of an action others see:** sharing a file from your SHELF with a friend needs your tap (approval token bound to that file and that number). *Proposed in the film; confirm on hack day.* | Ties the control story to the notes problem. |
| 14 | **Pricing stays in the deck, not in the film.** | The film is about the product. |
| 15 | **India-first framing** throughout: WhatsApp, not email; no "email your professor for an extension" or "extra class" actions. | That is not how Indian colleges work. |

### Still open

- Which tier the MCP connector sits in (currently "Pro: bring your own AI" in the deck).
- Whether Jev joins the build, after its picks are compared with Claude's on our eval set.
- Confirm the file-sharing approval example (decision 13) or replace it.
- The deck (`ppt/`) and the root PDFs still show parts of the older plan (rules-first, planner,
  class-rep relay). Update before the online pitch on 26–27 Nov.
