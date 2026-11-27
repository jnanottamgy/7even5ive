package com.sevenfive.app.ui.screens

import androidx.compose.animation.animateColorAsState
import androidx.compose.foundation.Canvas
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.LazyRow
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.outlined.CalendarMonth
import androidx.compose.material.icons.outlined.EventBusy
import androidx.compose.material.icons.outlined.Grade
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableIntStateOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.geometry.CornerRadius
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.geometry.Size
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.dp
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import com.sevenfive.app.data.Cards
import com.sevenfive.app.data.Slot
import com.sevenfive.app.data.SubjectAttendance
import com.sevenfive.app.ui.AppViewModel
import com.sevenfive.app.ui.components.AppCard
import com.sevenfive.app.ui.components.Dot
import com.sevenfive.app.ui.components.EmptyState
import com.sevenfive.app.ui.components.PushScaffold
import com.sevenfive.app.ui.components.SectionHeader
import com.sevenfive.app.ui.components.SlimBar
import com.sevenfive.app.ui.theme.LocalAppColors
import com.sevenfive.app.ui.theme.LocalStatusColors
import com.sevenfive.app.ui.theme.glassSurface
import com.sevenfive.app.ui.theme.pressable
import com.sevenfive.app.util.Week
import java.time.DayOfWeek
import java.time.LocalDate
import java.time.LocalDateTime
import java.time.LocalTime
import java.time.format.DateTimeFormatter
import java.util.Locale

private val dayChip = DateTimeFormatter.ofPattern("EEE d", Locale.ENGLISH)
private val clock12 = DateTimeFormatter.ofPattern("h:mm a", Locale.ENGLISH)

private fun hhmm(value: String): String = Week.time(value)?.format(clock12) ?: value.take(5)

/** A capsule that is the brand colour when chosen: the iOS segmented look, one per option. */
@Composable
private fun Choice(text: String, selected: Boolean, onClick: () -> Unit) {
    val fill by animateColorAsState(if (selected) MaterialTheme.colorScheme.primary else Color.Transparent, label = "choice")
    Text(
        text,
        style = MaterialTheme.typography.labelLarge,
        color = if (selected) MaterialTheme.colorScheme.onPrimary else MaterialTheme.colorScheme.onSurface,
        modifier = Modifier
            .pressable(scaleTo = 0.94f, haptic = true, onClick = onClick)
            .glassSurface(shape = CircleShape, strong = true)
            .background(fill, CircleShape)
            .padding(horizontal = 14.dp, vertical = 8.dp),
    )
}

@Composable
private fun NotConnected(padding: PaddingValues, what: String) {
    LazyColumn(contentPadding = padding) {
        item {
            EmptyState(Icons.Outlined.EventBusy, "No $what yet",
                "Connect or refresh your portal in the Attendance tab, and it shows up here.")
        }
    }
}

// --- Bunk planner ----------------------------------------------------------------------------

/**
 * "Can I skip Friday?" as a screen: pick a day in the next week, choose which of its classes to
 * miss, and see each subject's attendance after it, assuming every class until then is attended.
 * Plain arithmetic on the portal's own counts; the minimum is the college's own.
 */
@Composable
fun PlannerScreen(vm: AppViewModel, onBack: () -> Unit) {
    val state by vm.cards.collectAsStateWithLifecycle()
    val cards = state.cards
    PushScaffold("Bunk planner", onBack) { padding ->
        if (cards == null || !cards.timetable.connected || !cards.attendance.connected) {
            NotConnected(padding, "timetable")
            return@PushScaffold
        }
        Planner(cards, padding)
    }
}

