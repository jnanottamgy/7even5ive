package com.sevenfive.app.ui.screens

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.ExperimentalLayoutApi
import androidx.compose.foundation.layout.FlowRow
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.outlined.HelpOutline
import androidx.compose.material.icons.filled.CheckCircle
import androidx.compose.material.icons.filled.NotificationsActive
import androidx.compose.material.icons.filled.PhoneInTalk
import androidx.compose.material.icons.filled.PlayArrow
import androidx.compose.material.icons.filled.Stop
import androidx.compose.material.icons.outlined.Done
import androidx.compose.material.icons.outlined.WbSunny
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material.icons.outlined.CalendarMonth
import androidx.compose.material.icons.outlined.EventAvailable
import androidx.compose.material.icons.outlined.NotificationAdd
import androidx.compose.material.icons.outlined.Schedule
import androidx.compose.material.icons.outlined.AutoAwesome
import androidx.compose.material.icons.outlined.Shield
import androidx.compose.material.icons.automirrored.outlined.KeyboardArrowRight
import androidx.compose.ui.platform.LocalContext
import android.widget.Toast
import com.sevenfive.app.ui.LocalNav
import com.sevenfive.app.ui.Routes
import com.sevenfive.app.util.Opener
import com.sevenfive.app.util.Week
import com.sevenfive.app.ui.theme.pressable
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.DropdownMenu
import androidx.compose.material3.DropdownMenuItem
import androidx.compose.material3.Icon
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.runtime.mutableIntStateOf
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import com.sevenfive.app.data.Approval
import com.sevenfive.app.data.CallSettings
import com.sevenfive.app.data.Cards
import com.sevenfive.app.data.Item
import com.sevenfive.app.data.Reminder
import com.sevenfive.app.ui.AppViewModel
import com.sevenfive.app.ui.BriefingPlayer
import com.sevenfive.app.ui.DoneApproval
import com.sevenfive.app.ui.components.AppCard
import com.sevenfive.app.ui.components.CallConsentDialog
import com.sevenfive.app.ui.components.EmptyState
import com.sevenfive.app.ui.components.GlassPill
import com.sevenfive.app.ui.components.IconTile
import com.sevenfive.app.ui.components.KindChip
import com.sevenfive.app.ui.components.PrimaryPill
import com.sevenfive.app.ui.components.RouteBadge
import com.sevenfive.app.ui.components.ScreenIntro
import com.sevenfive.app.ui.components.SectionHeader
import com.sevenfive.app.ui.components.TabScaffold
import com.sevenfive.app.ui.components.kindColor
import com.sevenfive.app.ui.components.kindStyle
import com.sevenfive.app.ui.theme.LocalAppColors
import com.sevenfive.app.ui.theme.LocalStatusColors
import com.sevenfive.app.ui.theme.Motion
import com.sevenfive.app.ui.theme.glassSurface
import com.sevenfive.app.util.Time
import java.time.Duration
import java.time.Instant

