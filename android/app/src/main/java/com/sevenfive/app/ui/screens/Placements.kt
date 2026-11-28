package com.sevenfive.app.ui.screens

import androidx.compose.foundation.background
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
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.outlined.OpenInNew
import androidx.compose.material.icons.outlined.AlternateEmail
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableIntStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.platform.LocalUriHandler
import androidx.compose.ui.semantics.Role
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.role
import androidx.compose.ui.semantics.selected
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.dp
import com.sevenfive.app.data.Cards
import com.sevenfive.app.data.Item
import com.sevenfive.app.data.LocalLog
import com.sevenfive.app.ui.components.AppCard
import com.sevenfive.app.ui.components.GlassPill
import com.sevenfive.app.ui.components.PrimaryPill
import com.sevenfive.app.ui.components.rememberNow
import com.sevenfive.app.ui.theme.LocalAppColors
import com.sevenfive.app.ui.theme.NeoGround
import com.sevenfive.app.ui.theme.NeoInk
import com.sevenfive.app.ui.theme.Orange
import com.sevenfive.app.ui.theme.pressable
import com.sevenfive.app.util.Time
import java.util.Locale

/*
 * The placement tracker: each drive from college mail as a card that knows whether the student
 * clears its CGPA cut-off, how long is left to register, and how far they've got. The steps are
 * the student's own, kept on this phone (LocalLog); the drive itself is the mail's.
 */

private val CUTOFF = Regex("""(?i)(?:cgpa|cpi|gpa)[^0-9]{0,24}(\d{1,2}(?:\.\d{1,2})?)""")

/** The CGPA cut-off a mail states ("CGPA 7.0 and above"), if it states one. */
internal fun cgpaCutoff(details: String?): Double? =
    details?.let { CUTOFF.find(it)?.groupValues?.get(1)?.toDoubleOrNull() }?.takeIf { it in 0.0..10.0 }

/** The student's latest CGPA, from the portal's results. */
internal fun latestCgpa(cards: Cards): Double? =
    cards.results.data.semesters.filter { it.cgpa != null }.maxByOrNull { it.semester }?.cgpa

/** Eligible, not eligible, or unknown (no cut-off in the mail, or no CGPA from the portal). */
internal fun eligible(item: Item, cgpa: Double?): Boolean? {
    val cut = cgpaCutoff(item.details) ?: return null
    return cgpa?.let { it >= cut }
}

/** The line over the placement list: how many drives, how many the student clears, how many started. */
@Composable
internal fun PlacementSummary(drives: List<Item>, cards: Cards, modifier: Modifier = Modifier) {
    val context = LocalContext.current
    val sid = cards.student?.id ?: 0
    val cgpa = latestCgpa(cards)
    val clears = drives.count { eligible(it, cgpa) == true }
    val started = drives.count { LocalLog.stage(context, sid, it.id) > 0 }
    val app = LocalAppColors.current
    Row(modifier.fillMaxWidth().padding(top = 6.dp, bottom = 4.dp), horizontalArrangement = Arrangement.spacedBy(22.dp)) {
        Stat("${drives.size}", if (drives.size == 1) "drive" else "drives")
        Stat("$clears", "you clear")
        Stat("$started", "in progress")
        if (cgpa != null) {
            Spacer(Modifier.weight(1f))
            Column(horizontalAlignment = Alignment.End) {
                Text(String.format(Locale.ENGLISH, "%.2f", cgpa), style = MaterialTheme.typography.headlineSmall)
                Text("your CGPA", style = MaterialTheme.typography.bodySmall, color = app.secondaryLabel)
            }
        }
    }
}

@Composable
private fun Stat(value: String, label: String) {
    Column {
        Text(value, style = MaterialTheme.typography.headlineSmall)
        Text(label, style = MaterialTheme.typography.bodySmall, color = LocalAppColors.current.secondaryLabel)
    }
}

