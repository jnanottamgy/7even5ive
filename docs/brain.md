# The brain: algorithms first, LLM as fallback

## 1. Deadline extraction cascade

Each stage hands on only what it could not settle.

| Stage | What runs | Cost |
|---|---|---|
| 0. Structured source | Google Classroom coursework already has `dueDate`; use it directly | Free |
| 1. Rules | Date parser anchored to the message's **sent time** (so "next Friday" is right even if read days later); Indian day-month order; patterns such as "due by", "on or before", "submit before", "EOD" = 11:59 pm | Free |
| 2. Subject | Exact name → cached alias → course-code pattern → mention scan → fuzzy match | Free |
| 3. Jev | Intent classification with calibrated confidence, if API access arrives in time | Very cheap |
| 4. LLM | Claude on Bedrock fills only the fields still missing | Paid, rare |
| 5. Ask | Low confidence → a notification asks the student | Free |

A confidence score decides the outcome: ≥ 0.9 acts alone, 0.6–0.9 calls the LLM, < 0.6 asks.
Thresholds are tuned on a set of sample professor emails and class-group messages.

**What the LLM resolves is cached**, so the same phrasing never needs the LLM twice.

## 2. Deduplication

The same assignment often arrives three times (email, Classroom, WhatsApp forward).

- Files: SHA-256 of the bytes.
- Deadlines: key of (subject, normalised title, due date ± 1 day). A match merges sources into one
  deadline instead of creating three.

## 3. Week planner

Google OR-Tools CP-SAT.

- **Variables:** a start slot for each study block (30-minute grid over the week).
- **Hard constraints:** no overlap with classes (timetable), exams, existing Calendar events, the
  sleep window, placement tests; each deadline's blocks finish before it is due.
- **Soft constraints (objective):** urgency (time to deadline) × weightage, weaker subjects (marks)
  get more time, no more than N hours of study per day.

The output is clash-free by construction. The LLM is used only to write the one-line summary
("3 sessions for DBMS before Friday's assignment").

## 4. Bunk meter

Pure arithmetic, per subject, using the college's minimum attendance (configurable).

- Can skip: `floor(attended / minimum − held)`
- Must attend: `ceil((minimum × held − attended) / (1 − minimum))`

With the timetable, the projection runs to the end of the semester, not just today.

## 5. Change detection (triggers)

The portal is synced on app open and once each morning. Each sync stores a hash of the result;
a changed hash (new marks, attendance moved) fires an event. No polling every few minutes, so the
portal sees one student's normal traffic.

## 6. Morning briefing

Built from a fixed template filled with the day's data: classes, deadlines, attendance warnings,
plans waiting for approval. No LLM, so nothing can be invented. ElevenLabs voices it.
