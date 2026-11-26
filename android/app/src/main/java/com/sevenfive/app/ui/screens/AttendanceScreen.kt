package com.sevenfive.app.ui.screens

import androidx.compose.animation.core.Animatable
import androidx.compose.animation.core.Spring
import androidx.compose.animation.core.spring
import androidx.compose.foundation.Canvas
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
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.itemsIndexed
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.outlined.Link
import androidx.compose.material.icons.outlined.Lock
import androidx.compose.material.icons.outlined.Refresh
import androidx.compose.material.icons.outlined.School
import androidx.compose.material3.LinearProgressIndicator
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.remember
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.geometry.Size
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.StrokeCap
import androidx.compose.ui.graphics.drawscope.Stroke
import androidx.compose.ui.graphics.vector.ImageVector
import androidx.compose.ui.graphics.drawscope.rotate
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.Dp
import androidx.compose.ui.unit.dp
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import com.sevenfive.app.data.Attendance
import com.sevenfive.app.data.SubjectAttendance
import com.sevenfive.app.portal.PortalStatus
import com.sevenfive.app.ui.AppViewModel
import com.sevenfive.app.ui.components.AppCard
import com.sevenfive.app.ui.components.Dot
import com.sevenfive.app.ui.components.GlassPill
import com.sevenfive.app.ui.components.IconTile
import com.sevenfive.app.ui.components.PrimaryPill
import com.sevenfive.app.ui.components.ScreenIntro
import com.sevenfive.app.ui.components.SectionHeader
import com.sevenfive.app.ui.components.TabScaffold
import com.sevenfive.app.ui.components.uniqueKeys
import com.sevenfive.app.ui.theme.LocalAppColors
import com.sevenfive.app.ui.theme.LocalStatusColors
import com.sevenfive.app.ui.theme.Motion
import com.sevenfive.app.util.Time
import java.util.Locale

private val severity = mapOf("unrecoverable" to 0, "short" to 1, "at_risk" to 2, "safe" to 3)

/** Worst first: status, then lowest percent. PortMax already sorts; this keeps it true. */
fun worstFirst(subjects: List<SubjectAttendance>): List<SubjectAttendance> =
    subjects.sortedWith(compareBy<SubjectAttendance>({ severity[it.status] ?: 0 }, { it.percent }))

@Composable
fun AttendanceScreen(vm: AppViewModel, onSettings: () -> Unit, onPortal: () -> Unit) {
    val state by vm.cards.collectAsStateWithLifecycle()
    val portal by vm.portal.collectAsStateWithLifecycle()
    val attendance = state.cards?.attendance

    TabScaffold("Attendance", vm, onSettings) { padding ->
        if (attendance == null) {
            LoadingOrError(state.loading, padding)
            return@TabScaffold
        }
        val subjects = worstFirst(attendance.subjects)
        LazyColumn(contentPadding = padding, verticalArrangement = Arrangement.spacedBy(10.dp)) {
            item(key = "intro") { ScreenIntro("Worst subject first, with exactly what to do.") }
            item(key = "portal") { PortalCard(attendance, portal, onPortal, Modifier.animateItem(placementSpec = Motion.item)) }
            if (subjects.isNotEmpty()) {
                val short = subjects.count { it.status == "short" || it.status == "unrecoverable" }
                item(key = "header") {
                    SectionHeader(
                        if (short == 0) "All subjects" else "$short below ${minimumOf(subjects)}%",
                        Modifier.animateItem(placementSpec = Motion.item),
                    )
                }
                // A code can repeat (a theory and a lab paper, or a portal page with no codes).
                val keys = uniqueKeys(subjects) { it.code }
                itemsIndexed(subjects, key = { i, _ -> keys[i] }) { _, subject ->
                    SubjectCard(subject, Modifier.animateItem(placementSpec = Motion.item))
                }
            }
        }
    }
}