/** One drive: who and what, the cut-off against your CGPA, time left to register, your steps. */
@Composable
internal fun PlacementCard(item: Item, cards: Cards, modifier: Modifier = Modifier) {
    val context = LocalContext.current
    val uri = LocalUriHandler.current
    val app = LocalAppColors.current
    val sid = cards.student?.id ?: 0
    var stage by remember(item.id, sid) { mutableIntStateOf(LocalLog.stage(context, sid, item.id)) }
    fun set(to: Int) {
        stage = to
        LocalLog.setStage(context, sid, item.id, to)
    }
    val cgpa = latestCgpa(cards)
    val cut = cgpaCutoff(item.details)
    val ok = eligible(item, cgpa)
    val deadline = Time.parse(item.dueAt).takeIf { item.kind == "deadline" }
    val drive = Time.parse(item.eventAt) ?: Time.parse(item.dueAt).takeIf { item.kind != "deadline" }

    AppCard(modifier) {
        Column {
            // Who and what.
            Text(
                (item.organisation ?: item.title ?: "Placement drive"),
                style = MaterialTheme.typography.titleLarge,
            )
            val what = listOfNotNull(item.role, item.title.takeIf { it != item.organisation }).joinToString(" · ")
            if (what.isNotBlank()) {
                Text(what, style = MaterialTheme.typography.bodyMedium, color = app.secondaryLabel)
            }

            // Eligibility: the mail's cut-off against the student's CGPA.
            Spacer(Modifier.height(12.dp))
            val (line, tone) = when {
                cut == null -> "No CGPA cut-off in the mail" to app.secondaryLabel
                cgpa == null -> "Cut-off CGPA ${fmt(cut)} · connect the portal to check yours" to app.secondaryLabel
                ok == true -> "You clear the cut-off · ${fmt(cgpa)} ≥ ${fmt(cut)}" to NeoInk
                else -> "Below the cut-off · ${fmt(cgpa)} < ${fmt(cut)}" to com.sevenfive.app.ui.theme.LocalStatusColors.current.short
            }
            Row(verticalAlignment = Alignment.CenterVertically) {
                Box(Modifier.size(8.dp).clip(CircleShape).background(if (ok == false) Orange else if (ok == true) NeoInk else app.hairline))
                Spacer(Modifier.width(8.dp))
                Text(line, style = MaterialTheme.typography.bodyMedium, fontWeight = FontWeight.Medium, color = tone)
            }
            item.details?.takeIf { it.isNotBlank() }?.let {
                Text(it, style = MaterialTheme.typography.bodySmall, color = app.secondaryLabel, modifier = Modifier.padding(start = 16.dp, top = 2.dp))
            }

            // Time left to register, live: its own small piece, so only it ticks every second.
            if (deadline != null) {
                Spacer(Modifier.height(12.dp))
                RegisterCountdown(deadline)
                Text("Last date ${Time.dayAndTime(deadline)}", style = MaterialTheme.typography.bodySmall, color = app.secondaryLabel)
            }
            if (drive != null) {
                Text("Drive or test ${Time.dayAndTime(drive)}", style = MaterialTheme.typography.bodySmall, color = app.secondaryLabel)
            }

            // Your steps.
            Spacer(Modifier.height(14.dp))
            Pipeline(stage) { set(it) }

            Spacer(Modifier.height(12.dp))
            Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                item.link?.let { link ->
                    PrimaryPill("Register", onClick = {
                        runCatching { uri.openUri(link) }
                        if (stage == 0) set(1)
                    }, icon = Icons.AutoMirrored.Outlined.OpenInNew)
                }
                item.mailLink?.let { link ->
                    GlassPill("Mail", onClick = { runCatching { uri.openUri(link) } }, icon = Icons.Outlined.AlternateEmail)
                }
                Spacer(Modifier.weight(1f))
                Text(
                    if (stage == LocalLog.NOT_APPLYING) "Applying after all" else "Not applying",
                    style = MaterialTheme.typography.labelMedium,
                    color = app.secondaryLabel,
                    modifier = Modifier
                        .clip(CircleShape)
                        .pressable(scaleTo = 0.96f) { set(if (stage == LocalLog.NOT_APPLYING) 0 else LocalLog.NOT_APPLYING) }
                        .padding(horizontal = 8.dp, vertical = 12.dp),
                )
            }
        }
    }
}

/** Registered → Test → Interview → Offer: tap a step to say you've reached it (tap again to step back). */
@Composable
private fun Pipeline(stage: Int, onSet: (Int) -> Unit) {
    val app = LocalAppColors.current
    if (stage == LocalLog.NOT_APPLYING) {
        Text("Not applying", style = MaterialTheme.typography.bodyMedium, color = app.secondaryLabel)
        return
    }
    Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(4.dp)) {
        LocalLog.stages.forEachIndexed { i, name ->
            val step = i + 1
            val reached = stage >= step
            val current = stage == step
            Column(
                Modifier
                    .weight(1f)
                    .clip(MaterialTheme.shapes.small)
                    .semantics(mergeDescendants = true) {
                        role = Role.Button
                        selected = reached
                        contentDescription = "$name" + if (reached) ", reached" else ""
                    }
                    .pressable(scaleTo = 0.96f) { onSet(if (current) step - 1 else step) }
                    .padding(vertical = 6.dp),
                horizontalAlignment = Alignment.CenterHorizontally,
            ) {
                Box(
                    Modifier
                        .fillMaxWidth()
                        .height(4.dp)
                        .clip(CircleShape)
                        .background(if (current && step == LocalLog.stages.size) Orange else if (reached) NeoInk else app.hairline),
                )
                Text(
                    name,
                    style = MaterialTheme.typography.labelMedium,
                    color = if (reached) NeoInk else app.secondaryLabel,
                    textAlign = TextAlign.Center,
                    modifier = Modifier.padding(top = 6.dp),
                )
            }
        }
    }
}

private fun fmt(v: Double): String =
    if (v % 1.0 == 0.0) String.format(Locale.ENGLISH, "%.1f", v) else String.format(Locale.ENGLISH, "%.2f", v).trimEnd('0')

@Composable
private fun RegisterCountdown(deadline: java.time.OffsetDateTime) {
    val now by rememberNow(1_000L)
    val left = Time.countdown(deadline, now)
    Text(
        if (left == "now") "Registration closed" else "Register within $left",
        style = MaterialTheme.typography.titleMedium.copy(fontFeatureSettings = "tnum"),
        color = if (deadline.toInstant().isBefore(now.plusSeconds(86_400))) com.sevenfive.app.ui.theme.LocalStatusColors.current.short else NeoInk,
    )
}
