package com.sevenfive.app.ui.screens

import androidx.compose.foundation.Canvas
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.BoxWithConstraints
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxHeight
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.offset
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.PlayArrow
import androidx.compose.material3.Icon
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.geometry.Size
import androidx.compose.ui.graphics.StrokeCap
import androidx.compose.ui.graphics.drawscope.Stroke
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.Dp
import androidx.compose.ui.unit.dp
import com.sevenfive.app.data.SubjectAttendance
import com.sevenfive.app.ui.theme.LocalAppColors
import com.sevenfive.app.ui.theme.NeoGround
import com.sevenfive.app.ui.theme.NeoInk
import com.sevenfive.app.ui.theme.Orange
import com.sevenfive.app.ui.theme.glassSurface
import com.sevenfive.app.ui.theme.pressable
import java.time.Duration
import java.time.format.DateTimeFormatter
import java.util.Locale

/*
 * Today as a bento, not a grid: tiles of different sizes, each with its own small picture and a
 * line said the way a person would say it. One dark strip (Your day) and the orange touches give
 * the screen a centre of gravity instead of six equal boxes.
 */

private val SKIP = setOf("and", "of", "the", "&", "to", "for", "in")

/** "Database Management Systems" -> "DBMS"; a one-word name stays as it is. */
internal fun shortName(name: String, code: String): String {
    val words = name.split(' ', '-').filter { it.isNotBlank() && it.lowercase() !in SKIP }
    if (words.size < 2) return name.ifBlank { code }
    // Mostly initials; "Database" is "DB" the way students say it (DBMS).
    return words.joinToString("") { w -> if (w.equals("database", ignoreCase = true)) "DB" else w.first().uppercase() }
}

private val dayShort = DateTimeFormatter.ofPattern("EEE d", Locale.ENGLISH)

/** The attendance tile: how many subjects are above the line, the bars, and who needs you. */
@Composable
internal fun AttendanceBento(subjects: List<SubjectAttendance>, modifier: Modifier = Modifier, onClick: () -> Unit) {
    val app = LocalAppColors.current
    val above = subjects.count { it.percent >= it.minimumPercent }
    val worst = subjects.minByOrNull { it.percent }
    val low = worst != null && worst.percent < worst.minimumPercent
    Column(
        modifier
            .pressable(scaleTo = 0.97f, onClick = onClick)
            .glassSurface(shape = RoundedCornerShape(28.dp))
            .padding(horizontal = 18.dp, vertical = 16.dp),
    ) {
        NeoLabel("Attendance", dot = if (low) Orange else null)
        Spacer(Modifier.weight(1f))
        Row(verticalAlignment = Alignment.Bottom) {
            Text(if (subjects.isEmpty()) "—" else "$above", style = MaterialTheme.typography.headlineLarge)
            if (subjects.isNotEmpty()) {
                Text("/${subjects.size}", style = MaterialTheme.typography.titleMedium,
                    color = app.secondaryLabel, modifier = Modifier.padding(bottom = 4.dp))
                Spacer(Modifier.width(12.dp))
                Bars(subjects, subjects.first().minimumPercent, Modifier.weight(1f).height(30.dp))
            }
        }
        Text(
            when {
                worst == null -> "connect the portal"
                low -> "${shortName(worst.name, worst.code)} needs you"
                else -> "all above ${pct(worst.minimumPercent)}%"
            },
            style = MaterialTheme.typography.bodySmall,
            color = if (low) com.sevenfive.app.ui.theme.LocalStatusColors.current.short else app.secondaryLabel,
            maxLines = 1,
            overflow = TextOverflow.Ellipsis,
            modifier = Modifier.padding(top = 8.dp),
        )
    }
}