@Composable
fun HomeScreen(vm: AppViewModel, onSettings: () -> Unit) {
    val state by vm.cards.collectAsStateWithLifecycle()
    val busy by vm.busy.collectAsStateWithLifecycle()
    val approved by vm.approved.collectAsStateWithLifecycle()
    val settings by vm.settings.collectAsStateWithLifecycle()
    val cards = state.cards
    // After the cards, one request at a time (AppViewModel.loadHome).
    LaunchedEffect(Unit) { vm.loadHome() }
    val due = cards?.dueThisWeek.orEmpty()
    val name = cards?.student?.name?.substringBefore(' ')?.takeIf { it.isNotBlank() }

    val subtitle = when {
        cards == null -> null
        due.isEmpty() -> "Nothing due in the next 7 days."
        due.size == 1 -> "1 thing due in the next 7 days."
        else -> "${due.size} things due in the next 7 days."
    }

    var segment by rememberSaveable { mutableIntStateOf(0) }
    TabScaffold(if (name != null) "Hi, $name" else "This week", vm, onSettings) { padding ->
        if (cards == null) {
            LoadingOrError(state.loading, padding)
            return@TabScaffold
        }
        // Organised into short segments instead of one long scroll.
        val needs = cards.approvals.size + cards.needsReview.size
        val segments = listOf(
            Segment("Today"),
            Segment("Week", due.size),
            Segment("Needs you", needs),
            Segment("AI"),
        )
        LazyColumn(contentPadding = padding, verticalArrangement = Arrangement.spacedBy(10.dp)) {
            item(key = "segments") { NeoSegments(segments, segment) { segment = it } }
            when (segment) {
                0 -> {
                    // The next thing due, huge, then the day.
                    item(key = "hero") { HomeHero(cards, Modifier.animateItem(placementSpec = Motion.item)) }
                    item(key = "ask") { AskBar(Modifier.animateItem(placementSpec = Motion.item)) }
                    item(key = "briefing") { BriefingCard(vm, Modifier.animateItem(placementSpec = Motion.item)) }
                    item(key = "today") { Today(cards, Modifier.animateItem(placementSpec = Motion.item)) }
                }
                1 -> {
                    item(key = "intro") { ScreenIntro(subtitle) }
                    if (due.isEmpty()) {
                        item(key = "empty") {
                            EmptyState(
                                Icons.Outlined.EventAvailable,
                                "A clear week",
                                "Deadlines and exams from your groups, mail and Classroom show up here.",
                            )
                        }
                    }
                    items(due, key = { "i-${it.id}" }) { item ->
                        val reminder = cards.reminders.firstOrNull { it.itemId == item.id }
                            ?: cards.reminders.firstOrNull { it.itemId == null && it.title == item.title && it.dueAt == item.dueAt }
                        DueCard(
                            item, reminder, "item:${item.id}" in busy, "done:${item.id}" in busy, settings?.calls,
                            Modifier.animateItem(placementSpec = Motion.item),
                            onRemind = { minutes, channel -> vm.remind(item, minutes, channel) },
                            onCallConsent = { minutes -> vm.enableCallsAndRemind(item, minutes) },
                            onDone = { vm.markDone(item) },
                        )
                    }
                }
                2 -> {
                    if (cards.approvals.isEmpty() && approved.isEmpty() && cards.needsReview.isEmpty()) {
                        item(key = "nothing") {
                            EmptyState(Icons.Outlined.Done, "Nothing needs you", "Calendar changes your AI asks for, and messages it couldn't read, wait here for your tap.")
                        }
                    }
                    if (cards.approvals.isNotEmpty() || approved.isNotEmpty()) {
                        item(key = "h-approvals") { SectionHeader("Needs your tap", Modifier.animateItem(placementSpec = Motion.item)) }
                        items(cards.approvals, key = { "a-" + it.token }) { approval ->
                            ApprovalCard(
                                approval, vm.titleFor(approval), approval.token in busy,
                                Modifier.animateItem(placementSpec = Motion.item),
                            ) { vm.approve(approval) }
                        }
                        items(approved, key = { "d-" + it.approval.token }) { done ->
                            DoneApprovalCard(done, done.approval.token in busy, Modifier.animateItem(placementSpec = Motion.item)) {
                                vm.approve(done.approval)
                            }
                        }
                    }
                    if (cards.needsReview.isNotEmpty()) {
                        item(key = "h-review") { SectionHeader("Couldn't read these", Modifier.animateItem(placementSpec = Motion.item)) }
                        items(cards.needsReview, key = { "r-${it.id}" }) { item ->
                            NeedsReviewCard(item, Modifier.animateItem(placementSpec = Motion.item))
                        }
                    }
                }
                else -> {
                    if (cards.audit.isNotEmpty()) {
                        item(key = "ai") { YourAi(cards, Modifier.animateItem(placementSpec = Motion.item)) }
                    } else {
                        item(key = "ai-empty") {
                            EmptyState(Icons.Outlined.Shield, "No AI activity yet", "Every time your AI reads or changes something, it shows here.")
                        }
                    }
                }
            }
        }
    }
}

