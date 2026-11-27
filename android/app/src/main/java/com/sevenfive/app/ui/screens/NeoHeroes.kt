package com.sevenfive.app.ui.screens

import androidx.compose.foundation.background
import androidx.compose.material.icons.automirrored.outlined.KeyboardArrowRight
import androidx.compose.material.icons.outlined.Alarm
import androidx.compose.foundation.clickable
import androidx.compose.foundation.horizontalScroll
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.BoxWithConstraints
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.offset
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.draw.drawBehind
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.role
import androidx.compose.ui.semantics.selected
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.sevenfive.app.data.Cards
import com.sevenfive.app.data.SubjectAttendance
import com.sevenfive.app.ui.components.kindStyle
import com.sevenfive.app.ui.components.rememberNow
import androidx.compose.runtime.getValue
import com.sevenfive.app.ui.theme.LocalAppColors
import com.sevenfive.app.ui.theme.glassSurface
import com.sevenfive.app.ui.theme.NeoInk
import com.sevenfive.app.ui.theme.Orange
import com.sevenfive.app.util.Time
import java.time.LocalDate
import java.time.ZoneId
import java.time.format.DateTimeFormatter
import java.time.format.TextStyle
import java.util.Locale

/*
 * Neo-minimal heroes: each tab opens on one big answer, and everything else steps back.
 * Orange appears once per screen, on the thing that needs the student.
 */

/** A small uppercase label with an optional dot: the quiet line above a hero. */
@Composable
internal fun NeoLabel(text: String, dot: Color? = null, modifier: Modifier = Modifier) {
    Row(modifier, verticalAlignment = Alignment.CenterVertically) {
        if (dot != null) {
            Box(Modifier.size(8.dp).clip(CircleShape).background(dot))
            Spacer(Modifier.width(8.dp))
        }
        Text(
            text.uppercase(),
            style = MaterialTheme.typography.labelSmall,
            letterSpacing = 1.5.sp,
            color = LocalAppColors.current.secondaryLabel,
        )
    }
}

private val hourMinute = DateTimeFormatter.ofPattern("HH:mm", Locale.ENGLISH)

private fun dayWord(date: LocalDate, today: LocalDate = LocalDate.now()): String = when (date) {
    today -> "Today"
    today.plusDays(1) -> "Tomorrow"
    else -> date.dayOfWeek.getDisplayName(TextStyle.FULL, Locale.ENGLISH)
}

/** Home: the next thing due, huge; then attendance in one line and five small bars. */
@Composable
internal fun HomeHero(cards: Cards, modifier: Modifier = Modifier, withAttendance: Boolean = true) {
    val app = LocalAppColors.current
    val zone = ZoneId.systemDefault()
    val next = cards.dueThisWeek
        .mapNotNull { item -> Time.parse(item.dueAt)?.let { item to it.atZoneSameInstant(zone) } }
        .minByOrNull { it.second }
    Column(modifier.fillMaxWidth().padding(top = 6.dp, bottom = 4.dp)) {
        if (next != null) {
            val (item, at) = next
            // Real time: a countdown that ticks every second, not a fixed clock time.
            val now by rememberNow(1_000L)
            val days = java.time.Duration.between(now, at.toInstant()).toDays()
            val countdown = Time.countdown(at.toOffsetDateTime(), now)
            NeoLabel("Next · due ${dayWord(at.toLocalDate()).lowercase(Locale.ENGLISH)}", dot = Orange)
            Row(Modifier.padding(top = 8.dp), verticalAlignment = Alignment.Bottom) {
                com.sevenfive.app.ui.components.RollingText(
                    countdown,
                    // Days make it longer: one size down so it still fits on one line.
                    style = (if (days > 0) MaterialTheme.typography.displaySmall else MaterialTheme.typography.displayMedium)
                        .copy(fontFeatureSettings = "tnum"),
                    modifier = Modifier.semantics(mergeDescendants = true) { contentDescription = "Time left: $countdown" },
                )
                Text(
                    if (countdown == "now") " due now" else " left",
                    style = MaterialTheme.typography.titleMedium,
                    color = app.secondaryLabel,
                    modifier = Modifier.padding(bottom = 8.dp),
                )
            }
            Text(
                item.title ?: kindStyle(item.kind).label,
                style = MaterialTheme.typography.titleLarge,
                maxLines = 1,
                overflow = TextOverflow.Ellipsis,
                modifier = Modifier.padding(top = 6.dp),
            )
            Text(
                listOfNotNull(item.subject, kindStyle(item.kind).label).joinToString(" · "),
                style = MaterialTheme.typography.bodyMedium,
                color = app.secondaryLabel,
                maxLines = 1,
                overflow = TextOverflow.Ellipsis,
                modifier = Modifier.padding(top = 2.dp),
            )
        } else {
            NeoLabel("This week")
            Text("A clear week.", style = MaterialTheme.typography.displaySmall, modifier = Modifier.padding(top = 10.dp))
        }

        val subjects = cards.attendance.subjects
        if (withAttendance && subjects.isNotEmpty()) {
            val minimum = subjects.first().minimumPercent
            val above = subjects.count { it.percent >= it.minimumPercent }
            Row(Modifier.fillMaxWidth().padding(top = 34.dp), verticalAlignment = Alignment.Bottom) {
                Column(Modifier.weight(1f)) {
                    Text("$above/${subjects.size}", style = MaterialTheme.typography.displaySmall)
                    Text(
                        "subjects above ${pct(minimum)}%",
                        style = MaterialTheme.typography.bodyMedium,
                        color = app.secondaryLabel,
                        modifier = Modifier.padding(top = 4.dp),
                    )
                }
                MiniBars(subjects, minimum)
            }
        }
    }
}