@Composable
private fun Planner(cards: Cards, padding: PaddingValues) {
    val app = LocalAppColors.current
    val now = remember { LocalDateTime.now() }
    val days = remember(cards.timetable) {
        (0..7).map { now.toLocalDate().plusDays(it.toLong()) }
            .filter { Week.on(cards.timetable.data, it.dayOfWeek).isNotEmpty() }
    }
    var dayIndex by rememberSaveable { mutableIntStateOf(0) }
    val day = days.getOrNull(dayIndex) ?: days.firstOrNull()
    // Which of that day's classes you'd miss: all of them to start with.
    var skipped by remember(day) { mutableStateOf(day?.let { Week.on(cards.timetable.data, it.dayOfWeek).indices.toSet() } ?: emptySet()) }

    LazyColumn(contentPadding = padding, verticalArrangement = Arrangement.spacedBy(10.dp)) {
        item(key = "intro") {
            Text(
                "Pick a day and the classes you'd miss. Each subject shows where it ends up, if " +
                    "you attend every class until then.",
                style = MaterialTheme.typography.bodyLarge,
                color = app.secondaryLabel,
                modifier = Modifier.padding(horizontal = 4.dp),
            )
        }
        if (day == null) {
            item { EmptyState(Icons.Outlined.EventBusy, "No classes in the next week") }
            return@LazyColumn
        }
        item(key = "days") {
            LazyRow(horizontalArrangement = Arrangement.spacedBy(8.dp), contentPadding = PaddingValues(horizontal = 2.dp)) {
                items(days.size) { i ->
                    val d = days[i]
                    val label = when (d) {
                        now.toLocalDate() -> "Today"
                        now.toLocalDate().plusDays(1) -> "Tomorrow"
                        else -> d.format(dayChip)
                    }
                    Choice(label, i == days.indexOf(day)) { dayIndex = i }
                }
            }
        }
        val slots = Week.on(cards.timetable.data, day.dayOfWeek)
        item(key = "h-classes") { SectionHeader("Classes that day · tap to attend or skip") }
        item(key = "classes-$day") {
            Column(Modifier.fillMaxWidth().glassSurface()) {
                slots.forEachIndexed { i, slot ->
                    val off = i in skipped
                    val tint by animateColorAsState(
                        if (off) LocalStatusColors.current.short else LocalStatusColors.current.safe, label = "slot",
                    )
                    Row(
                        Modifier
                            .fillMaxWidth()
                            .pressable(scaleTo = 0.985f, haptic = true) { skipped = if (off) skipped - i else skipped + i }
                            .padding(horizontal = 14.dp, vertical = 11.dp),
                        verticalAlignment = Alignment.CenterVertically,
                    ) {
                        Text(hhmm(slot.start), style = MaterialTheme.typography.labelLarge, color = app.secondaryLabel,
                            modifier = Modifier.width(72.dp))
                        Text(cards.subjectName(slot.code), style = MaterialTheme.typography.bodyLarge, modifier = Modifier.weight(1f))
                        Text(if (off) "Skip" else "Attend", style = MaterialTheme.typography.labelLarge, color = tint,
                            fontWeight = FontWeight.SemiBold)
                    }
                    if (i < slots.lastIndex) Box(Modifier.padding(start = 14.dp).fillMaxWidth().height(0.6.dp).background(app.hairline))
                }
            }
        }
        val before = Week.before(cards.timetable.data, now, day)
        val missed = slots.filterIndexed { i, _ -> i in skipped }.groupingBy { it.code }.eachCount()
        val attendedThatDay = slots.filterIndexed { i, _ -> i !in skipped }.groupingBy { it.code }.eachCount()
        val affected = cards.attendance.subjects.filter { it.code in missed || it.code in attendedThatDay }
        item(key = "h-after") { SectionHeader("After ${day.format(DateTimeFormatter.ofPattern("EEEE", Locale.ENGLISH))}") }
        if (affected.isEmpty()) {
            item { Text("None of these classes count for attendance.", style = MaterialTheme.typography.bodyMedium,
                color = app.secondaryLabel, modifier = Modifier.padding(horizontal = 6.dp)) }
        }
        affected.forEach { s ->
            item(key = "p-${s.code}") {
                Projection(s, attend = (before[s.code] ?: 0) + (attendedThatDay[s.code] ?: 0), skip = missed[s.code] ?: 0)
            }
        }
    }
}

