# The brain: model reads first, code checks

The model proposes; code decides what is true and what is allowed. That split, which SHELF already
uses, is what keeps answers accurate without trusting the model blindly.

## 1. Understanding a message (LLM-first)

| Step | What runs |
|---|---|
| 1. Read | Claude on Amazon Bedrock reads the forwarded message (and up to a few images) and proposes a structured result: intent (deadline, note, notice, question, …), subject, due date and time, task. |
| 2. Check | Code validates each field against the student's real data: the **subject must exist** in their subject list; the **date must be real**, resolved from the message's sent time (so "Friday" is right even if forwarded days later; "EOD" means 11:59 PM); the deadline must **not duplicate** one already saved. |
| 3. Ask | If a check fails, or something is missing, 7even5ive asks one short question instead of guessing. |
| 4. Act | Only a checked result is written, shown as a card, and logged with undo. |

**Jev** (being tested): a fast intent classifier that might handle the simplest messages ("thanks",
"ok", greetings) before the model. It is not part of the build until its picks are compared with
Claude's on our eval set.

## 2. SHELF: filing and finding files

- A forwarded PDF or image is filed by **caption, filename and subject** into notes, question
  papers or circulars.
- **Duplicates** are caught by the SHA-256 of the file's bytes, so the same PDF forwarded twice is
  stored once.
- "dbms unit 3 notes" returns the file. If nothing matches, it says so and asks which subject.
- **PDF contents are not parsed for deadlines.**

## 3. College mail filter

Read-only Gmail. Each new mail is classified; only **placements, internships and exam-cell
notices** are kept, with their deadline and form link, in SHELF's Opportunities. Newsletters,
webinars and promotions are ignored. The student fills forms themselves.

## 4. Attendance and bunk math

Pure arithmetic per subject, at the college's minimum (75% by default):

- Can still skip: `floor(attended / minimum − held)`
- Must attend to get back: `ceil((minimum × held − attended) / (1 − minimum))`

Example: 33 of 45 classes (73%) → attend the next 3 to reach 75%.
With the timetable, the projection runs to the end of the semester.

## 5. Change detection

The portal is synced on app open and once each morning; a changed hash of the result (new marks,
attendance moved) fires an event. No polling every few minutes, so the portal sees one student's
normal traffic.

## 6. Morning briefing

A fixed template filled with the day's data: classes, deadlines, attendance risk, opportunities.
No model writes it, so nothing can be invented; ElevenLabs voices it.

## Removed from the earlier plan

Rules-first extraction cascade and confidence thresholds · the "handled by rules %" counter ·
the OR-Tools week planner · any class-rep feature. See [`decisions.md`](decisions.md).