/** One thin bar per subject, a faint line at the minimum; the ones under it in orange. */
@Composable
private fun MiniBars(subjects: List<SubjectAttendance>, minimum: Double) {
    val maxH = 52f
    val line = LocalAppColors.current.secondaryLabel
    val lineFromBottom = ((minimum - 50.0) / 50.0 * maxH).toFloat().coerceIn(0f, maxH)
    val label = subjects.joinToString(", ") { "${it.code} ${pct(it.percent)} percent" } + ". Line at ${pct(minimum)} percent."
    Row(
        Modifier
            .height(maxH.dp)
            .semantics { contentDescription = label }
            .drawBehind {
                val y = size.height - lineFromBottom.dp.toPx()
                drawLine(line.copy(alpha = 0.5f), Offset(0f, y), Offset(size.width, y), strokeWidth = 1.dp.toPx())
            },
        horizontalArrangement = Arrangement.spacedBy(7.dp),
        verticalAlignment = Alignment.Bottom,
    ) {
        subjects.take(8).forEach { s ->
            val h = (((s.percent - 50.0) / 50.0) * maxH).toFloat().coerceIn(6f, maxH)
            Box(
                Modifier
                    .width(7.dp)
                    .height(h.dp)
                    .clip(RoundedCornerShape(4.dp))
                    .background(if (s.percent < s.minimumPercent) Orange else NeoInk),
            )
        }
    }
}

/** Attendance: the subject that needs you most, as one huge number and its exact advice. */
@Composable
internal fun AttendanceHero(s: SubjectAttendance, modifier: Modifier = Modifier) {
    val app = LocalAppColors.current
    val low = s.percent < s.minimumPercent
    Column(modifier.fillMaxWidth().padding(top = 12.dp, bottom = 8.dp)) {
        NeoLabel(if (low) "Needs you · ${s.code}" else "Lowest · ${s.code}", dot = if (low) Orange else NeoInk)
        Row(Modifier.padding(top = 8.dp), verticalAlignment = Alignment.Bottom) {
            Text(String.format(Locale.ENGLISH, "%.1f", s.percent), style = MaterialTheme.typography.displayLarge)
            Text("%", style = MaterialTheme.typography.headlineSmall, modifier = Modifier.padding(start = 4.dp, bottom = 10.dp))
        }
        Text(s.name, style = MaterialTheme.typography.titleLarge, modifier = Modifier.padding(top = 14.dp))
        Text(
            "${s.attended} of ${s.held} classes attended",
            style = MaterialTheme.typography.bodyMedium,
            color = app.secondaryLabel,
            modifier = Modifier.padding(top = 2.dp),
        )
        LineWithMark(s.percent, s.minimumPercent, if (low) Orange else NeoInk, Modifier.padding(top = 26.dp))
        if (s.message.isNotBlank()) {
            Text(s.message, style = MaterialTheme.typography.titleLarge, modifier = Modifier.padding(top = 24.dp))
        }
    }
}

