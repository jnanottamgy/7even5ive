package com.sevenfive.app.ui.screens

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.imePadding
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.outlined.Alarm
import androidx.compose.material.icons.outlined.PieChart
import androidx.compose.material.icons.outlined.Search
import androidx.compose.material.icons.outlined.SearchOff
import androidx.compose.material3.Icon
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.material3.TextField
import androidx.compose.material3.TextFieldDefaults
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.focus.FocusRequester
import androidx.compose.ui.focus.focusRequester
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.vector.ImageVector
import androidx.compose.ui.text.input.ImeAction
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import com.sevenfive.app.data.Cards
import com.sevenfive.app.ui.AppViewModel
import com.sevenfive.app.ui.components.EmptyState
import com.sevenfive.app.ui.components.IconTile
import com.sevenfive.app.ui.components.PushScaffold
import com.sevenfive.app.ui.components.SectionHeader
import com.sevenfive.app.ui.components.kindColor
import com.sevenfive.app.ui.components.kindStyle
import com.sevenfive.app.ui.theme.LocalAppColors
import com.sevenfive.app.ui.theme.LocalStatusColors
import com.sevenfive.app.ui.theme.Motion
import com.sevenfive.app.ui.theme.glassSurface
import com.sevenfive.app.ui.theme.pressable
import com.sevenfive.app.util.Time

/** One search hit, wherever it lives. [open] runs when it's tapped (a file, for example). */
private data class Hit(
    val key: String,
    val section: String,
    val title: String,
    val detail: String,
    val icon: ImageVector,
    val color: Color,
    val open: (() -> Unit)? = null,
)

/** Every word of the query must appear somewhere in the text, in any order. */
fun matches(query: String, vararg text: String?): Boolean {
    val hay = text.filterNotNull().joinToString(" ").lowercase()
    return query.lowercase().split(' ').filter { it.isNotBlank() }.all { it in hay }
}

/** Search across everything the app holds: due, materials, mail, reminders, subjects. */
@Composable
fun SearchScreen(vm: AppViewModel, onBack: () -> Unit) {
    val state by vm.cards.collectAsStateWithLifecycle()
    var query by rememberSaveable { mutableStateOf("") }
    val focus = remember { FocusRequester() }
    LaunchedEffect(Unit) { runCatching { focus.requestFocus() } }
    val cards = state.cards
    val hits = if (cards == null || query.isBlank()) emptyList() else hitsFor(cards, query.trim(), vm)
    val app = LocalAppColors.current

    PushScaffold("Search", onBack) { padding ->
        LazyColumn(
            Modifier.fillMaxSize().imePadding(),
            contentPadding = padding,
            verticalArrangement = Arrangement.spacedBy(8.dp),
        ) {
            item(key = "field") {
                Row(
                    Modifier.fillMaxWidth().glassSurface(shape = CircleShape, strong = true).padding(start = 14.dp),
                    verticalAlignment = Alignment.CenterVertically,
                ) {
                    Icon(Icons.Outlined.Search, contentDescription = null, tint = app.secondaryLabel)
                    TextField(
                        value = query,
                        onValueChange = { query = it.take(80) },
                        placeholder = { Text("Deadlines, notes, subjects, mail") },
                        singleLine = true,
                        keyboardOptions = KeyboardOptions(imeAction = ImeAction.Search),
                        textStyle = MaterialTheme.typography.bodyLarge,
                        colors = TextFieldDefaults.colors(
                            focusedContainerColor = Color.Transparent,
                            unfocusedContainerColor = Color.Transparent,
                            focusedIndicatorColor = Color.Transparent,
                            unfocusedIndicatorColor = Color.Transparent,
                            cursorColor = MaterialTheme.colorScheme.primary,
                        ),
                        modifier = Modifier.weight(1f).focusRequester(focus),
                    )
                }
            }
            if (query.isNotBlank() && hits.isEmpty()) {
                item(key = "none") { EmptyState(Icons.Outlined.SearchOff, "Nothing matches “${query.trim()}”") }
            }
            var section = ""
            hits.forEach { hit ->
                if (hit.section != section) {
                    section = hit.section
                    item(key = "h-${hit.section}") { SectionHeader(hit.section, Modifier.animateItem(placementSpec = Motion.item)) }
                }
                item(key = hit.key) { HitRow(hit, Modifier.animateItem(placementSpec = Motion.item)) }
            }
        }
    }
}

@Composable
private fun hitsFor(cards: Cards, q: String, vm: AppViewModel): List<Hit> {
    val status = LocalStatusColors.current
    val app = LocalAppColors.current
    val out = mutableListOf<Hit>()
    cards.dueThisWeek.filter { matches(q, it.title, it.subject, it.kind) }.forEach {
        out += Hit("d${it.id}", "Due this week", it.title ?: "Untitled",
            listOfNotNull(it.subject, Time.parse(it.dueAt)?.let { at -> Time.dayAndTime(at) }).joinToString(" · "),
            kindStyle(it.kind).icon, kindColor(it.kind))
    }
    cards.materials.filter { matches(q, it.title, it.subject) }.forEach {
        out += Hit("m${it.id}", "Materials", it.title ?: "Untitled", it.subject ?: "",
            kindStyle("material").icon, kindColor("material"), open = if (it.hasFile) ({ vm.openFile(it) }) else null)
    }
    cards.opportunities.filter { matches(q, it.title, it.subject, it.kind) }.forEach {
        out += Hit("o${it.id}", "Inbox", it.title ?: "Untitled", kindStyle(it.kind).label,
            kindStyle(it.kind).icon, kindColor(it.kind))
    }
    cards.reminders.filter { matches(q, it.title, it.subject) }.forEach {
        out += Hit("r${it.id}", "Reminders", it.title ?: "Untitled",
            Time.parse(it.firesAt)?.let { at -> "Reminds ${Time.dayAndTime(at)}" } ?: "",
            Icons.Outlined.Alarm, app.deadline)
    }
    cards.attendance.subjects.filter { matches(q, it.name, it.code) }.forEach {
        out += Hit("s${it.code}", "Attendance", it.name, "${it.percent.toInt()}% · ${it.message}",
            Icons.Outlined.PieChart, status.of(it.status))
    }
    cards.needsReview.filter { matches(q, it.title) }.forEach {
        out += Hit("n${it.id}", "Couldn't read these", it.title ?: "Untitled", "Not filed",
            kindStyle("notice").icon, app.secondaryLabel)
    }
    return out
}

@Composable
private fun HitRow(hit: Hit, modifier: Modifier = Modifier) {
    Row(
        modifier
            .fillMaxWidth()
            .then(if (hit.open != null) Modifier.pressable(scaleTo = 0.98f, onClick = hit.open) else Modifier)
            .glassSurface(shape = MaterialTheme.shapes.medium)
            .padding(12.dp),
        verticalAlignment = Alignment.CenterVertically,
    ) {
        IconTile(hit.icon, hit.color, size = 34.dp)
        Spacer(Modifier.width(12.dp))
        Column(Modifier.weight(1f)) {
            Text(hit.title, style = MaterialTheme.typography.bodyLarge, maxLines = 2, overflow = TextOverflow.Ellipsis)
            if (hit.detail.isNotBlank()) {
                Text(hit.detail, style = MaterialTheme.typography.bodySmall, color = LocalAppColors.current.secondaryLabel,
                    maxLines = 2, overflow = TextOverflow.Ellipsis)
            }
        }
    }
}
