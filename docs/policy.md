# Policy engine

The LLM never decides what is allowed. It can only **propose** an action. Code checks every
proposal against this policy before anything happens.

That is what makes the agent safe against prompt injection: an email that says "ignore your rules"
can change what the model proposes, but not what the policy permits.

## The three levels

| Level | Test | Behaviour |
|---|---|---|
| `alone` | Only the student will ever see the result, and it can be undone | Runs immediately, logged, Undo available |
| `ask` | Someone else could see it, or it writes to an outside service | Parked as an approval; runs only after a tap |
| `never` | It cannot be undone, or it acts on the college's or someone else's behalf | Refused; the refusal is logged |

## Actions

| Action | Level | Notes |
|---|---|---|
| `save_deadline` (SHELF) | alone | Undo deletes it |
| `attendance_warning` | alone | Notification only |
| `voice_note_to_deadline` | alone | Same as save_deadline, source = voice note |
| `morning_briefing` | alone | Read-only summary |
| `add_calendar_event` | ask | Writes to an outside service |
| `propose_week_plan` | ask | Approving writes several Calendar events at once |
| `draft_email` | ask | Drafted only; the student sends it themselves |
| `reschedule_event` | ask | |
| `send_email` / `send_message` | never | The student always presses send |
| `submit_form` / `submit_assignment` | never | |
| `write_portal` | never | The portal MCP server exposes read-only tools only |
| `payment` | never | |
| `delete_*` | never | Deleting is done by the student in the app |

## Rules the engine always applies

1. **Unknown action → `never`.** A new action must be added to this table deliberately.
2. **An approval is re-checked when it is tapped.** A plan approved after its slot has passed is
   refused, not executed.
3. **Text from sources is data, never instructions.** Email bodies, WhatsApp messages and portal
   pages are passed to the model as quoted content.
4. **Every decision is logged**: action, level, outcome, source, and how it was extracted
   (rules or LLM). The live counter is computed from this log.
