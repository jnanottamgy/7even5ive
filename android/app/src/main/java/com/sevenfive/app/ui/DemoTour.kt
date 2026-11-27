package com.sevenfive.app.ui

import androidx.compose.animation.AnimatedContent
import androidx.compose.animation.AnimatedVisibility
import androidx.compose.animation.core.Spring
import androidx.compose.animation.core.animateFloatAsState
import androidx.compose.animation.core.spring
import androidx.compose.animation.expandVertically
import androidx.compose.animation.fadeIn
import androidx.compose.animation.fadeOut
import androidx.compose.animation.shrinkVertically
import androidx.compose.animation.slideInHorizontally
import androidx.compose.animation.slideOutHorizontally
import androidx.compose.animation.togetherWith
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.outlined.ArrowBack
import androidx.compose.material.icons.outlined.CheckCircle
import androidx.compose.material.icons.outlined.Close
import androidx.compose.material3.Icon
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import com.sevenfive.app.ui.components.GlassPill
import com.sevenfive.app.ui.components.PrimaryPill
import com.sevenfive.app.ui.components.SlimBar
import com.sevenfive.app.ui.theme.LocalAppColors
import com.sevenfive.app.ui.theme.Motion
import com.sevenfive.app.ui.theme.frosted
import com.sevenfive.app.ui.theme.glassSurface
import com.sevenfive.app.ui.theme.pressable
import dev.chrisbanes.haze.HazeState

