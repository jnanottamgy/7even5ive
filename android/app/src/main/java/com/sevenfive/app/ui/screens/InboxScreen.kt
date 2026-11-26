package com.sevenfive.app.ui.screens

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.outlined.MarkEmailRead
import androidx.compose.material.icons.outlined.Shield
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import com.sevenfive.app.data.Item
import com.sevenfive.app.ui.AppViewModel
import com.sevenfive.app.ui.components.AppCard
import com.sevenfive.app.ui.components.EmptyState
import com.sevenfive.app.ui.components.IconTile
import com.sevenfive.app.ui.components.KindChip
import com.sevenfive.app.ui.components.RouteBadge
import com.sevenfive.app.ui.components.ScreenIntro
import com.sevenfive.app.ui.components.SlimBar
import com.sevenfive.app.ui.components.TabScaffold
import com.sevenfive.app.ui.components.kindColor
import com.sevenfive.app.ui.components.kindStyle
import com.sevenfive.app.ui.theme.LocalAppColors
import com.sevenfive.app.ui.theme.LocalStatusColors
import com.sevenfive.app.ui.theme.Motion
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

    TabScaffold("Inbox", vm, onSettings) { padding ->
        if (cards == null) {
            LoadingOrError(state.loading, padding)
            return@TabScaffold
        }
        val opportunities = cards.opportunities.sortedByDescending { it.relevance ?: 0.0 }
        val app = LocalAppColors.current
        LazyColumn(contentPadding = padding, verticalArrangement = Arrangement.spacedBy(10.dp)) {
            item(key = "intro") { ScreenIntro("Internships, events and notices from college mail that fit you.") }
            item(key = "shield") {
                AppCard {
                    Row(verticalAlignment = Alignment.CenterVertically) {
                        IconTile(Icons.Outlined.Shield, LocalStatusColors.current.safe, size = 36.dp)
                        Spacer(Modifier.width(12.dp))
                        Column {
                            Text(filteredLine(cards.filtered), style = MaterialTheme.typography.titleSmall)
                            Text("Paid \"placement\" offers and fake placement-cell mail never reach this list.",
                                style = MaterialTheme.typography.bodySmall, color = app.secondaryLabel)
                        }
                    }
                }
            }
            if (opportunities.isEmpty()) {
                item(key = "empty") {
                    EmptyState(Icons.Outlined.MarkEmailRead, "Nothing worth your time yet",
                        "Real internships and events from college mail show up here, best match first.")
                }
            }
            items(opportunities, key = { it.id }) { OpportunityCard(it, Modifier.animateItem(placementSpec = Motion.item)) }
        }
    }
}

@Composable
private fun OpportunityCard(item: Item, modifier: Modifier = Modifier) {
    val due = Time.parse(item.dueAt)
    val app = LocalAppColors.current
    val color = kindColor(item.kind)
    AppCard(modifier) {
        Column {
            Row(verticalAlignment = Alignment.Top) {
                IconTile(kindStyle(item.kind).icon, color)
                Spacer(Modifier.width(12.dp))
                Column(Modifier.weight(1f)) {
                    Text(item.title ?: "Untitled", style = MaterialTheme.typography.titleMedium)
                    if (due != null) {
                        Text("${Time.dayAndTime(due)} · ${Time.until(due)}", style = MaterialTheme.typography.bodySmall,
                            color = app.secondaryLabel)
                    }
                }
            }
            Spacer(Modifier.height(10.dp))
            Row(verticalAlignment = Alignment.CenterVertically) {
                KindChip(item.kind)
                Spacer(Modifier.width(8.dp))
                RouteBadge(item.route)
                Spacer(Modifier.weight(1f))
                item.relevance?.let {
                    Text("${(it * 100).toInt()}% match", style = MaterialTheme.typography.labelMedium,
                        fontWeight = FontWeight.SemiBold, color = MaterialTheme.colorScheme.primary)
                }
            }
            item.relevance?.let {
                Spacer(Modifier.height(8.dp))
                SlimBar(it.toFloat(), MaterialTheme.colorScheme.primary)
            }
        }
    }
}
