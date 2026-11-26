package com.sevenfive.app.ui.screens

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.outlined.Alarm
import androidx.compose.material.icons.outlined.AlarmOff
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import com.sevenfive.app.data.Reminder
import com.sevenfive.app.ui.AppViewModel
import com.sevenfive.app.ui.components.AppCard
import com.sevenfive.app.ui.components.EmptyState
import com.sevenfive.app.ui.components.GlassPill
import com.sevenfive.app.ui.components.IconTile
import com.sevenfive.app.ui.components.ScreenIntro
import com.sevenfive.app.ui.components.TabScaffold
import com.sevenfive.app.ui.theme.LocalAppColors
import com.sevenfive.app.ui.theme.Motion
import com.sevenfive.app.util.Time

@Composable
fun RemindersScreen(vm: AppViewModel, onSettings: () -> Unit) {
    val state by vm.cards.collectAsStateWithLifecycle()
    val busy by vm.busy.collectAsStateWithLifecycle()
    val reminders = state.cards?.reminders.orEmpty()
        .sortedBy { Time.parse(it.firesAt)?.toInstant() }

    TabScaffold("Reminders", vm, onSettings) { padding ->
        if (state.cards == null) {
            LoadingOrError(state.loading, padding)
            return@TabScaffold
        }
        LazyColumn(contentPadding = padding, verticalArrangement = Arrangement.spacedBy(10.dp)) {
            item(key = "intro") { ScreenIntro("Only the ones you asked for.") }
            if (reminders.isEmpty()) {
                item(key = "empty") {
                    EmptyState(Icons.Outlined.AlarmOff, "No reminders",
                        "Tap \"Remind me\" on a card in This week: 1 day, 3 hours or 1 hour before it's due.")
                }
            }
            items(reminders, key = { it.id }) { r ->
                ReminderCard(r, "rem:${r.id}" in busy, Modifier.animateItem(placementSpec = Motion.item)) { vm.cancel(r) }
            }
            if (reminders.isNotEmpty()) {
                item(key = "note") {
                    Text(
                        "Phone notifications for reminders are coming; until then they live here.",
                        style = MaterialTheme.typography.bodySmall,
                        color = LocalAppColors.current.tertiaryLabel,
                        modifier = Modifier.padding(horizontal = 6.dp, vertical = 4.dp),
                    )
                }
            }
        }
    }
}

@Composable
private fun ReminderCard(r: Reminder, busy: Boolean, modifier: Modifier = Modifier, onCancel: () -> Unit) {
    val fires = Time.parse(r.firesAt)
    val due = Time.parse(r.dueAt)
    val app = LocalAppColors.current
    AppCard(modifier) {
        Row(verticalAlignment = Alignment.CenterVertically) {
            IconTile(Icons.Outlined.Alarm, app.deadline)
            Spacer(Modifier.width(12.dp))
            Column(Modifier.weight(1f)) {
                Text(
                    fires?.let { "${Time.dayAndTime(it)} · ${Time.until(it)}" } ?: "Soon",
                    style = MaterialTheme.typography.labelMedium,
                    fontWeight = FontWeight.SemiBold,
                    color = MaterialTheme.colorScheme.primary,
                )
                Text(r.title ?: "Untitled", style = MaterialTheme.typography.titleMedium)
                Text(
                    listOfNotNull(r.subject, due?.let { "due ${Time.dayAndTime(it)}" }).joinToString(" · "),
                    style = MaterialTheme.typography.bodySmall,
                    color = app.secondaryLabel,
                )
            }
            Spacer(Modifier.width(8.dp))
            GlassPill("Cancel", onClick = onCancel, busy = busy, tint = MaterialTheme.colorScheme.error)
        }
    }
}
