package com.sevenfive.app.ui.screens

import androidx.compose.foundation.background
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
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.sevenfive.app.data.Cards
import com.sevenfive.app.data.SubjectAttendance
import com.sevenfive.app.ui.components.kindStyle
import com.sevenfive.app.ui.theme.LocalAppColors
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
internal fun HomeHero(cards: Cards, modifier: Modifier = Modifier) {
    val app = LocalAppColors.current
    val zone = ZoneId.systemDefault()
    val next = cards.dueThisWeek
        .mapNotNull { item -> Time.parse(item.dueAt)?.let { item to it.atZoneSameInstant(zone) } }
        .minByOrNull { it.second }
    Column(modifier.fillMaxWidth().padding(start = 4.dp, end = 4.dp, top = 12.dp, bottom = 8.dp)) {
        if (next != null) {
            val (item, at) = next
            NeoLabel("Next", dot = Orange)
            Text(
                dayWord(at.toLocalDate()) + "\n" + at.format(hourMinute),
                style = MaterialTheme.typography.displayMedium,
                modifier = Modifier.padding(top = 10.dp),
            )
            Text(
                item.title ?: kindStyle(item.kind).label,
                style = MaterialTheme.typography.titleLarge,
                maxLines = 2,
                overflow = TextOverflow.Ellipsis,
                modifier = Modifier.padding(top = 16.dp),
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
        if (subjects.isNotEmpty()) {
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
                drawLine(line.copy(alpha = 0.5f), Offset(-6.dp.toPx(), y), Offset(size.width + 6.dp.toPx(), y), strokeWidth = 1.dp.toPx())
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
    Column(modifier.fillMaxWidth().padding(start = 4.dp, end = 4.dp, top = 12.dp, bottom = 8.dp)) {
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
    Column(modifier.fillMaxWidth().padding(start = 4.dp, end = 4.dp, top = 12.dp, bottom = 8.dp)) {
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