@Composable
private fun Projection(s: SubjectAttendance, attend: Int, skip: Int) {
    val status = LocalStatusColors.current
    val after = Week.projected(s, attend, skip)
    val ok = after >= s.minimumPercent
    val color = if (ok) (if (after - s.minimumPercent < 5) status.atRisk else status.safe) else status.short
    AppCard {
        Row(verticalAlignment = Alignment.CenterVertically) {
            AttendanceRing(after, s.minimumPercent, color, size = 56.dp)
            Spacer(Modifier.width(14.dp))
            Column(Modifier.weight(1f)) {
                Text(s.name, style = MaterialTheme.typography.titleMedium)
                Text(
                    "${pct(s.percent)}% now → ${pct(Math.round(after * 10) / 10.0)}%" +
                        (if (skip > 0) " · misses $skip" else "") + (if (attend > 0) " · attends $attend" else ""),
                    style = MaterialTheme.typography.bodySmall,
                    color = LocalAppColors.current.secondaryLabel,
                )
                Text(
                    if (ok) "Stays at or above ${pct(s.minimumPercent)}%" else "Falls below ${pct(s.minimumPercent)}%",
                    style = MaterialTheme.typography.labelMedium,
                    fontWeight = FontWeight.SemiBold,
                    color = color,
                )
            }
        }
    }
}

// --- Timetable -------------------------------------------------------------------------------

/** The week from the portal: pick a day, see its classes with each subject's attendance colour. */
@Composable
fun TimetableScreen(vm: AppViewModel, onBack: () -> Unit) {
    val state by vm.cards.collectAsStateWithLifecycle()
    val cards = state.cards
    PushScaffold("Timetable", onBack) { padding ->
        if (cards == null || !cards.timetable.connected) {
            NotConnected(padding, "timetable")
            return@PushScaffold
        }
        val days = DayOfWeek.values().filter { Week.on(cards.timetable.data, it).isNotEmpty() }
        val today = LocalDate.now().dayOfWeek
        var chosen by rememberSaveable { mutableStateOf(if (today in days) today else days.firstOrNull() ?: today) }
        LazyColumn(contentPadding = padding, verticalArrangement = Arrangement.spacedBy(10.dp)) {
            item(key = "days") {
                LazyRow(horizontalArrangement = Arrangement.spacedBy(8.dp), contentPadding = PaddingValues(horizontal = 2.dp)) {
                    items(days) { d -> Choice(if (d == today) "Today" else Week.short(d), d == chosen) { chosen = d } }
                }
            }
            val slots = Week.on(cards.timetable.data, chosen)
            item(key = "list-$chosen") { DayClasses(cards, slots, highlightNow = chosen == today) }
        }
    }
}

/** A day's classes as one grouped card. With [highlightNow], the class on now is marked. */
@Composable
internal fun DayClasses(cards: Cards, slots: List<Slot>, highlightNow: Boolean, modifier: Modifier = Modifier) {
    val app = LocalAppColors.current
    val status = LocalStatusColors.current
    val now = LocalTime.now()
    Column(modifier.fillMaxWidth().glassSurface()) {
        slots.forEachIndexed { i, slot ->
            val start = Week.time(slot.start)
            val end = Week.time(slot.end)
            val live = highlightNow && start != null && end != null && !now.isBefore(start) && now.isBefore(end)
            val past = highlightNow && end != null && !now.isBefore(end)
            val subject = cards.attendance.subjects.firstOrNull { it.code == slot.code }
            Row(
                Modifier
                    .fillMaxWidth()
                    .background(if (live) MaterialTheme.colorScheme.primary.copy(alpha = 0.10f) else Color.Transparent)
                    .padding(horizontal = 14.dp, vertical = 12.dp),
                verticalAlignment = Alignment.CenterVertically,
            ) {
                Column(Modifier.width(76.dp)) {
                    Text(hhmm(slot.start), style = MaterialTheme.typography.labelLarge,
                        color = if (past) app.tertiaryLabel else MaterialTheme.colorScheme.onSurface)
                    Text(hhmm(slot.end), style = MaterialTheme.typography.labelSmall, color = app.tertiaryLabel)
                }
                Box(
                    Modifier.width(3.dp).height(34.dp).background(
                        subject?.let { status.of(it.status) } ?: app.hairline, CircleShape,
                    ),
                )
                Spacer(Modifier.width(12.dp))
                Column(Modifier.weight(1f)) {
                    Text(cards.subjectName(slot.code), style = MaterialTheme.typography.bodyLarge,
                        color = if (past) app.secondaryLabel else MaterialTheme.colorScheme.onSurface)
                    Text(
                        listOfNotNull(slot.room, subject?.let { "${it.percent.toInt()}% attendance" }).joinToString(" · "),
                        style = MaterialTheme.typography.bodySmall,
                        color = app.secondaryLabel,
                    )
                }
                if (live) {
                    Text("Now", style = MaterialTheme.typography.labelMedium, fontWeight = FontWeight.Bold,
                        color = MaterialTheme.colorScheme.primary)
                }
            }
            if (i < slots.lastIndex) Box(Modifier.padding(start = 14.dp).fillMaxWidth().height(0.6.dp).background(app.hairline))
        }
    }
}