/** What a step's button makes happen on the demo server. */
enum class DemoAction(val label: String) {
    FORWARD_QUIZ("Forward it"),
    FORWARD_NOTES("Forward the slides"),
    SIGNED_ONLY("Try both"),
    AI_CALENDAR("Let the AI ask"),
    NO_SEND_TOOL("Try to send mail"),
    SERVERLESS("Ping the server"),
    CHECK_MAIL("Check now"),
    PLAY_BRIEFING("Play it"),
    TEST_CALL("Ring me now"),
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
            Routes.HOME, "Your day, read aloud",
            "The morning briefing: today's classes, what's due, attendance at risk and new mail, " +
                "written by code from the student's own data and read by ElevenLabs. It lives in the " +
                "app; it is never a notification.",
            DemoAction.PLAY_BRIEFING,
        ),
        DemoStep(
            Routes.INBOX, "College mail, read for you",
            "Placements, internships and exam notices, judged by Claude and checked by code: every " +
                "date, quote and form link must be in the mail itself. Spam and fake 'placement cell' " +
                "mails never get here. Check now: a new internship arrives.",
            DemoAction.CHECK_MAIL,
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
            Routes.HOME, "Ask your semester",
            "Tap Ask your semester and try “Can I skip Friday?”. The answer comes only from the " +
                "student's data, through the same gateway an AI uses over MCP, and says which tools it called.",
        ),
        DemoStep(
            Routes.ATTENDANCE, "Plan a day off",
            "Tap Planner, pick a day, and tap a class to attend or skip it: every subject's ring " +
                "moves to where it would end up. Grades and Timetable sit beside it.",
        ),
        DemoStep(
            Routes.HOME, "Every AI request, logged",
            "Scroll to AI activity: each request through the gateway, what ran, what waited for " +
                "a tap and what was refused. The proof the rules hold.",
        ),
        DemoStep(
            Routes.HOME, "Reminders only on request",
            "No spam notifications. Tap Remind me on the quiz card, 1 hour before: it arrives as a " +
                "notification then. Open the Reminders tab.",
        ),
        DemoStep(
            Routes.REMINDERS, "The urgent call",
            "For what really matters: Call me, after a one-time consent. ElevenLabs rings shortly " +
                "before it's due, at most twice a day and never at night; a missed call becomes one " +
                "notification. Turn calls on in Settings, then ring now.",
            DemoAction.TEST_CALL,
        ),
        DemoStep(
            Routes.HOME, "Just ask",
            "Tap the microphone at the top and ask \"what's due this week?\" or \"can I skip DBMS " +
                "tomorrow?\" ElevenLabs listens and answers; every fact comes from the same gateway " +
                "as a tap, and adding to the calendar still waits for Approve.",
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

/**
 * The tour's guide: a frosted card floating above the tabs while the real app shows behind it.
 * Moving between steps slides the text the way you went.
 */
@Composable
fun DemoBar(
    state: TourState,
    haze: HazeState,
    onBack: () -> Unit,
    onNext: () -> Unit,
    onAct: () -> Unit,
    onClose: () -> Unit,
    modifier: Modifier = Modifier,
) {
    val step = DemoTour.steps[state.index]
    val last = state.index == DemoTour.steps.lastIndex
    val app = LocalAppColors.current
    val progress by animateFloatAsState(
        (state.index + 1f) / DemoTour.steps.size,
        spring(stiffness = Spring.StiffnessLow),
        label = "tour progress",
    )
    val shape = RoundedCornerShape(26.dp)
    Column(
        modifier
            .fillMaxWidth()
            .frosted(haze, shape)
            .padding(start = 16.dp, end = 10.dp, top = 12.dp, bottom = 12.dp),
    ) {
        Row(verticalAlignment = Alignment.CenterVertically) {
            Text(
                "DEMO  ${state.index + 1} OF ${DemoTour.steps.size}",
                style = MaterialTheme.typography.labelSmall,
                color = MaterialTheme.colorScheme.primary,
                modifier = Modifier.weight(1f),
            )
            Box(
                Modifier
                    .size(28.dp)
                    .pressable(onClick = onClose)
                    .glassSurface(shape = CircleShape, strong = true),
                contentAlignment = Alignment.Center,
            ) {
                Icon(Icons.Outlined.Close, contentDescription = "End the demo", tint = app.secondaryLabel, modifier = Modifier.size(16.dp))
            }
        }
        SlimBar(progress, MaterialTheme.colorScheme.primary, Modifier.padding(top = 6.dp, end = 6.dp, bottom = 8.dp))
        AnimatedContent(
            targetState = state.index,
            transitionSpec = {
                val forward = targetState > initialState
                (slideInHorizontally(Motion.screen) { if (forward) it / 3 else -it / 3 } + fadeIn(Motion.fade)) togetherWith
                    (slideOutHorizontally(Motion.screen) { if (forward) -it / 3 else it / 3 } + fadeOut(Motion.fade))
            },
            label = "tour step",
        ) { index ->
            val shown = DemoTour.steps[index]
            Column(Modifier.fillMaxWidth().padding(end = 6.dp)) {
                Text(shown.title, style = MaterialTheme.typography.titleMedium)
                Text(
                    shown.say,
                    style = MaterialTheme.typography.bodySmall,
                    color = app.secondaryLabel,
                    modifier = Modifier.padding(top = 2.dp),
                )
            }
        }
        AnimatedVisibility(
            visible = state.result != null,
            enter = fadeIn() + expandVertically(),
            exit = fadeOut() + shrinkVertically(),
        ) {
            Row(Modifier.padding(top = 8.dp, end = 6.dp), verticalAlignment = Alignment.Top) {
                Icon(
                    Icons.Outlined.CheckCircle,
                    contentDescription = null,
                    tint = MaterialTheme.colorScheme.tertiary,
                    modifier = Modifier.size(16.dp),
                )
                Spacer(Modifier.width(6.dp))
                Text(state.result.orEmpty(), style = MaterialTheme.typography.labelMedium)
            }
        }
        Row(
            Modifier.fillMaxWidth().padding(top = 10.dp, end = 4.dp),
            horizontalArrangement = Arrangement.spacedBy(8.dp),
            verticalAlignment = Alignment.CenterVertically,
        ) {
            GlassPill(
                "Back",
                onClick = onBack,
                enabled = state.index > 0 && !state.busy,
                icon = Icons.AutoMirrored.Outlined.ArrowBack,
                tint = MaterialTheme.colorScheme.onSurface,
            )
            Spacer(Modifier.weight(1f))
            if (step.action != null) {
                GlassPill(step.action.label, onClick = onAct, busy = state.busy)
            }
            PrimaryPill(if (last) "Finish" else "Next", onClick = if (last) onClose else onNext, enabled = !state.busy)
        }
    }
}