/** A 4 dp line filled to [percent], with an ink tick at [minimum]. */
@Composable
private fun LineWithMark(percent: Double, minimum: Double, color: Color, modifier: Modifier = Modifier) {
    val track = LocalAppColors.current.hairline
    BoxWithConstraints(modifier.fillMaxWidth().height(16.dp)) {
        Box(
            Modifier.align(Alignment.CenterStart).fillMaxWidth().height(4.dp).clip(CircleShape).background(track),
        )
        Box(
            Modifier
                .align(Alignment.CenterStart)
                .fillMaxWidth((percent / 100.0).toFloat().coerceIn(0f, 1f))
                .height(4.dp)
                .clip(CircleShape)
                .background(color),
        )
        Box(
            Modifier
                .offset(x = maxWidth * (minimum / 100.0).toFloat() - 1.dp)
                .width(2.dp)
                .height(16.dp)
                .background(NeoInk),
        )
    }
}

/** Inbox: how many things are worth the student's time, huge; what was kept out, quietly. */
@Composable
internal fun InboxHero(worth: Int, filtered: Int, modifier: Modifier = Modifier) {
    val app = LocalAppColors.current
    Column(modifier.fillMaxWidth().padding(top = 12.dp, bottom = 8.dp)) {
        NeoLabel("College mail", dot = if (filtered > 0) Orange else null)
        Text("$worth", style = MaterialTheme.typography.displayLarge, modifier = Modifier.padding(top = 8.dp))
        Text(
            if (worth == 1) "worth your time" else "worth your time",
            style = MaterialTheme.typography.titleLarge,
            modifier = Modifier.padding(top = 10.dp),
        )
        Text(
            filteredLine(filtered) + ". Paid \"placement\" offers and fake placement-cell mail never reach this list.",
            style = MaterialTheme.typography.bodyMedium,
            color = app.secondaryLabel,
            modifier = Modifier.padding(top = 4.dp),
        )
    }
}

/** One segment of a tab: its name and, when it has any, how many things are in it. */
internal data class Segment(val label: String, val count: Int = 0)

/**
 * The segmented control that organises a tab into a few short pages instead of one long scroll.
 * The current segment is an ink pill; the rest are quiet words.
 */
@Composable
internal fun NeoSegments(segments: List<Segment>, selected: Int, modifier: Modifier = Modifier, onSelect: (Int) -> Unit) {
    val app = LocalAppColors.current
    val haptics = androidx.compose.ui.platform.LocalHapticFeedback.current
    // Up to four share the width evenly, with one ink pill that slides between them on a spring;
    // more scroll sideways, each as wide as its words.
    val many = segments.size > 4
    val pick: (Int) -> Unit = { i ->
        if (i != selected) haptics.performHapticFeedback(androidx.compose.ui.hapticfeedback.HapticFeedbackType.TextHandleMove)
        onSelect(i)
    }
    if (!many) {
        androidx.compose.foundation.layout.BoxWithConstraints(
            modifier
                .fillMaxWidth()
                .padding(top = 2.dp, bottom = 6.dp)
                .glassSurface(shape = CircleShape)
                .padding(4.dp),
        ) {
            val slot = maxWidth / segments.size
            val x by androidx.compose.animation.core.animateDpAsState(
                slot * selected,
                androidx.compose.animation.core.spring(dampingRatio = 0.78f, stiffness = 420f),
                label = "segment pill",
            )
            Box(Modifier.offset(x = x).width(slot).height(40.dp).clip(CircleShape).background(NeoInk))
            Row(Modifier.fillMaxWidth()) {
                segments.forEachIndexed { i, seg -> SegmentLabel(seg, i == selected, Modifier.width(slot)) { pick(i) } }
            }
        }
        return
    }
    Row(
        modifier
            .fillMaxWidth()
            .padding(top = 2.dp, bottom = 6.dp)
            .glassSurface(shape = CircleShape)
            .horizontalScroll(rememberScrollState())
            .padding(4.dp),
        horizontalArrangement = Arrangement.spacedBy(2.dp),
    ) {
        segments.forEachIndexed { i, seg ->
            val on = i == selected
            val pill by androidx.compose.animation.animateColorAsState(if (on) NeoInk else Color.Transparent, label = "pill")
            SegmentLabel(seg, on, Modifier.clip(CircleShape).background(pill).padding(horizontal = 14.dp)) { pick(i) }
        }
    }
}

