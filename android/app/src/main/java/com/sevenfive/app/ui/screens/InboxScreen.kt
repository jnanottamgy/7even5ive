package com.sevenfive.app.ui.screens

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.outlined.MarkEmailRead
import androidx.compose.material.icons.outlined.Shield
import androidx.compose.material3.Icon
import androidx.compose.material3.LinearProgressIndicator
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.dp
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import com.sevenfive.app.data.Item
import com.sevenfive.app.ui.AppViewModel
import com.sevenfive.app.ui.components.AppCard
import com.sevenfive.app.ui.components.EmptyState
import com.sevenfive.app.ui.components.KindChip
import com.sevenfive.app.ui.components.RouteBadge
import com.sevenfive.app.ui.components.ScreenPadding
import com.sevenfive.app.ui.components.TabScaffold
import com.sevenfive.app.util.Time

fun filteredLine(n: Int): String = when (n) {
    0 -> "No spam or fake mails found"
    1 -> "1 spam or fake mail filtered out"
    else -> "$n spam or fake mails filtered out"
}

@Composable
fun InboxScreen(vm: AppViewModel, onSettings: () -> Unit) {
    val state by vm.cards.collectAsStateWithLifecycle()
    val cards = state.cards

    TabScaffold("From your inbox", vm, onSettings, subtitle = "Internships, events and notices that fit you") {
        if (cards == null) {
            LoadingOrError(state.loading)
            return@TabScaffold
        }
        val opportunities = cards.opportunities.sortedByDescending { it.relevance ?: 0.0 }
        LazyColumn(contentPadding = ScreenPadding, verticalArrangement = Arrangement.spacedBy(10.dp)) {
            item {
                AppCard(muted = true) {
                    Row(verticalAlignment = Alignment.CenterVertically) {
                        Icon(Icons.Outlined.Shield, contentDescription = null, tint = MaterialTheme.colorScheme.tertiary)
                        Spacer(Modifier.width(12.dp))
                        Column {
                            Text(filteredLine(cards.filtered), style = MaterialTheme.typography.titleSmall)
                            Text("Paid \"placement\" offers and fake placement-cell mail never reach this list.",
                                style = MaterialTheme.typography.bodySmall,
                                color = MaterialTheme.colorScheme.onSurfaceVariant)
                        }
                    }
                }
            }
            if (opportunities.isEmpty()) {
                item {
                    EmptyState(Icons.Outlined.MarkEmailRead, "Nothing worth your time yet",
                        "Real internships and events from college mail show up here, best match first.")
                }
            }
            items(opportunities, key = { it.id }) { OpportunityCard(it) }
        }
    }
}

@Composable
private fun OpportunityCard(item: Item) {
    val due = Time.parse(item.dueAt)
    AppCard {
        Column {
            Row(verticalAlignment = Alignment.CenterVertically) {
                KindChip(item.kind)
                Spacer(Modifier.width(8.dp))
                RouteBadge(item.route)
                Spacer(Modifier.weight(1f))
                item.relevance?.let {
                    Text("${(it * 100).toInt()}% match", style = MaterialTheme.typography.labelLarge,
                        color = MaterialTheme.colorScheme.primary)
                }
            }
            Spacer(Modifier.height(8.dp))
            Text(item.title ?: "Untitled", style = MaterialTheme.typography.titleMedium)
            if (due != null) {
                Text("${Time.dayAndTime(due)} · ${Time.until(due)}", style = MaterialTheme.typography.bodySmall,
                    color = MaterialTheme.colorScheme.onSurfaceVariant)
            }
            item.relevance?.let {
                Spacer(Modifier.height(8.dp))
                LinearProgressIndicator(
                    progress = { it.toFloat().coerceIn(0f, 1f) },
                    modifier = Modifier.fillMaxWidth(),
                    drawStopIndicator = {},
                )
            }
        }
    }
}