private fun minimumOf(subjects: List<SubjectAttendance>) =
    subjects.firstOrNull()?.minimumPercent?.let { pct(it) } ?: "75"

private fun pct(v: Double): String =
    if (v % 1.0 == 0.0) v.toInt().toString() else String.format(Locale.ENGLISH, "%.2f", v).trimEnd('0').trimEnd('.')

@Composable
private fun PortalCard(attendance: Attendance, portal: PortalStatus, onPortal: () -> Unit, modifier: Modifier = Modifier) {
    val fetched = Time.parse(attendance.fetchedAt)?.toInstant()
    val app = LocalAppColors.current
    AppCard(modifier) {
        Column(verticalArrangement = Arrangement.spacedBy(12.dp)) {
            when {
                portal.needsLogin -> {
                    Header(Icons.Outlined.Lock, MaterialTheme.colorScheme.error, "Log in to your portal again",
                        "Your portal session ended. Log in once and attendance refreshes from your phone.")
                    PrimaryPill("Log in to portal", onClick = onPortal)
                }
                !attendance.connected -> {
                    Header(Icons.Outlined.Link, app.material, "Connect your portal",
                        "Log in on your college portal's own page, inside this app. We never see or store " +
                            "your password; the session stays on this phone.")
                    PrimaryPill("Connect portal", onClick = onPortal)
                }
                else -> {
                    Row(verticalAlignment = Alignment.CenterVertically) {
                        IconTile(Icons.Outlined.School, app.material, size = 36.dp)
                        Spacer(Modifier.width(12.dp))
                        Column(Modifier.weight(1f)) {
                            Text("From your college portal", style = MaterialTheme.typography.titleSmall)
                            Text(
                                when {
                                    fetched == null -> "Updated recently"
                                    attendance.stale -> "Last updated ${Time.ago(fetched)}: may be out of date"
                                    else -> "Updated ${Time.ago(fetched)}"
                                },
                                style = MaterialTheme.typography.bodySmall,
                                color = if (attendance.stale) MaterialTheme.colorScheme.error else app.secondaryLabel,
                            )
                        }
                        GlassPill("Refresh", onClick = onPortal, enabled = !portal.busy, icon = Icons.Outlined.Refresh)
                    }
                }
            }
            if (portal.busy) {
                LinearProgressIndicator(
                    Modifier.fillMaxWidth().height(4.dp),
                    color = MaterialTheme.colorScheme.primary,
                    trackColor = app.hairline,
                    strokeCap = StrokeCap.Round,
                    gapSize = 0.dp,
                )
                Text("Refreshing from the portal…", style = MaterialTheme.typography.bodySmall, color = app.secondaryLabel)
            } else if (portal.lastError != null) {
                Text(portal.lastError, style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.error)
            }
        }
    }
}

@Composable
private fun Header(icon: ImageVector, color: Color, title: String, body: String) {
    Row(verticalAlignment = Alignment.Top) {
        IconTile(icon, color, size = 36.dp)
        Spacer(Modifier.width(12.dp))
        Column {
            Text(title, style = MaterialTheme.typography.titleMedium)
            Text(body, style = MaterialTheme.typography.bodyMedium, color = LocalAppColors.current.secondaryLabel)
        }
    }
}

private fun statusLabel(status: String) = when (status) {
    "safe" -> "Safe"
    "at_risk" -> "At risk"
    "short" -> "Short"
    "unrecoverable" -> "Can't recover"
    else -> status
}