/** One segment's words; their colour eases between ink and light as the pill arrives. */
@Composable
private fun SegmentLabel(seg: Segment, on: Boolean, modifier: Modifier, onClick: () -> Unit) {
    val app = LocalAppColors.current
    val ink by androidx.compose.animation.animateColorAsState(if (on) com.sevenfive.app.ui.theme.NeoGround else NeoInk, label = "segment ink")
    Row(
        modifier
            .height(40.dp)
            .clip(CircleShape)
            .semantics(mergeDescendants = true) {
                this.selected = on
                role = androidx.compose.ui.semantics.Role.Tab
            }
            .clickable(onClick = onClick),
        horizontalArrangement = Arrangement.Center,
        verticalAlignment = Alignment.CenterVertically,
    ) {
        Text(
            seg.label,
            style = MaterialTheme.typography.labelMedium,
            fontWeight = if (on) androidx.compose.ui.text.font.FontWeight.SemiBold else androidx.compose.ui.text.font.FontWeight.Medium,
            color = ink,
            maxLines = 1,
            overflow = TextOverflow.Ellipsis,
        )
        if (seg.count > 0) {
            Spacer(Modifier.width(5.dp))
            Text(
                if (seg.count > 99) "99+" else "${seg.count}",
                style = MaterialTheme.typography.labelSmall,
                color = if (on) Orange else app.secondaryLabel,
            )
        }
    }
}

/**
 * Reminders, folded into Home: one row that says how many are set and which fires next, and
 * opens the full list. Keeps the tab bar to what's used every day.
 */
@Composable
internal fun RemindersEntry(reminders: List<com.sevenfive.app.data.Reminder>, modifier: Modifier = Modifier, onOpen: () -> Unit) {
    val app = LocalAppColors.current
    val now by rememberNow(30_000L)
    val next = reminders
        .mapNotNull { r -> Time.parse(r.firesAt)?.let { r to it } }
        .filter { it.second.toInstant().isAfter(now) }
        .minByOrNull { it.second }
    val line = when {
        next != null -> "Next: ${next.first.title ?: "a reminder"} · ${Time.until(next.second, now)}"
        reminders.isEmpty() -> "None set. Tap Remind me on anything due."
        else -> "${reminders.size} set"
    }
    Row(
        modifier
            .fillMaxWidth()
            .glassSurface(shape = MaterialTheme.shapes.large)
            .semantics(mergeDescendants = true) { role = androidx.compose.ui.semantics.Role.Button }
            .clickable(onClick = onOpen)
            .padding(horizontal = 18.dp, vertical = 16.dp),
        verticalAlignment = Alignment.CenterVertically,
    ) {
        androidx.compose.material3.Icon(
            androidx.compose.material.icons.Icons.Outlined.Alarm,
            contentDescription = null,
            tint = NeoInk,
            modifier = Modifier.size(22.dp),
        )
        Spacer(Modifier.width(14.dp))
        Column(Modifier.weight(1f)) {
            Text("Reminders", style = MaterialTheme.typography.titleMedium)
            Text(
                line,
                style = MaterialTheme.typography.bodySmall,
                color = app.secondaryLabel,
                maxLines = 1,
                overflow = TextOverflow.Ellipsis,
            )
        }
        if (reminders.isNotEmpty()) {
            Spacer(Modifier.width(10.dp))
            Box(
                Modifier.size(26.dp).clip(CircleShape).background(Orange),
                contentAlignment = Alignment.Center,
            ) {
                Text(
                    if (reminders.size > 9) "9+" else "${reminders.size}",
                    style = MaterialTheme.typography.labelMedium,
                    color = NeoInk,
                )
            }
        }
        Spacer(Modifier.width(6.dp))
        androidx.compose.material3.Icon(
            androidx.compose.material.icons.Icons.AutoMirrored.Outlined.KeyboardArrowRight,
            contentDescription = null,
            tint = app.secondaryLabel,
        )
    }
}

/** Two or more deadlines or exams close together: which ones, and what to do first. */
internal data class Clash(val items: List<Pair<com.sevenfive.app.data.Item, java.time.ZonedDateTime>>, val advice: String, val title: String)

private val dayName = DateTimeFormatter.ofPattern("EEE d", Locale.ENGLISH)