// --- Marks and results -----------------------------------------------------------------------

/** Internal marks per subject (each component as a bar) and past results with CGPA. */
@Composable
fun GradesScreen(vm: AppViewModel, onBack: () -> Unit) {
    val state by vm.cards.collectAsStateWithLifecycle()
    val cards = state.cards
    var tab by rememberSaveable { mutableIntStateOf(0) }
    PushScaffold("Grades", onBack) { padding ->
        if (cards == null || (!cards.marks.connected && !cards.results.connected)) {
            NotConnected(padding, "marks")
            return@PushScaffold
        }
        LazyColumn(contentPadding = padding, verticalArrangement = Arrangement.spacedBy(10.dp)) {
            item(key = "tabs") {
                NeoSegments(listOf(Segment("Internal marks"), Segment("Results"), Segment("What-if")), tab) { tab = it }
            }
            if (tab == 2) {
                item(key = "what-if") { WhatIfCalculator(cards) }
            } else if (tab == 0) {
                val bySubject = cards.marks.data.groupBy { it.code }
                if (bySubject.isEmpty()) item { EmptyState(Icons.Outlined.Grade, "No marks yet") }
                bySubject.forEach { (code, rows) ->
                    item(key = "m-$code") {
                        val scored = rows.sumOf { it.scored }
                        val max = rows.sumOf { it.maximum }
                        AppCard {
                            Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
                                Row(verticalAlignment = Alignment.CenterVertically) {
                                    Text(cards.subjectName(code), style = MaterialTheme.typography.titleMedium, modifier = Modifier.weight(1f))
                                    Text("${pct(scored)}/${pct(max)}", style = MaterialTheme.typography.titleMedium,
                                        color = MaterialTheme.colorScheme.primary)
                                }
                                rows.forEach { r ->
                                    val fraction = if (r.maximum > 0) (r.scored / r.maximum).toFloat() else 0f
                                    val color = when {
                                        fraction >= 0.75f -> LocalStatusColors.current.safe
                                        fraction >= 0.5f -> LocalStatusColors.current.atRisk
                                        else -> LocalStatusColors.current.short
                                    }
                                    Row(verticalAlignment = Alignment.CenterVertically) {
                                        Text(r.component, style = MaterialTheme.typography.labelMedium,
                                            color = LocalAppColors.current.secondaryLabel, modifier = Modifier.width(64.dp))
                                        SlimBar(fraction, color, Modifier.weight(1f))
                                        Text("${pct(r.scored)}/${pct(r.maximum)}", style = MaterialTheme.typography.labelMedium,
                                            textAlign = TextAlign.End, modifier = Modifier.width(64.dp))
                                    }
                                }
                            }
                        }
                    }
                }
            } else {
                val results = cards.results.data
                val semesters = results.semesters.sortedBy { it.semester }
                semesters.lastOrNull()?.let { last ->
                    item(key = "cgpa") {
                        AppCard {
                            Row(verticalAlignment = Alignment.CenterVertically) {
                                Column(Modifier.weight(1f)) {
                                    Text("CGPA", style = MaterialTheme.typography.labelMedium, color = LocalAppColors.current.secondaryLabel)
                                    Text(last.cgpa?.let { "%.2f".format(Locale.ENGLISH, it) } ?: "—",
                                        style = MaterialTheme.typography.headlineMedium, color = MaterialTheme.colorScheme.primary)
                                    Text("after semester ${last.semester}", style = MaterialTheme.typography.bodySmall,
                                        color = LocalAppColors.current.secondaryLabel)
                                }
                                SgpaBars(semesters.map { it.semester to (it.sgpa ?: 0.0) })
                            }
                        }
                    }
                }
                results.subjects.groupBy { it.semester }.toSortedMap(compareByDescending { it }).forEach { (sem, rows) ->
                    item(key = "h-$sem") {
                        SectionHeader("Semester $sem" + (semesters.firstOrNull { it.semester == sem }?.sgpa?.let { " · SGPA $it" } ?: ""))
                    }
                    item(key = "r-$sem") {
                        Column(Modifier.fillMaxWidth().glassSurface()) {
                            rows.forEachIndexed { i, r ->
                                Row(Modifier.fillMaxWidth().padding(horizontal = 14.dp, vertical = 11.dp),
                                    verticalAlignment = Alignment.CenterVertically) {
                                    Dot(gradeColor(r.grade))
                                    Spacer(Modifier.width(10.dp))
                                    Text(cards.subjectName(r.code), style = MaterialTheme.typography.bodyLarge, modifier = Modifier.weight(1f))
                                    Text("${pct(r.credits)} cr", style = MaterialTheme.typography.labelMedium,
                                        color = LocalAppColors.current.secondaryLabel)
                                    Spacer(Modifier.width(12.dp))
                                    Text(r.grade, style = MaterialTheme.typography.titleMedium, color = gradeColor(r.grade))
                                }
                                if (i < rows.lastIndex) Box(Modifier.padding(start = 14.dp).fillMaxWidth().height(0.6.dp)
                                    .background(LocalAppColors.current.hairline))
                            }
                        }
                    }
                }
            }
        }
    }
}

