package com.sevenfive.app.ui.screens

import androidx.compose.foundation.Canvas
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.outlined.Link
import androidx.compose.material.icons.outlined.Lock
import androidx.compose.material.icons.outlined.Refresh
import androidx.compose.material.icons.outlined.School
import androidx.compose.material3.Button
import androidx.compose.material3.Icon
import androidx.compose.material3.LinearProgressIndicator
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.geometry.CornerRadius
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.geometry.Size
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import com.sevenfive.app.data.Attendance
import com.sevenfive.app.data.SubjectAttendance
import com.sevenfive.app.portal.PortalStatus
import com.sevenfive.app.ui.AppViewModel
import com.sevenfive.app.ui.components.AppCard
import com.sevenfive.app.ui.components.Dot
import com.sevenfive.app.ui.theme.LocalStatusColors
import com.sevenfive.app.ui.components.ScreenPadding
import com.sevenfive.app.ui.components.SectionHeader
import com.sevenfive.app.ui.components.TabScaffold
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

    TabScaffold("Attendance", vm, onSettings) {
        if (attendance == null) {
            LoadingOrError(state.loading)
            return@TabScaffold
        }
        val subjects = worstFirst(attendance.subjects)
        LazyColumn(contentPadding = ScreenPadding, verticalArrangement = Arrangement.spacedBy(10.dp)) {
            item { PortalCard(attendance, portal, onPortal) }
            if (subjects.isNotEmpty()) {
                val short = subjects.count { it.status == "short" || it.status == "unrecoverable" }
                item {
                    SectionHeader(
                        if (short == 0) "All subjects" else "$short below ${minimumOf(subjects)}%"
                    )
                }
                items(subjects, key = { it.code }) { SubjectCard(it) }
            }
        }
    }
}

private fun minimumOf(subjects: List<SubjectAttendance>) =
    subjects.firstOrNull()?.minimumPercent?.let { pct(it) } ?: "75"

private fun pct(v: Double): String =
    if (v % 1.0 == 0.0) v.toInt().toString() else String.format(Locale.ENGLISH, "%.2f", v).trimEnd('0').trimEnd('.')

@Composable
private fun PortalCard(attendance: Attendance, portal: PortalStatus, onPortal: () -> Unit) {
    val fetched = Time.parse(attendance.fetchedAt)?.toInstant()
    AppCard(muted = attendance.connected && !portal.needsLogin) {
        Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
            when {
                portal.needsLogin -> {
                    Header(Icons.Outlined.Lock, "Log in to your portal again",
                        "Your portal session ended. Log in once and attendance refreshes from your phone.")
                    Button(onClick = onPortal) { Text("Log in to portal") }
                }
                !attendance.connected -> {
                    Header(Icons.Outlined.Link, "Connect your portal",
                        "Log in on your college portal's own page, inside this app. We never see or store " +
                            "your password; the session stays on this phone.")
                    Button(onClick = onPortal) { Text("Connect portal") }
                }
                else -> {
                    Row(verticalAlignment = Alignment.CenterVertically) {
                        Icon(Icons.Outlined.School, contentDescription = null, tint = MaterialTheme.colorScheme.primary)
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
                                color = if (attendance.stale) MaterialTheme.colorScheme.error
                                else MaterialTheme.colorScheme.onSurfaceVariant,
                            )
                        }
                        OutlinedButton(onClick = onPortal, enabled = !portal.busy) {
                            Icon(Icons.Outlined.Refresh, contentDescription = null, modifier = Modifier.size(18.dp))
                            Spacer(Modifier.width(6.dp))
                            Text("Refresh")
                        }
                    }
                }
            }
            if (portal.busy) {
                LinearProgressIndicator(Modifier.fillMaxWidth())
                Text("Refreshing from the portal…", style = MaterialTheme.typography.bodySmall)
            } else if (portal.lastError != null) {
                Text(portal.lastError, style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.error)
            }
        }
    }
}

@Composable
private fun Header(icon: androidx.compose.ui.graphics.vector.ImageVector, title: String, body: String) {
    Row(verticalAlignment = Alignment.Top) {
        Icon(icon, contentDescription = null, tint = MaterialTheme.colorScheme.primary)
        Spacer(Modifier.width(12.dp))
        Column {
            Text(title, style = MaterialTheme.typography.titleMedium)
            Text(body, style = MaterialTheme.typography.bodyMedium, color = MaterialTheme.colorScheme.onSurfaceVariant)
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
private fun SubjectCard(s: SubjectAttendance) {
    val color = LocalStatusColors.current.of(s.status)
    AppCard {
        Column(verticalArrangement = Arrangement.spacedBy(6.dp)) {
            Row(verticalAlignment = Alignment.CenterVertically) {
                Column(Modifier.weight(1f)) {
                    Text(s.name, style = MaterialTheme.typography.titleMedium)
                    Row(verticalAlignment = Alignment.CenterVertically) {
                        Text(s.code, style = MaterialTheme.typography.labelMedium,
                            color = MaterialTheme.colorScheme.onSurfaceVariant)
                        Spacer(Modifier.width(8.dp))
                        Dot(color)
                        Spacer(Modifier.width(4.dp))
                        Text(statusLabel(s.status), style = MaterialTheme.typography.labelMedium, color = color)
                    }
                }
                Column(horizontalAlignment = Alignment.End) {
                    Text("${pct(s.percent)}%", style = MaterialTheme.typography.headlineSmall,
                        fontWeight = FontWeight.Bold, color = color)
                    Text("${s.attended}/${s.held} classes", style = MaterialTheme.typography.labelSmall,
                        color = MaterialTheme.colorScheme.onSurfaceVariant)
                }
            }
            AttendanceBar(s.percent, s.minimumPercent, color)
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
                Text(extra.joinToString(" · "), style = MaterialTheme.typography.bodySmall,
                    color = MaterialTheme.colorScheme.onSurfaceVariant)
            }
        }
    }
}

/** A bar with a tick at the minimum, so "how far from 75%" is visible at a glance. */
@Composable
private fun AttendanceBar(percent: Double, minimum: Double, color: androidx.compose.ui.graphics.Color) {
    val track = MaterialTheme.colorScheme.surfaceVariant
    val tick = MaterialTheme.colorScheme.onSurface
    Canvas(Modifier.fillMaxWidth().height(10.dp)) {
        val r = CornerRadius(size.height / 2, size.height / 2)
        drawRoundRect(track, cornerRadius = r)
        val w = (percent / 100.0).coerceIn(0.0, 1.0).toFloat() * size.width
        drawRoundRect(color, size = Size(w, size.height), cornerRadius = r)
        val x = (minimum / 100.0).coerceIn(0.0, 1.0).toFloat() * size.width
        drawLine(tick, Offset(x, -2f), Offset(x, size.height + 2f), strokeWidth = 2.dp.toPx())
    }
}