@Composable
private fun Bars(subjects: List<SubjectAttendance>, minimum: Double, modifier: Modifier) {
    val line = LocalAppColors.current.secondaryLabel
    val label = subjects.joinToString(", ") { "${it.code} ${pct(it.percent)} percent" }
    Canvas(modifier.semantics { contentDescription = label }) {
        val n = subjects.size.coerceAtMost(8)
        val gap = 6.dp.toPx()
        val w = ((size.width - gap * (n - 1)) / n).coerceAtMost(10.dp.toPx())
        val y75 = size.height * (1f - ((minimum - 50.0) / 50.0).toFloat().coerceIn(0f, 1f))
        drawLine(line.copy(alpha = 0.45f), Offset(0f, y75), Offset(size.width, y75), strokeWidth = 1.dp.toPx())
        subjects.take(n).forEachIndexed { i, s ->
            val h = (size.height * ((s.percent - 50.0) / 50.0).toFloat()).coerceIn(4.dp.toPx(), size.height)
            val x = i * (w + gap) + w / 2
            drawLine(
                if (s.percent < s.minimumPercent) Orange else NeoInk,
                Offset(x, size.height), Offset(x, size.height - h),
                strokeWidth = w, cap = StrokeCap.Round,
            )
        }
    }
}

/** The busy-stretch tile: one line, a little timeline, how many of each kind; names in the sheet. */
@Composable
internal fun ClashBento(clash: Clash?, modifier: Modifier = Modifier, onClick: () -> Unit) {
    val app = LocalAppColors.current
    Column(
        modifier
            .pressable(scaleTo = 0.97f, onClick = onClick)
            .glassSurface(shape = RoundedCornerShape(28.dp))
            .padding(horizontal = 18.dp, vertical = 16.dp),
    ) {
        NeoLabel(if (clash == null) "This week" else "Busy stretch", dot = if (clash != null) Orange else null)
        Spacer(Modifier.weight(1f))
        if (clash == null) {
            Text("Spread out", style = MaterialTheme.typography.titleLarge, maxLines = 1)
            Text("nothing bunched up", style = MaterialTheme.typography.bodySmall, color = app.secondaryLabel,
                modifier = Modifier.padding(top = 8.dp))
            return@Column
        }
        Text("${clash.items.size} in ${days(clash)}", style = MaterialTheme.typography.titleLarge, maxLines = 1)
        Timeline(clash, Modifier.fillMaxWidth().padding(top = 10.dp).height(14.dp))
        val exams = clash.items.count { it.first.kind == "exam" }
        val rest = clash.items.size - exams
        Text(
            listOfNotNull(
                exams.takeIf { it > 0 }?.let { if (it == 1) "1 exam" else "$it exams" },
                rest.takeIf { it > 0 }?.let { if (it == 1) "1 deadline" else "$it deadlines" },
            ).joinToString(" · ") + " · " + dayShort.format(clash.items.first().second),
            style = MaterialTheme.typography.bodySmall,
            color = app.secondaryLabel,
            maxLines = 1,
            overflow = TextOverflow.Ellipsis,
            modifier = Modifier.padding(top = 8.dp),
        )
    }
}

private fun days(clash: Clash): String {
    val first = clash.items.first().second.toLocalDate()
    val last = clash.items.last().second.toLocalDate()
    val n = java.time.temporal.ChronoUnit.DAYS.between(first, last) + 1
    return if (n <= 1) "one day" else "$n days"
}

/** Dots on a line from the first to the last: exams orange, the rest ink. */
@Composable
private fun Timeline(clash: Clash, modifier: Modifier) {
    val app = LocalAppColors.current
    val start = clash.items.first().second
    val end = clash.items.last().second
    val span = Duration.between(start, end).toMinutes().coerceAtLeast(1).toFloat()
    Canvas(modifier) {
        val y = size.height / 2
        drawLine(app.hairline, Offset(0f, y), Offset(size.width, y), strokeWidth = 2.dp.toPx(), cap = StrokeCap.Round)
        clash.items.forEach { (item, at) ->
            val f = Duration.between(start, at).toMinutes() / span
            val x = 5.dp.toPx() + f * (size.width - 10.dp.toPx())
            drawCircle(if (item.kind == "exam") Orange else NeoInk, radius = 5.dp.toPx(), center = Offset(x, y))
        }
    }
}