@Composable
private fun gradeColor(grade: String): Color {
    val status = LocalStatusColors.current
    return when (grade.uppercase()) {
        "O", "A+", "S" -> status.safe
        "A", "B+" -> LocalAppColors.current.material
        "B", "C" -> status.atRisk
        else -> status.short
    }
}

/** SGPA per semester as small rounded bars, scaled to 10. */
@Composable
private fun SgpaBars(values: List<Pair<Int, Double>>) {
    val color = MaterialTheme.colorScheme.primary
    val track = LocalAppColors.current.hairline
    Column(horizontalAlignment = Alignment.CenterHorizontally) {
        Canvas(Modifier.width((values.size * 18).coerceAtLeast(18).dp).height(56.dp)) {
            val w = 10.dp.toPx()
            values.forEachIndexed { i, (_, v) ->
                val x = i * 18.dp.toPx() + 4.dp.toPx()
                drawRoundRect(track, Offset(x, 0f), Size(w, size.height), CornerRadius(w / 2))
                val h = (v / 10.0).coerceIn(0.0, 1.0).toFloat() * size.height
                drawRoundRect(color, Offset(x, size.height - h), Size(w, h), CornerRadius(w / 2))
            }
        }
        Text("SGPA", style = MaterialTheme.typography.labelSmall, color = LocalAppColors.current.tertiaryLabel)
    }
}

/** The three ways into the portal's other data, shown on the Attendance tab. */
@Composable
internal fun CollegeTiles(onOpen: (String) -> Unit, modifier: Modifier = Modifier) {
    val app = LocalAppColors.current
    Row(modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(10.dp)) {
        Tile("Planner", Icons.Outlined.EventBusy, LocalStatusColors.current.atRisk, Modifier.weight(1f)) {
            onOpen(com.sevenfive.app.ui.Routes.PLANNER)
        }
        Tile("Timetable", Icons.Outlined.CalendarMonth, app.material, Modifier.weight(1f)) {
            onOpen(com.sevenfive.app.ui.Routes.TIMETABLE)
        }
        Tile("Grades", Icons.Outlined.Grade, app.event, Modifier.weight(1f)) {
            onOpen(com.sevenfive.app.ui.Routes.GRADES)
        }
    }
}

@Composable
private fun Tile(label: String, icon: androidx.compose.ui.graphics.vector.ImageVector, color: Color, modifier: Modifier, onClick: () -> Unit) {
    Column(
        modifier
            .pressable(scaleTo = 0.95f, haptic = true, onClick = onClick)
            .glassSurface(shape = MaterialTheme.shapes.medium)
            .padding(vertical = 12.dp),
        horizontalAlignment = Alignment.CenterHorizontally,
        verticalArrangement = Arrangement.spacedBy(6.dp),
    ) {
        com.sevenfive.app.ui.components.IconTile(icon, color, size = 34.dp)
        Text(label, style = MaterialTheme.typography.labelLarge)
    }
}