/** The first stretch where deadlines and exams fall within 48 hours of each other. */
internal fun findClash(items: List<com.sevenfive.app.data.Item>, now: java.time.Instant = java.time.Instant.now()): Clash? {
    val zone = ZoneId.systemDefault()
    val dated = items
        .filter { it.kind == "deadline" || it.kind == "exam" }
        .mapNotNull { item -> Time.parse(item.dueAt)?.atZoneSameInstant(zone)?.let { item to it } }
        .filter { it.second.toInstant().isAfter(now) }
        .sortedBy { it.second }
    var i = 0
    while (i < dated.size) {
        var j = i
        while (j + 1 < dated.size && java.time.Duration.between(dated[j].second, dated[j + 1].second).toHours() < 48) j++
        if (j > i) {
            val group = dated.subList(i, j + 1).take(4)
            val firstDay = group.first().second.toLocalDate()
            val lastDay = group.last().second.toLocalDate()
            val title = if (firstDay == lastDay) "${dayName.format(firstDay)} has ${group.size} things"
            else "${dayName.format(firstDay)} – ${dayName.format(lastDay)}: ${group.size} things"
            val exam = group.firstOrNull { it.first.kind == "exam" }
            val deadlines = group.filter { it.first.kind == "deadline" }
            val advice = when {
                exam != null && deadlines.isNotEmpty() ->
                    "Finish ${deadlines.first().first.title ?: "the submission"} early, so the day before " +
                        "${exam.first.title ?: "the exam"} is free to revise."
                exam != null -> "Two exams close together: split your revision across both from today."
                else -> "Start ${group.first().first.title ?: "the first one"} now, then ${group[1].first.title ?: "the next"}."
            }
            return Clash(group, advice, title)
        }
        i = j + 1
    }
    return null
}

@Composable
internal fun ClashCard(clash: Clash, modifier: Modifier = Modifier) {
    val app = LocalAppColors.current
    Column(
        modifier
            .fillMaxWidth()
            .glassSurface(shape = MaterialTheme.shapes.large)
            .padding(18.dp),
    ) {
        NeoLabel("Busy stretch", dot = Orange)
        Text(clash.title, style = MaterialTheme.typography.titleLarge, modifier = Modifier.padding(top = 8.dp))
        clash.items.forEach { (item, at) ->
            Row(Modifier.padding(top = 6.dp), verticalAlignment = Alignment.CenterVertically) {
                Text(
                    "${dayName.format(at)} ${at.format(hourMinute)}",
                    style = MaterialTheme.typography.bodySmall.copy(fontFeatureSettings = "tnum"),
                    color = app.secondaryLabel,
                    modifier = Modifier.width(86.dp),
                )
                Text(
                    item.title ?: kindStyle(item.kind).label,
                    style = MaterialTheme.typography.bodyMedium,
                    maxLines = 1,
                    overflow = TextOverflow.Ellipsis,
                    modifier = Modifier.weight(1f),
                )
                Text(kindStyle(item.kind).label, style = MaterialTheme.typography.labelSmall, color = app.secondaryLabel)
            }
        }
        Text(clash.advice, style = MaterialTheme.typography.bodyMedium, fontWeight = androidx.compose.ui.text.font.FontWeight.Medium,
            modifier = Modifier.padding(top = 12.dp))
    }
}

/** "12 of 14 done on time this month": quiet, from what this phone has seen. */
@Composable
internal fun DoneHistory(month: com.sevenfive.app.data.LocalLog.Month, modifier: Modifier = Modifier) {
    val app = LocalAppColors.current
    Row(modifier.fillMaxWidth().padding(top = 4.dp), verticalAlignment = Alignment.CenterVertically) {
        Text("${month.onTime} of ${month.total}", style = MaterialTheme.typography.titleMedium)
        Text(
            " deadlines done on time this month",
            style = MaterialTheme.typography.bodyMedium,
            color = app.secondaryLabel,
            modifier = Modifier.weight(1f),
        )
        // A small ring of how much was on time.
        val share = if (month.total > 0) month.onTime.toFloat() / month.total else 0f
        androidx.compose.foundation.Canvas(Modifier.size(22.dp)) {
            val stroke = 3.dp.toPx()
            val box = androidx.compose.ui.geometry.Size(size.width - stroke, size.height - stroke)
            val tl = Offset(stroke / 2, stroke / 2)
            drawArc(app.hairline, 0f, 360f, false, tl, box, style = androidx.compose.ui.graphics.drawscope.Stroke(stroke))
            drawArc(NeoInk, -90f, 360f * share, false, tl, box,
                style = androidx.compose.ui.graphics.drawscope.Stroke(stroke, cap = androidx.compose.ui.graphics.StrokeCap.Round))
        }
    }
}
