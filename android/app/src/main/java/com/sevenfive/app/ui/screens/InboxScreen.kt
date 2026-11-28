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
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.padding
import com.sevenfive.app.ui.components.segmentSlide
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableIntStateOf
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
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

/** One kind of college mail: its cards, or a plain line saying there are none. */
private fun androidx.compose.foundation.lazy.LazyListScope.mailSegment(list: List<Item>, emptyTitle: String, emptyBody: String) {
    if (list.isEmpty()) {
        item(key = "empty-$emptyTitle") { EmptyState(Icons.Outlined.MarkEmailRead, emptyTitle, emptyBody) }
    }
    items(list, key = { "m-${it.id}" }) { MailCard(it, Modifier.animateItem(placementSpec = Motion.item)) }
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

    var segment by rememberSaveable { mutableIntStateOf(0) }
    TabScaffold("Inbox", vm, onSettings) { padding ->
        if (cards == null) {
            LoadingOrError(state.loading, padding)
            return@TabScaffold
        }
        val mailCards = cards.opportunities.filter { it.fromMail }
        val others = cards.opportunities.filterNot { it.fromMail }.sortedByDescending { it.relevance ?: 0.0 }
        val app = LocalAppColors.current
        // College mail, split the way a student thinks about it.
        val placements = mailCards.filter { it.category == "placement" }
        val internships = mailCards.filter { it.category == "internship" }
        val exams = mailCards.filter { it.category == "exam_notice" }
        val rest = mailCards.filter { it.category !in setOf("placement", "internship", "exam_notice") } + others
        val segments = listOf(
            Segment("Overview"),
            Segment("Placements", placements.size),
            Segment("Internships", internships.size),
            Segment("Exam notices", exams.size),
            Segment("Events & more", rest.size),
        )
        // The switcher stays pinned; the segment under it slides in when it changes.
        Column(Modifier.fillMaxSize().padding(start = 16.dp, end = 16.dp, top = padding.calculateTopPadding())) {
            NeoSegments(segments, segment) { segment = it }
            LazyColumn(
                contentPadding = PaddingValues(top = 6.dp, bottom = padding.calculateBottomPadding()),
                verticalArrangement = Arrangement.spacedBy(10.dp),
                modifier = Modifier.fillMaxSize().segmentSlide(segment),
            ) {                when (segment) {
                    0 -> {
                        item(key = "hero") {
                            InboxHero(mailCards.size + others.size, cards.filtered, Modifier.animateItem(placementSpec = Motion.item))
                        }
                        item(key = "mailbox") { MailboxCard(cards.mail, checking, Modifier.animateItem(placementSpec = Motion.item)) { vm.checkMail() } }
                    }
                    1 -> {
                    // The placement tracker: eligibility, time left to register, your steps.
                    if (placements.isEmpty()) {
                        item(key = "empty-placements") {
                            EmptyState(Icons.Outlined.MarkEmailRead, "No placement drives yet",
                                "Job offers and placement drives from college mail show up here, with whether you clear the cut-off.")
                        }
                    } else {
                        item(key = "placement-summary") { PlacementSummary(placements, cards) }
                    }
                    items(placements, key = { "p-${it.id}" }) { PlacementCard(it, cards, Modifier.animateItem(placementSpec = Motion.item)) }
                }
                    2 -> mailSegment(internships, "No internships yet", "Internship openings from college mail show up here.")
                    3 -> mailSegment(exams, "No exam notices", "Exam timetables, hall tickets and results notices show up here.")
                    else -> {
                        if (rest.isEmpty()) {
                            item(key = "empty-other") {
                                EmptyState(Icons.Outlined.MarkEmailRead, "Nothing else worth your time",
                                    "Events and opportunities from mail, your groups and Classroom show up here.")
                            }
                        }
                        items(rest, key = { "o-${it.id}" }) { item ->
                            if (item.fromMail) MailCard(item, Modifier.animateItem(placementSpec = Motion.item))
                            else OpportunityCard(item, Modifier.animateItem(placementSpec = Motion.item))
                        }
                    }
                }
                    }
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
                        when {
                            mail.isDemo -> "Demo mailbox"
                            mail.needsGoogle -> "Your college mail"
                            else -> mail.address ?: "Your college mail"
                        },
                        style = MaterialTheme.typography.titleSmall,
                    )
                    val checked = Time.parse(mail.checkedAt)?.let { "Checked ${Time.dayAndTime(it)}" } ?: "Not checked yet"
                    val next = Time.parse(mail.nextCheckAt)?.let { " · next ${Time.dayAndTime(it)}" }.orEmpty()
                    Text(
                        if (mail.needsGoogle) "Not connected" else checked + next,
                        style = MaterialTheme.typography.bodySmall,
                        color = app.secondaryLabel,
                    )
                }
                if (!mail.needsGoogle) {
                    Spacer(Modifier.width(8.dp))
                    GlassPill(
                        if (cooling) "Checked" else "Check now",
                        onClick = onCheck,
                        enabled = !cooling,
                        busy = checking,
                        icon = Icons.Outlined.Refresh,
                    )
                }
            }
            Spacer(Modifier.height(8.dp))
            Text(
                when {
                    mail.needsGoogle -> "Connect Google in Settings: placements, internships and exam notices from your college mail land here."
                    mail.needsReconnect -> "Google stopped accepting the connection: reconnect it in Settings to keep your college mail coming."
                    mail.isDemo -> leftOutLine(mail.leftOut) + " · invented mail until you connect Google in Settings"
                    else -> leftOutLine(mail.leftOut)
                },
                style = MaterialTheme.typography.labelMedium,
                color = app.tertiaryLabel,
            )
        }
    }
}

/** One college-mail card: what it is, who, when, and the way to act on it. */
@Composable
private fun MailCard(item: Item, modifier: Modifier = Modifier) {
    val liveNow by com.sevenfive.app.ui.components.rememberNow(30_000L)
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
                    Text("$what ${Time.dayAndTime(due)} · ${Time.until(due, liveNow)}", style = MaterialTheme.typography.bodySmall,
                        fontWeight = FontWeight.Medium,
                        color = if (Time.until(due, liveNow) in listOf("today", "overdue")) MaterialTheme.colorScheme.error else app.secondaryLabel)
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
    val liveNow by com.sevenfive.app.ui.components.rememberNow(30_000L)
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
                        Text("${Time.dayAndTime(due)} · ${Time.until(due, liveNow)}", style = MaterialTheme.typography.bodySmall,
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
