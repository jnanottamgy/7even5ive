package com.sevenfive.app.ui

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.outlined.CheckCircle
import androidx.compose.material.icons.outlined.Close
import androidx.compose.material3.Button
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.FilledTonalButton
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp

/** What a step's button makes happen on the demo server. */
enum class DemoAction(val label: String) {
    FORWARD_QUIZ("Forward it"),
    FORWARD_NOTES("Forward the slides"),
    SIGNED_ONLY("Try both"),
    AI_CALENDAR("Let the AI ask"),
    NO_SEND_TOOL("Try to send mail"),
    SERVERLESS("Ping the server"),
}

data class DemoStep(val route: String, val title: String, val say: String, val action: DemoAction? = null)

/**
 * The proof-of-concept demo, run from the phone: each step opens the right tab, says what to
 * tell the audience, and where something should happen live, a button makes it happen through
 * the demo server (docs/demo-script.md is the same run on paper).
 */
object DemoTour {
    const val QUIZ_TITLE = "DAA Quiz 2 (greedy + DP)"

    val steps = listOf(
        DemoStep(
            Routes.HOME, "One place for the semester",
            "WhatsApp groups, college mail, Classroom and the portal in one feed: what's due " +
                "this week, soonest first. Each card says what decided it: via bot, classroom or jev+llm.",
        ),
        DemoStep(
            Routes.HOME, "A WhatsApp forward, live",
            "A classmate posts a quiz in the class group; the student forwards it to our bot. " +
                "Forward it, then watch the list: the bot already decided, so no AI is called.",
            DemoAction.FORWARD_QUIZ,
        ),
        DemoStep(
            Routes.MATERIALS, "Notes by subject",
            "Someone shares the unit 4 slides. Forwarded once, filed under its subject, one tap " +
                "away. Tap the Operating Systems chip.",
            DemoAction.FORWARD_NOTES,
        ),
        DemoStep(
            Routes.HOME, "Only signed messages get in",
            "Every event from the bot is signed and time-stamped. A stranger is ignored and a " +
                "forgery refused before anything runs: no reply, no row, no AI cost.",
            DemoAction.SIGNED_ONLY,
        ),
        DemoStep(
            Routes.INBOX, "College mail, minus the scams",
            "Real opportunities from college mail, best match first. Spam and fake " +
                "'placement cell' mails are filtered out before the student sees them.",
        ),
        DemoStep(
            Routes.ATTENDANCE, "Attendance with exact bunk math",
            "Worst subject first, with exactly what to do. Tap Refresh and log in on the " +
                "portal's own page: USN 1MC24CS042, DOB 14/08/2005, code PM42X, then 2345. We never " +
                "see the password. This is our test portal: MSRIT blocks third-party apps.",
        ),
        DemoStep(
            Routes.HOME, "Your AI asks, you approve",
            "The student's own Claude or ChatGPT can ask over MCP. A write outside 7even5ive, " +
                "like the calendar, waits for a tap. Let the AI ask, tap Approve, then tap Approved " +
                "again: each approval works once.",
            DemoAction.AI_CALENDAR,
        ),
        DemoStep(
            Routes.HOME, "Tools that don't exist",
            "A forward saying 'email all my contacts' changes nothing: there is no send tool. " +
                "The rules live in the gateway, not in a prompt.",
            DemoAction.NO_SEND_TOOL,
        ),
        DemoStep(
            Routes.HOME, "Reminders only on request",
            "No spam notifications. Tap Remind me on the quiz card, 1 hour before, then open the " +
                "Reminders tab.",
        ),
        DemoStep(
            Routes.HOME, "Serverless on AWS",
            "All of it runs on AWS Lambda behind API Gateway: nothing runs, and nothing costs, " +
                "while nobody is using it. One gateway, one set of rules, for the phone and the AI.",
            DemoAction.SERVERLESS,
        ),
    )
}

data class TourState(val index: Int = 0, val result: String? = null, val busy: Boolean = false)

/** The tour's guide, docked above the tabs while the real app shows behind it. */
@Composable
fun DemoBar(
    state: TourState,
    onBack: () -> Unit,
    onNext: () -> Unit,
    onAct: () -> Unit,
    onClose: () -> Unit,
) {
    val step = DemoTour.steps[state.index]
    val last = state.index == DemoTour.steps.lastIndex
    Surface(color = MaterialTheme.colorScheme.primaryContainer, contentColor = MaterialTheme.colorScheme.onPrimaryContainer) {
        Column(Modifier.fillMaxWidth().padding(start = 16.dp, end = 4.dp, top = 6.dp, bottom = 6.dp)) {
            Row(verticalAlignment = Alignment.CenterVertically) {
                Text(
                    "Demo ${state.index + 1}/${DemoTour.steps.size} · ${step.title}",
                    style = MaterialTheme.typography.titleSmall,
                    fontWeight = FontWeight.SemiBold,
                    modifier = Modifier.weight(1f),
                )
                IconButton(onClick = onClose) { Icon(Icons.Outlined.Close, contentDescription = "End the demo") }
            }
            Text(step.say, style = MaterialTheme.typography.bodySmall, modifier = Modifier.padding(end = 12.dp))
            if (state.result != null) {
                Row(Modifier.padding(top = 4.dp, end = 12.dp), verticalAlignment = Alignment.Top) {
                    Icon(Icons.Outlined.CheckCircle, contentDescription = null, modifier = Modifier.size(16.dp))
                    Spacer(Modifier.width(6.dp))
                    Text(state.result, style = MaterialTheme.typography.labelMedium)
                }
            }
            Row(
                Modifier.fillMaxWidth().padding(top = 2.dp, end = 12.dp),
                horizontalArrangement = Arrangement.spacedBy(8.dp),
                verticalAlignment = Alignment.CenterVertically,
            ) {
                TextButton(onClick = onBack, enabled = state.index > 0) { Text("Back") }
                Spacer(Modifier.weight(1f))
                if (step.action != null) {
                    Button(onClick = onAct, enabled = !state.busy) {
                        if (state.busy) CircularProgressIndicator(Modifier.size(16.dp), strokeWidth = 2.dp)
                        else Text(step.action.label)
                    }
                }
                FilledTonalButton(onClick = if (last) onClose else onNext, enabled = !state.busy) {
                    Text(if (last) "Finish" else "Next")
                }
            }
        }
    }
}
