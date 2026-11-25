package com.sevenfive.app.ui.screens

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.outlined.Alarm
import androidx.compose.material.icons.outlined.AlarmOff
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.Icon
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
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
import com.sevenfive.app.ui.components.ScreenPadding
import com.sevenfive.app.ui.components.TabScaffold
import com.sevenfive.app.util.Time

@Composable
fun RemindersScreen(vm: AppViewModel, onSettings: () -> Unit) {
    val state by vm.cards.collectAsStateWithLifecycle()
    val busy by vm.busy.collectAsStateWithLifecycle()
    val reminders = state.cards?.reminders.orEmpty()
        .sortedBy { Time.parse(it.firesAt)?.toInstant() }

    TabScaffold("Reminders", vm, onSettings, subtitle = "Only the ones you asked for") {
        if (state.cards == null) {
            LoadingOrError(state.loading)
            return@TabScaffold
        }
        LazyColumn(contentPadding = ScreenPadding, verticalArrangement = Arrangement.spacedBy(10.dp)) {
            if (reminders.isEmpty()) {
                item {
                    EmptyState(Icons.Outlined.AlarmOff, "No reminders",
                        "Tap \"Remind me\" on a card in This week: 1 day, 3 hours or 1 hour before it's due.")
                }
            }
            items(reminders, key = { it.id }) { r ->
                ReminderCard(r, "rem:${r.id}" in busy) { vm.cancel(r) }
            }
            if (reminders.isNotEmpty()) {
                item {
                    Text(
                        "Phone notifications for reminders are coming; until then they live here.",
                        style = MaterialTheme.typography.bodySmall,
                        color = MaterialTheme.colorScheme.outline,
                    )
                }
            }
        }
    }
}

@Composable
private fun ReminderCard(r: Reminder, busy: Boolean, onCancel: () -> Unit) {
    val fires = Time.parse(r.firesAt)
    val due = Time.parse(r.dueAt)
    AppCard {
        Row(verticalAlignment = Alignment.CenterVertically) {
            Icon(Icons.Outlined.Alarm, contentDescription = null, tint = MaterialTheme.colorScheme.primary)
            Spacer(Modifier.width(12.dp))
            Column(Modifier.weight(1f)) {
                Text(
                    fires?.let { "${Time.dayAndTime(it)} · ${Time.until(it)}" } ?: "Soon",
                    style = MaterialTheme.typography.labelLarge,
                    fontWeight = FontWeight.SemiBold,
                    color = MaterialTheme.colorScheme.primary,
                )
                Text(r.title ?: "Untitled", style = MaterialTheme.typography.titleMedium)
                Text(
                    listOfNotNull(r.subject, due?.let { "due ${Time.dayAndTime(it)}" }).joinToString(" · "),
                    style = MaterialTheme.typography.bodySmall,
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                )
            }
            TextButton(onClick = onCancel, enabled = !busy) {
                if (busy) CircularProgressIndicator(Modifier.size(16.dp), strokeWidth = 2.dp) else Text("Cancel")
            }
        }
    }
}