/** The dark strip: the one inverted surface on the screen, an orange play button, a greeting. */
@Composable
internal fun YourDayStrip(greeting: String, modifier: Modifier = Modifier, onClick: () -> Unit) {
    Row(
        modifier
            .fillMaxWidth()
            .height(64.dp)
            .pressable(scaleTo = 0.98f, haptic = true, onClick = onClick)
            .clip(RoundedCornerShape(32.dp))
            .background(NeoInk)
            .padding(start = 9.dp, end = 22.dp),
        verticalAlignment = Alignment.CenterVertically,
    ) {
        Box(Modifier.size(46.dp).clip(CircleShape).background(Orange), contentAlignment = Alignment.Center) {
            Icon(Icons.Filled.PlayArrow, contentDescription = "Play your day", tint = NeoInk, modifier = Modifier.size(24.dp))
        }
        Spacer(Modifier.width(14.dp))
        Column(Modifier.weight(1f)) {
            Text(greeting, style = MaterialTheme.typography.titleMedium, color = NeoGround, maxLines = 1, overflow = TextOverflow.Ellipsis)
            Text("your day, read aloud · about a minute", style = MaterialTheme.typography.bodySmall,
                color = NeoGround.copy(alpha = 0.7f), maxLines = 1, overflow = TextOverflow.Ellipsis)
        }
    }
}

/** A small chip: a word, a value, and (optionally) a ring. Three sit side by side. */
@Composable
internal fun MiniBento(label: String, value: String, caption: String, modifier: Modifier = Modifier, ring: Float? = null, onClick: () -> Unit) {
    val app = LocalAppColors.current
    Column(
        modifier
            .height(84.dp)
            .pressable(scaleTo = 0.96f, onClick = onClick)
            .glassSurface(shape = RoundedCornerShape(24.dp))
            .padding(horizontal = 14.dp, vertical = 10.dp),
        verticalArrangement = Arrangement.SpaceBetween,
    ) {
        Text(label.uppercase(), style = MaterialTheme.typography.labelSmall, color = app.secondaryLabel, maxLines = 1)
        Row(verticalAlignment = Alignment.CenterVertically) {
            Text(value, style = MaterialTheme.typography.titleLarge, maxLines = 1, modifier = Modifier.weight(1f, fill = false))
            if (ring != null) {
                Spacer(Modifier.width(8.dp))
                Ring(ring, 20.dp)
            }
        }
        Text(caption, style = MaterialTheme.typography.labelSmall, color = app.secondaryLabel, maxLines = 1, overflow = TextOverflow.Ellipsis)
    }
}

@Composable
private fun Ring(share: Float, size: Dp) {
    val track = LocalAppColors.current.hairline
    Canvas(Modifier.size(size)) {
        val stroke = 3.dp.toPx()
        val box = Size(this.size.width - stroke, this.size.height - stroke)
        val tl = Offset(stroke / 2, stroke / 2)
        drawArc(track, 0f, 360f, false, tl, box, style = Stroke(stroke))
        drawArc(NeoInk, -90f, 360f * share.coerceIn(0f, 1f), false, tl, box, style = Stroke(stroke, cap = StrokeCap.Round))
    }
}


/** One quiet stat in a row of three: no box, just a small label over a value. */
@Composable
internal fun QuietStat(label: String, value: String, modifier: Modifier = Modifier, ring: Float? = null, onClick: () -> Unit) {
    val app = LocalAppColors.current
    Column(
        modifier
            .clip(RoundedCornerShape(16.dp))
            .pressable(scaleTo = 0.96f, onClick = onClick)
            .padding(vertical = 8.dp, horizontal = 4.dp),
    ) {
        Text(label.uppercase(), style = MaterialTheme.typography.labelSmall, color = app.secondaryLabel, maxLines = 1)
        Row(verticalAlignment = Alignment.CenterVertically, modifier = Modifier.padding(top = 4.dp)) {
            Text(value, style = MaterialTheme.typography.titleMedium, maxLines = 1, overflow = TextOverflow.Ellipsis)
            if (ring != null) {
                Spacer(Modifier.width(6.dp))
                Ring(ring, 14.dp)
            }
        }
    }
}
