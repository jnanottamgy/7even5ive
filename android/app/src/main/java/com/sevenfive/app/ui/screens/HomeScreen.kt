package com.sevenfive.app.ui.screens

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.CheckCircle
import androidx.compose.material.icons.filled.NotificationsActive
import androidx.compose.material.icons.outlined.CalendarMonth
import androidx.compose.material.icons.outlined.EventAvailable
import androidx.compose.material.icons.automirrored.outlined.HelpOutline
import androidx.compose.material.icons.outlined.NotificationAdd
import androidx.compose.material3.Button
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.DropdownMenu
import androidx.compose.material3.DropdownMenuItem
import androidx.compose.material3.Icon
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import com.sevenfive.app.data.Approval
import com.sevenfive.app.data.Item
import com.sevenfive.app.data.Reminder
import com.sevenfive.app.ui.AppViewModel
import com.sevenfive.app.ui.DoneApproval
import com.sevenfive.app.ui.components.AppCard
import com.sevenfive.app.ui.components.EmptyState
import com.sevenfive.app.ui.components.KindChip
import com.sevenfive.app.ui.components.RouteBadge
import com.sevenfive.app.ui.components.ScreenPadding
import com.sevenfive.app.ui.components.SectionHeader
import com.sevenfive.app.ui.components.TabScaffold
import com.sevenfive.app.util.Time
import java.time.Duration
import java.time.Instant

@Composable
fun HomeScreen(vm: AppViewModel, onSettings: () -> Unit) {
    val state by vm.cards.collectAsStateWithLifecycle()
    val busy by vm.busy.collectAsStateWithLifecycle()
    val approved by vm.approved.collectAsStateWithLifecycle()
    val cards = state.cards
    val due = cards?.dueThisWeek.orEmpty()
    val name = cards?.student?.name?.substringBefore(' ')?.takeIf { it.isNotBlank() }

    val subtitle = when {
        cards == null -> null
        due.isEmpty() -> "Nothing due in the next 7 days"
        due.size == 1 -> "1 thing due in the next 7 days"
        else -> "${due.size} things due in the next 7 days"
    }

    TabScaffold(if (name != null) "Hi, $name" else "This week", vm, onSettings, subtitle) {
        if (cards == null) {
            LoadingOrError(state.loading)
            return@TabScaffold
        }
        LazyColumn(contentPadding = ScreenPadding, verticalArrangement = Arrangement.spacedBy(10.dp)) {
            if (cards.approvals.isNotEmpty() || approved.isNotEmpty()) {
                item { SectionHeader("Needs your tap") }
                items(cards.approvals, key = { "a-" + it.token }) { approval ->
                    ApprovalCard(approval, vm.titleFor(approval), approval.token in busy) { vm.approve(approval) }
                }
                items(approved, key = { "d-" + it.approval.token }) { done ->
                    DoneApprovalCard(done, done.approval.token in busy) { vm.approve(done.approval) }
                }
            }

            item { SectionHeader("Due this week") }
            if (due.isEmpty()) {
                item {
                    EmptyState(
                        Icons.Outlined.EventAvailable,
                        "A clear week",
                        "Deadlines and exams from your groups, mail and Classroom show up here.",
                    )
                }
            }
            items(due, key = { "i-${it.id}" }) { item ->
                val reminder = cards.reminders.firstOrNull { it.title == item.title && it.dueAt == item.dueAt }
                DueCard(item, reminder, "item:${item.id}" in busy) { minutes -> vm.remind(item, minutes) }
            }

            if (cards.needsReview.isNotEmpty()) {
                item { SectionHeader("Couldn't read these") }
                items(cards.needsReview, key = { "r-${it.id}" }) { item -> NeedsReviewCard(item) }
            }
        }
    }
}

@Composable
internal fun LoadingOrError(loading: Boolean) {
    Box(Modifier.fillMaxWidth().padding(top = 64.dp), contentAlignment = Alignment.TopCenter) {
        if (loading) {
            CircularProgressIndicator()
        } else {
            EmptyState(
                Icons.AutoMirrored.Outlined.HelpOutline,
                "No cards yet",
                "Start the 7even5ive demo on the laptop, then check the server address in Settings.",
            )
        }
    }
}

@Composable
private fun ApprovalCard(approval: Approval, title: String, busy: Boolean, onApprove: () -> Unit) {
    AppCard {
        Row(verticalAlignment = Alignment.CenterVertically) {
            Icon(Icons.Outlined.CalendarMonth, contentDescription = null, tint = MaterialTheme.colorScheme.primary)
            Spacer(Modifier.width(12.dp))
            Column(Modifier.weight(1f)) {
                Text(actionLabel(approval.action), style = MaterialTheme.typography.labelLarge,
                    color = MaterialTheme.colorScheme.onSurfaceVariant)
                Text(title, style = MaterialTheme.typography.titleMedium, maxLines = 2, overflow = TextOverflow.Ellipsis)
                Text("Your AI asked for this. It only runs if you tap.", style = MaterialTheme.typography.bodySmall,
                    color = MaterialTheme.colorScheme.onSurfaceVariant)
            }
            Spacer(Modifier.width(8.dp))
            Button(onClick = onApprove, enabled = !busy) {
                if (busy) CircularProgressIndicator(Modifier.size(16.dp), strokeWidth = 2.dp) else Text("Approve")
            }
        }
    }
}

