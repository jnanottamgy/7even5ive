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
import androidx.compose.material.icons.automirrored.outlined.OpenInNew
import androidx.compose.material.icons.outlined.AlternateEmail
import androidx.compose.material.icons.outlined.MarkEmailRead
import androidx.compose.material.icons.outlined.Refresh
import androidx.compose.material.icons.outlined.Shield
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalUriHandler
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import com.sevenfive.app.data.Item
import com.sevenfive.app.data.MailStatus
import com.sevenfive.app.ui.AppViewModel
import com.sevenfive.app.ui.components.AppCard
import com.sevenfive.app.ui.components.EmptyState
import com.sevenfive.app.ui.components.GlassPill
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
import java.time.Instant

fun filteredLine(n: Int): String = when (n) {
    0 -> "No spam or fake mails found"
    1 -> "1 spam or fake mail filtered out"
    else -> "$n spam or fake mails filtered out"
}

fun leftOutLine(n: Int): String = when (n) {
    0 -> "Nothing left out yet"
    1 -> "1 other mail left out"
    else -> "$n other mails left out"
}

/** What a college-mail card is about, as the student would say it. */
fun categoryLabel(category: String?): String = when (category) {
    "placement" -> "Placement"
    "internship" -> "Internship"
    "exam_notice" -> "Exam notice"
    else -> "College mail"
}

@Composable
fun InboxScreen(vm: AppViewModel, onSettings: () -> Unit) {
    val state by vm.cards.collectAsStateWithLifecycle()
    val checking by vm.checkingMail.collectAsStateWithLifecycle()
    val cards = state.cards

    TabScaffold("Inbox", vm, onSettings) { padding ->
        if (cards == null) {
            LoadingOrError(state.loading, padding)
            return@TabScaffold
        }
        val mailCards = cards.opportunities.filter { it.fromMail }
        val others = cards.opportunities.filterNot { it.fromMail }.sortedByDescending { it.relevance ?: 0.0 }
        val app = LocalAppColors.current
        LazyColumn(contentPadding = padding, verticalArrangement = Arrangement.spacedBy(10.dp)) {
            item(key = "intro") { ScreenIntro("Placements, internships, exam notices and events from college mail.") }
            item(key = "mailbox") { MailboxCard(cards.mail, checking, Modifier.animateItem(placementSpec = Motion.item)) { vm.checkMail() } }
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
            if (mailCards.isEmpty() && others.isEmpty()) {
                item(key = "empty") {
                    EmptyState(Icons.Outlined.MarkEmailRead, "Nothing worth your time yet",
                        "Real placements, internships and exam notices from college mail show up here.")
                }
            }
            items(mailCards, key = { "m-${it.id}" }) { MailCard(it, Modifier.animateItem(placementSpec = Motion.item)) }
            items(others, key = { "o-${it.id}" }) { OpportunityCard(it, Modifier.animateItem(placementSpec = Motion.item)) }
        }
    }
}

/** Which mailbox, when it was checked, and the student's "Check now". */
@Composable
private fun MailboxCard(mail: MailStatus, checking: Boolean, modifier: Modifier = Modifier, onCheck: () -> Unit) {
    val app = LocalAppColors.current
    val cooling = Time.parse(mail.checkNowAfter)?.toInstant()?.isAfter(Instant.now()) == true
    AppCard(modifier) {
        Column {
            Row(verticalAlignment = Alignment.CenterVertically) {
                IconTile(Icons.Outlined.AlternateEmail, app.event, size = 36.dp)
                Spacer(Modifier.width(12.dp))
                Column(Modifier.weight(1f)) {
                    Text(
                        if (mail.isDemo) "Demo mailbox" else (mail.address ?: "Your college mail"),
                        style = MaterialTheme.typography.titleSmall,
                    )
                    val checked = Time.parse(mail.checkedAt)?.let { "Checked ${Time.dayAndTime(it)}" } ?: "Not checked yet"
                    val next = Time.parse(mail.nextCheckAt)?.let { " · next ${Time.dayAndTime(it)}" }.orEmpty()
                    Text(checked + next, style = MaterialTheme.typography.bodySmall, color = app.secondaryLabel)
                }
                Spacer(Modifier.width(8.dp))
                GlassPill(
                    if (cooling) "Checked" else "Check now",
                    onClick = onCheck,
                    enabled = !cooling,
                    busy = checking,
                    icon = Icons.Outlined.Refresh,
                )
            }
            Spacer(Modifier.height(8.dp))
            Text(
                leftOutLine(mail.leftOut) + if (mail.isDemo) " · invented mail until you connect Google in Settings" else "",
                style = MaterialTheme.typography.labelMedium,
                color = app.tertiaryLabel,
            )
        }
    }
}

/** One college-mail card: what it is, who, when, and the way to act on it. */
@Composable
private fun MailCard(item: Item, modifier: Modifier = Modifier) {
    val app = LocalAppColors.current
    val uri = LocalUriHandler.current
    val due = Time.parse(item.dueAt)
    val event = Time.parse(item.eventAt)
    val color = kindColor(item.kind)
    AppCard(modifier) {
        Column {
            Row(verticalAlignment = Alignment.Top) {
                IconTile(kindStyle(item.kind).icon, color)
                Spacer(Modifier.width(12.dp))
                Column(Modifier.weight(1f)) {
                    Text(categoryLabel(item.category), style = MaterialTheme.typography.labelMedium,
                        fontWeight = FontWeight.SemiBold, color = color)
                    Text(item.title ?: "Untitled", style = MaterialTheme.typography.titleMedium)
                    val who = listOfNotNull(item.organisation, item.role).joinToString(" · ")
                    if (who.isNotBlank()) {
                        Text(who, style = MaterialTheme.typography.bodyMedium, color = app.secondaryLabel)
                    }
                }
            }
            if (due != null || event != null) {
                Spacer(Modifier.height(8.dp))
                if (due != null) {
                    val what = if (item.kind == "deadline") "Apply by" else "On"
                    Text("$what ${Time.dayAndTime(due)} · ${Time.until(due)}", style = MaterialTheme.typography.bodySmall,
                        fontWeight = FontWeight.Medium,
                        color = if (Time.until(due) in listOf("today", "overdue")) MaterialTheme.colorScheme.error else app.secondaryLabel)
                }
                if (event != null) {
                    Text("Drive or test ${Time.dayAndTime(event)}", style = MaterialTheme.typography.bodySmall, color = app.secondaryLabel)
                }
            }
            if (!item.summary.isNullOrBlank()) {
                Spacer(Modifier.height(6.dp))
                Text(item.summary, style = MaterialTheme.typography.bodySmall, color = app.secondaryLabel)
            }
            Spacer(Modifier.height(10.dp))
            Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                item.link?.let { link ->
                    GlassPill("Open form", onClick = { runCatching { uri.openUri(link) } },
                        icon = Icons.AutoMirrored.Outlined.OpenInNew)
                }
                item.mailLink?.let { link ->
                    GlassPill("Open in Gmail", onClick = { runCatching { uri.openUri(link) } },
                        icon = Icons.Outlined.AlternateEmail, tint = app.secondaryLabel)
                }
                Spacer(Modifier.weight(1f))
                RouteBadge(item.route)
            }
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