@Composable
private fun SubjectCard(s: SubjectAttendance, modifier: Modifier = Modifier) {
    val color = LocalStatusColors.current.of(s.status)
    val app = LocalAppColors.current
    AppCard(modifier) {
        Column(verticalArrangement = Arrangement.spacedBy(10.dp)) {
            Row(verticalAlignment = Alignment.CenterVertically) {
                AttendanceRing(s.percent, s.minimumPercent, color)
                Spacer(Modifier.width(14.dp))
                Column(Modifier.weight(1f)) {
                    Text(s.name, style = MaterialTheme.typography.titleMedium)
                    Row(verticalAlignment = Alignment.CenterVertically, modifier = Modifier.padding(top = 2.dp)) {
                        Dot(color)
                        Spacer(Modifier.width(5.dp))
                        Text(statusLabel(s.status), style = MaterialTheme.typography.labelMedium, color = color)
                        Text(
                            "  ·  ${s.code}  ·  ${s.attended}/${s.held} classes",
                            style = MaterialTheme.typography.labelMedium,
                            color = app.secondaryLabel,
                        )
                    }
                }
            }
            // Exact and written by code, not a model: shown word for word.
            Text(s.message, style = MaterialTheme.typography.bodyMedium)
            val next = s.nextClasses.mapNotNull { Time.parseDate(it) }.take(3)
            val extra = buildList {
                if (next.isNotEmpty()) add("Next: " + next.joinToString(", ") { Time.dayOnly(it) })
                s.semester?.let { sem ->
                    if (sem.canSkipRest != null && sem.remaining != null) {
                        add("Can miss ${sem.canSkipRest} of ${sem.remaining} left")
                    }
                    sem.bestFinalPercent?.let { add("Best possible ${pct(it)}%") }
                }
            }
            if (extra.isNotEmpty()) {
                Text(extra.joinToString(" · "), style = MaterialTheme.typography.bodySmall, color = app.secondaryLabel)
            }
        }
    }
}

/**
 * An activity-style ring: the percent attended sweeps in on a spring when it first shows, with a
 * small tick at the minimum, so "how far from 75%" reads at a glance.
 */
@Composable
private fun AttendanceRing(percent: Double, minimum: Double, color: Color, size: Dp = 62.dp) {
    val target = (percent / 100.0).coerceIn(0.0, 1.0).toFloat()
    val sweep = remember { Animatable(0f) }
    LaunchedEffect(target) { sweep.animateTo(target, spring(dampingRatio = 0.9f, stiffness = Spring.StiffnessVeryLow)) }
    val track = color.copy(alpha = 0.16f)
    val tick = MaterialTheme.colorScheme.onSurface.copy(alpha = 0.55f)
    Box(Modifier.size(size), contentAlignment = Alignment.Center) {
        Canvas(Modifier.size(size)) {
            val stroke = 7.dp.toPx()
            val inset = stroke / 2
            val arc = Size(this.size.width - stroke, this.size.height - stroke)
            val topLeft = Offset(inset, inset)
            drawArc(track, 0f, 360f, useCenter = false, topLeft = topLeft, size = arc, style = Stroke(stroke))
            rotate(-90f) {
                drawArc(
                    Brush.sweepGradient(listOf(color.copy(alpha = 0.7f), color, color.copy(alpha = 0.7f))),
                    0f,
                    360f * sweep.value,
                    useCenter = false,
                    topLeft = topLeft,
                    size = arc,
                    style = Stroke(stroke, cap = StrokeCap.Round),
                )
                // The minimum, as a short tick across the ring.
                val angle = Math.toRadians(360.0 * (minimum / 100.0).coerceIn(0.0, 1.0))
                val r = arc.width / 2
                val c = center
                val inner = r - stroke * 0.75f
                val outer = r + stroke * 0.75f
                val dx = kotlin.math.cos(angle).toFloat()
                val dy = kotlin.math.sin(angle).toFloat()
                drawLine(tick, Offset(c.x + dx * inner, c.y + dy * inner), Offset(c.x + dx * outer, c.y + dy * outer), 2.dp.toPx(), StrokeCap.Round)
            }
        }
        Text(
            "${pct(percent)}%".let { if (it.length > 5) "${percent.toInt()}%" else it },
            style = MaterialTheme.typography.labelLarge,
            fontWeight = FontWeight.Bold,
            color = color,
        )
    }
}