/** Kept after it ran: tapping again shows the gateway's "approval already used". */
@Composable
private fun DoneApprovalCard(done: DoneApproval, busy: Boolean, onTapAgain: () -> Unit) {
    AppCard(muted = true) {
        Row(verticalAlignment = Alignment.CenterVertically) {
            Icon(Icons.Filled.CheckCircle, contentDescription = null, tint = MaterialTheme.colorScheme.tertiary)
            Spacer(Modifier.width(12.dp))
            Column(Modifier.weight(1f)) {
                Text("Added to Google Calendar", style = MaterialTheme.typography.labelLarge,
                    color = MaterialTheme.colorScheme.onSurfaceVariant)
                Text(done.title, style = MaterialTheme.typography.titleMedium, maxLines = 2, overflow = TextOverflow.Ellipsis)
                Text("Each approval works once.", style = MaterialTheme.typography.bodySmall,
                    color = MaterialTheme.colorScheme.onSurfaceVariant)
            }
            OutlinedButton(onClick = onTapAgain, enabled = !busy) { Text("Approved") }
        }
    }
}

private fun actionLabel(action: String) = when (action) {
    "add_to_calendar" -> "Add to Google Calendar?"
    else -> action.replace('_', ' ').replaceFirstChar { it.uppercase() } + "?"
}

private val reminderChoices = listOf(24 * 60 to "1 day before", 3 * 60 to "3 hours before", 60 to "1 hour before")

@Composable
private fun DueCard(item: Item, reminder: Reminder?, busy: Boolean, onRemind: (Int) -> Unit) {
    val due = Time.parse(item.dueAt)
    AppCard {
        Column {
            Row(verticalAlignment = Alignment.CenterVertically) {
                KindChip(item.kind)
                Spacer(Modifier.width(8.dp))
                RouteBadge(item.route)
                Spacer(Modifier.weight(1f))
                if (due != null) {
                    // Within a day reads red; later reads in the brand colour.
                    val urgent = due.toInstant().isBefore(Instant.now().plus(Duration.ofHours(24)))
                    Text(
                        Time.until(due),
                        style = MaterialTheme.typography.labelLarge,
                        fontWeight = FontWeight.SemiBold,
                        color = if (urgent) MaterialTheme.colorScheme.error else MaterialTheme.colorScheme.primary,
                    )
                }
            }
            Spacer(Modifier.height(8.dp))
            Text(item.title ?: "Untitled", style = MaterialTheme.typography.titleMedium)
            if (!item.subject.isNullOrBlank()) {
                Text(item.subject, style = MaterialTheme.typography.bodyMedium, color = MaterialTheme.colorScheme.onSurfaceVariant)
            }
            Row(verticalAlignment = Alignment.CenterVertically) {
                Text(
                    due?.let { Time.dayAndTime(it) } ?: "No date",
                    style = MaterialTheme.typography.bodySmall,
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                    modifier = Modifier.weight(1f),
                )
                RemindButton(reminder, busy, onRemind)
            }
        }
    }
}

@Composable
private fun RemindButton(reminder: Reminder?, busy: Boolean, onRemind: (Int) -> Unit) {
    var open by remember { mutableStateOf(false) }
    Box {
        TextButton(onClick = { open = true }, enabled = !busy) {
            if (busy) {
                CircularProgressIndicator(Modifier.size(16.dp), strokeWidth = 2.dp)
            } else {
                Icon(
                    if (reminder != null) Icons.Filled.NotificationsActive else Icons.Outlined.NotificationAdd,
                    contentDescription = null,
                    modifier = Modifier.size(18.dp),
                )
            }
            Spacer(Modifier.width(6.dp))
            Text(
                if (reminder != null) Time.parse(reminder.firesAt)?.let { "Reminder ${Time.dayAndTime(it)}" } ?: "Reminder set"
                else "Remind me"
            )
        }
        DropdownMenu(expanded = open, onDismissRequest = { open = false }) {
            reminderChoices.forEach { (minutes, label) ->
                DropdownMenuItem(text = { Text(label) }, onClick = {
                    open = false
                    onRemind(minutes)
                })
            }
        }
    }
}

@Composable
private fun NeedsReviewCard(item: Item) {
    AppCard(muted = true) {
        Column {
            Text(
                item.title ?: "Untitled message",
                style = MaterialTheme.typography.bodyLarge,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
                maxLines = 2,
                overflow = TextOverflow.Ellipsis,
            )
            Text("Nobody could read this one for sure, so it wasn't filed.",
                style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.outline)
        }
    }
}