/** The way into Ask your semester: looks like a search field, opens the conversation. */
@Composable
private fun AskBar(modifier: Modifier = Modifier) {
    val nav = LocalNav.current
    val app = LocalAppColors.current
    Row(
        modifier
            .fillMaxWidth()
            .pressable(scaleTo = 0.98f, haptic = true) { nav(Routes.ASK) }
            .glassSurface(shape = CircleShape, strong = true)
            .padding(horizontal = 16.dp, vertical = 13.dp),
        verticalAlignment = Alignment.CenterVertically,
    ) {
        Icon(Icons.Outlined.AutoAwesome, contentDescription = null, tint = MaterialTheme.colorScheme.primary,
            modifier = Modifier.size(20.dp))
        Spacer(Modifier.width(10.dp))
        Text("Ask your semester… “Can I skip Friday?”", style = MaterialTheme.typography.bodyLarge,
            color = app.secondaryLabel, maxLines = 1, overflow = TextOverflow.Ellipsis)
    }
}

/** Today's remaining classes from the timetable; nothing when the portal has none. */
@Composable
private fun Today(cards: Cards, modifier: Modifier = Modifier) {
    if (!cards.timetable.connected) return
    val nav = LocalNav.current
    val now = java.time.LocalTime.now()
    val left = Week.on(cards.timetable.data, java.time.LocalDate.now().dayOfWeek)
        .filter { s -> Week.time(s.end)?.isAfter(now) ?: true }
    Column(modifier.pressable(scaleTo = 0.985f) { nav(Routes.TIMETABLE) }) {
        SectionHeader("Today", trailing = {
            Text("Timetable", style = MaterialTheme.typography.labelMedium, color = MaterialTheme.colorScheme.primary)
        })
        if (left.isEmpty()) {
            Text(
                "No more classes today.",
                style = MaterialTheme.typography.bodyMedium,
                color = LocalAppColors.current.secondaryLabel,
                modifier = Modifier
                    .fillMaxWidth()
                    .glassSurface(shape = MaterialTheme.shapes.medium)
                    .padding(14.dp),
            )
        } else {
            DayClasses(cards, left.take(3), highlightNow = true)
        }
    }
}

/** What your AI did through the gateway lately, and a way into the full log. */
@Composable
private fun YourAi(cards: Cards, modifier: Modifier = Modifier) {
    val nav = LocalNav.current
    val status = LocalStatusColors.current
    val app = LocalAppColors.current
    val refused = cards.audit.count { it.decision == "deny" }
    val held = cards.audit.count { it.decision == "ask" }
    Row(
        modifier
            .fillMaxWidth()
            .pressable(scaleTo = 0.98f) { nav(Routes.AI_LOG) }
            .glassSurface()
            .padding(16.dp),
        verticalAlignment = Alignment.CenterVertically,
    ) {
        IconTile(Icons.Outlined.Shield, status.safe)
        Spacer(Modifier.width(12.dp))
        Column(Modifier.weight(1f)) {
            Text("AI activity", style = MaterialTheme.typography.titleMedium)
            Text(
                "${cards.audit.size} requests through the gateway · $held held for you · $refused refused",
                style = MaterialTheme.typography.bodySmall,
                color = app.secondaryLabel,
            )
        }
        Icon(Icons.AutoMirrored.Outlined.KeyboardArrowRight, contentDescription = null, tint = app.tertiaryLabel)
    }
}

/** Three numbers worth knowing before scrolling, like a row of iOS widgets. */
@Composable
private fun Glance(cards: Cards, modifier: Modifier = Modifier) {
    val status = LocalStatusColors.current
    val worst = cards.attendance.subjects.minByOrNull { it.percent }
    val soonest = cards.dueThisWeek.mapNotNull { Time.parse(it.dueAt) }.minOrNull()
    Row(modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(10.dp)) {
        GlanceTile(
            value = "${cards.dueThisWeek.size}",
            label = "Due this week",
            color = MaterialTheme.colorScheme.primary,
            modifier = Modifier.weight(1f),
        )
        GlanceTile(
            value = soonest?.let { Time.until(it) } ?: "—",
            label = "Next deadline",
            color = if (soonest != null && soonest.toInstant().isBefore(Instant.now().plus(Duration.ofHours(24))))
                MaterialTheme.colorScheme.error else LocalAppColors.current.material,
            modifier = Modifier.weight(1f),
        )
        GlanceTile(
            value = worst?.let { "${it.percent.toInt()}%" } ?: "—",
            label = worst?.code ?: "Attendance",
            color = worst?.let { status.of(it.status) } ?: LocalAppColors.current.secondaryLabel,
            modifier = Modifier.weight(1f),
        )
    }
}

