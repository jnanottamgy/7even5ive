# Control: enforced at the gateway

The model never decides what is allowed. It can only **propose** a tool call. Every call, from our
Lambda workers, the ElevenLabs voice agent or the student's own AI through the MCP connector,
passes through **AgentCore Gateway**, where code decides.

A forwarded message that says "ignore your instructions" can change what the model proposes, but
not what the gateway permits.

## Three levels

| Level | Test | Behaviour |
|---|---|---|
| **For you** | Only the student sees the result, and it can be undone | Runs, logged, undo available |
| **Your tap** | Someone else would see it, or it writes to an outside service | Parked; runs only after a tap that mints a one-time token |
| **Never** | It can't be undone, or acts on the college's or someone else's behalf | The tool does not exist |

## Tools

| Tool | Level | Notes |
|---|---|---|
| Read deadlines, attendance, timetable, marks, library, opportunities | For you | All the MCP connector exposes by default |
| Save a deadline · file a document · set a reminder | For you | Undo deletes it |
| `Calendar___insert_event` | Your tap | One tap on the card |
| `WhatsApp___send_document` to someone else (share a file from your library) | Your tap | Token bound to that file and that number. *Example action, to confirm.* |
| Messages to the student themselves (alerts, briefing, the call) | For you | |
| Submit a form or assignment · pay · delete · write to the portal · send mail | Never | No such tools exist; Gmail is read-only and portal tools are read-only |

## Cedar, deny by default

```cedar
// nothing runs unless a rule permits it
permit (
  principal,
  action == AgentCore::Action::"WhatsApp___send_document",
  resource
) when { context.input has approval_token };
```

## The interceptor (Lambda)

1. **Provenance:** every value is tagged with where it came from. A recipient, link or amount that
   came from a forwarded message, mail body or web page is **untrusted** and can't be used as the
   target of an action.
2. **One-time tokens:** a tap mints an HMAC token over the SHA-256 of the exact arguments. It is
   single use and expires. Change one character after approval and the signature breaks.
3. **Re-check on tap:** an approval is re-validated when used; stale or changed actions are refused.

## Always

- **Unknown tool → denied.** New tools are added to the policy deliberately.
- **Source text is data, never instructions.** Messages, mail and portal pages reach the model as
  quoted content.
- **Every decision is logged:** tool, level, outcome, source.
- **Per-student scoping** in Neon Postgres: every query is filtered to one student, so a student only ever sees their own rows.