@Composable
private fun GlanceTile(value: String, label: String, color: Color, modifier: Modifier = Modifier) {
    Column(
        modifier
            .glassSurface(shape = MaterialTheme.shapes.medium)
            .padding(horizontal = 12.dp, vertical = 12.dp),
    ) {
        Text(
            value,
            style = MaterialTheme.typography.headlineSmall,
            fontWeight = FontWeight.Bold,
            color = color,
            maxLines = 1,
            overflow = TextOverflow.Ellipsis,
        )
        Text(
            label,
            style = MaterialTheme.typography.labelMedium,
            color = LocalAppColors.current.secondaryLabel,
            maxLines = 1,
            overflow = TextOverflow.Ellipsis,
        )
    }
}

@Composable
internal fun LoadingOrError(loading: Boolean, padding: PaddingValues) {
    // Neo-minimal: a skeleton of the screen while the first cards arrive, never a spinner.
    if (loading) {
        com.sevenfive.app.ui.components.SkeletonScreen(padding)
        return
    }
    Box(Modifier.fillMaxWidth().padding(padding).padding(top = 56.dp), contentAlignment = Alignment.TopCenter) {
        run {
            EmptyState(
                Icons.AutoMirrored.Outlined.HelpOutline,
                "No cards yet",
                "Check the server in Settings: the online demo needs no laptop.",
            )
        }
    }
}

@Composable
private fun ApprovalCard(approval: Approval, title: String, busy: Boolean, modifier: Modifier = Modifier, onApprove: () -> Unit) {
    val app = LocalAppColors.current
    Row(
        modifier
            .fillMaxWidth()
            .glassSurface(strong = true, tint = MaterialTheme.colorScheme.primary.copy(alpha = 0.08f))
            .padding(16.dp),
        verticalAlignment = Alignment.CenterVertically,
    ) {
        IconTile(Icons.Outlined.CalendarMonth, app.exam)
        Spacer(Modifier.width(12.dp))
        Column(Modifier.weight(1f)) {
            Text(actionLabel(approval.action), style = MaterialTheme.typography.labelMedium, color = app.secondaryLabel)
            Text(title, style = MaterialTheme.typography.titleMedium, maxLines = 2, overflow = TextOverflow.Ellipsis)
            Text("Your AI asked. It only runs if you tap.", style = MaterialTheme.typography.bodySmall, color = app.secondaryLabel)
        }
        Spacer(Modifier.width(8.dp))
        PrimaryPill("Approve", onClick = onApprove, busy = busy)
    }
}

/** Kept after it ran: tapping again shows the gateway's "approval already used". */
@Composable
private fun DoneApprovalCard(done: DoneApproval, busy: Boolean, modifier: Modifier = Modifier, onTapAgain: () -> Unit) {
    val app = LocalAppColors.current
    AppCard(modifier, muted = true) {
        Row(verticalAlignment = Alignment.CenterVertically) {
            IconTile(Icons.Filled.CheckCircle, LocalStatusColors.current.safe)
            Spacer(Modifier.width(12.dp))
            Column(Modifier.weight(1f)) {
                Text("Added to Google Calendar", style = MaterialTheme.typography.labelMedium, color = app.secondaryLabel)
                Text(done.title, style = MaterialTheme.typography.titleMedium, maxLines = 2, overflow = TextOverflow.Ellipsis)
                Text("Each approval works once.", style = MaterialTheme.typography.bodySmall, color = app.secondaryLabel)
            }
            Spacer(Modifier.width(8.dp))
            GlassPill("Approved", onClick = onTapAgain, busy = busy, tint = LocalStatusColors.current.safe)
        }
    }
}

private fun actionLabel(action: String) = when (action) {
    "add_to_calendar" -> "Add to Google Calendar?"
    else -> action.replace('_', ' ').replaceFirstChar { it.uppercase() } + "?"
}

private val reminderChoices = listOf(24 * 60 to "1 day before", 3 * 60 to "3 hours before", 60 to "1 hour before")

/** Today's briefing: a few sentences written by code, read aloud by ElevenLabs or the phone. */
@Composable
private fun BriefingCard(vm: AppViewModel, modifier: Modifier = Modifier) {
    val briefing by vm.briefing.collectAsStateWithLifecycle()
    val player by vm.briefingPlayer.collectAsStateWithLifecycle()
    val app = LocalAppColors.current
    AppCard(modifier) {
        Column {
            Row(verticalAlignment = Alignment.CenterVertically) {
                IconTile(Icons.Outlined.WbSunny, app.deadline)
                Spacer(Modifier.width(12.dp))
                Column(Modifier.weight(1f)) {
                    Text("Your day", style = MaterialTheme.typography.labelMedium, color = app.secondaryLabel)
                    Text(briefing?.greeting ?: "Today's briefing", style = MaterialTheme.typography.titleMedium)
                }
                Spacer(Modifier.width(8.dp))
                when (player.phase) {
                    BriefingPlayer.Phase.PLAYING ->
                        GlassPill("Stop", onClick = { vm.stopBriefing() }, icon = Icons.Filled.Stop)
                    BriefingPlayer.Phase.LOADING -> PrimaryPill("Play", onClick = {}, busy = true)
                    BriefingPlayer.Phase.IDLE ->
                        PrimaryPill("Play", onClick = { vm.playBriefing() }, icon = Icons.Filled.PlayArrow)
                }
            }
            val lines = briefing?.sections?.flatMap { it.lines }.orEmpty()
            if (lines.isNotEmpty()) {
                Spacer(Modifier.height(10.dp))
                lines.take(4).forEach { line ->
                    Text("• $line", style = MaterialTheme.typography.bodyMedium, modifier = Modifier.padding(vertical = 1.dp))
                }
            }
            Spacer(Modifier.height(8.dp))
            val voice = player.voice ?: if (briefing?.audio?.available == true) "ElevenLabs" else "this phone's voice"
            Text("Read by $voice · in the app only, never a notification",
                style = MaterialTheme.typography.labelSmall, color = app.tertiaryLabel)
            player.note?.let { Text(it, style = MaterialTheme.typography.labelSmall, color = app.tertiaryLabel) }
        }
    }
}

/** Today's classes from the portal's timetable, in a row. */
@OptIn(ExperimentalLayoutApi::class)
@Composable
private fun DueCard(
    item: Item,
    reminder: Reminder?,
    busy: Boolean,
    doneBusy: Boolean,
    calls: CallSettings?,
    modifier: Modifier = Modifier,
    onRemind: (Int, String) -> Unit,
    onCallConsent: (Int) -> Unit,
    onDone: () -> Unit,
) {
    val liveNow by com.sevenfive.app.ui.components.rememberNow(30_000L)
    val due = Time.parse(item.dueAt)
    val app = LocalAppColors.current
    // Within a day reads red; later reads in the brand colour.
    val urgent = due != null && due.toInstant().isBefore(liveNow.plus(Duration.ofHours(24)))
    AppCard(modifier) {
        Column {
            Row(verticalAlignment = Alignment.Top) {
                IconTile(kindStyle(item.kind).icon, kindColor(item.kind))
                Spacer(Modifier.width(12.dp))
                Column(Modifier.weight(1f)) {
                    Text(item.title ?: "Untitled", style = MaterialTheme.typography.titleMedium)
                    if (!item.subject.isNullOrBlank()) {
                        Text(item.subject, style = MaterialTheme.typography.bodyMedium, color = app.secondaryLabel)
                    }
                }
                if (due != null) {
                    Spacer(Modifier.width(8.dp))
                    val tint = if (urgent) MaterialTheme.colorScheme.error else MaterialTheme.colorScheme.primary
                    Text(
                        Time.until(due, liveNow),
                        style = MaterialTheme.typography.labelMedium,
                        fontWeight = FontWeight.SemiBold,
                        color = tint,
                        modifier = Modifier
                            .glassSurface(shape = CircleShape, tint = tint.copy(alpha = 0.12f))
                            .padding(horizontal = 10.dp, vertical = 4.dp),
                    )
                }
            }
            Spacer(Modifier.height(10.dp))
            Row(verticalAlignment = Alignment.CenterVertically) {
                KindChip(item.kind)
                Spacer(Modifier.width(8.dp))
                Icon(Icons.Outlined.Schedule, contentDescription = null, tint = app.tertiaryLabel, modifier = Modifier.size(13.dp))
                Spacer(Modifier.width(3.dp))
                Text(
                    due?.let { Time.dayAndTime(it) } ?: "No date",
                    style = MaterialTheme.typography.bodySmall,
                    color = app.secondaryLabel,
                    maxLines = 1,
                    overflow = TextOverflow.Ellipsis,
                    modifier = Modifier.weight(1f),
                )
                RouteBadge(item.route)
            }
            Spacer(Modifier.height(10.dp))
            // Wraps on a narrow phone: a long reminder time and three pills don't fit one line.
            FlowRow(
                horizontalArrangement = Arrangement.spacedBy(8.dp),
                verticalArrangement = Arrangement.spacedBy(8.dp),
            ) {
                RemindButton(reminder, busy, calls, onRemind, onCallConsent)
                if (due != null) {
                    val context = LocalContext.current
                    GlassPill("Calendar", onClick = {
                        Opener.addToPhoneCalendar(context, item)?.let { Toast.makeText(context, it, Toast.LENGTH_SHORT).show() }
                    }, icon = Icons.Outlined.EventAvailable, tint = MaterialTheme.colorScheme.onSurface)
                }
                GlassPill("Done", onClick = onDone, busy = doneBusy, icon = Icons.Outlined.Done,
                    tint = LocalStatusColors.current.safe)
            }
        }
    }
}

@Composable
private fun RemindButton(
    reminder: Reminder?,
    busy: Boolean,
    calls: CallSettings?,
    onRemind: (Int, String) -> Unit,
    onCallConsent: (Int) -> Unit,
) {
    var open by remember { mutableStateOf(false) }
    var consentFor by remember { mutableStateOf<Int?>(null) }
    val callLead = calls?.leadMinutes ?: 120
    Box {
        GlassPill(
            when {
                reminder == null -> "Remind me"
                reminder.isCall -> Time.parse(reminder.firesAt)?.let { "Call ${Time.dayAndTime(it)}" } ?: "Call set"
                else -> Time.parse(reminder.firesAt)?.let { "Reminder ${Time.dayAndTime(it)}" } ?: "Reminder set"
            },
            onClick = { open = true },
            busy = busy,
            icon = when {
                reminder == null -> Icons.Outlined.NotificationAdd
                reminder.isCall -> Icons.Filled.PhoneInTalk
                else -> Icons.Filled.NotificationsActive
            },
        )
        DropdownMenu(
            expanded = open,
            onDismissRequest = { open = false },
            shape = MaterialTheme.shapes.medium,
            containerColor = LocalAppColors.current.glassFallback,
        ) {
            reminderChoices.forEach { (minutes, label) ->
                DropdownMenuItem(text = { Text(label, style = MaterialTheme.typography.bodyLarge) }, onClick = {
                    open = false
                    onRemind(minutes, "push")
                })
            }
            HorizontalDivider()
            DropdownMenuItem(
                text = { Text("Call me ${leadLabel(callLead)} before", style = MaterialTheme.typography.bodyLarge) },
                leadingIcon = { Icon(Icons.Filled.PhoneInTalk, contentDescription = null, tint = MaterialTheme.colorScheme.primary) },
                onClick = {
                    open = false
                    if (calls?.enabled == true) onRemind(callLead, "call") else consentFor = callLead
                },
            )
        }
    }
    consentFor?.let { minutes ->
        CallConsentDialog(
            calls,
            onAccept = {
                consentFor = null
                onCallConsent(minutes)
            },
            onDismiss = { consentFor = null },
        )
    }
}

private fun leadLabel(minutes: Int): String = when {
    minutes % 60 == 0 && minutes >= 120 -> "${minutes / 60} hours"
    minutes == 60 -> "1 hour"
    else -> "$minutes minutes"
}

@Composable
private fun NeedsReviewCard(item: Item, modifier: Modifier = Modifier) {
    val app = LocalAppColors.current
    AppCard(modifier, muted = true) {
        Column {
            Text(
                item.title ?: "Untitled message",
                style = MaterialTheme.typography.bodyLarge,
                maxLines = 2,
                overflow = TextOverflow.Ellipsis,
            )
            Text(
                "Nobody could read this one for sure, so it wasn't filed.",
                style = MaterialTheme.typography.bodySmall,
                color = app.secondaryLabel,
            )
        }
    }
}
