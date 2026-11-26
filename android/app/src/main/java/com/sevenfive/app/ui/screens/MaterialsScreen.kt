package com.sevenfive.app.ui.screens

import androidx.compose.animation.animateColorAsState
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.LazyRow
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.outlined.KeyboardArrowRight
import androidx.compose.material.icons.outlined.Description
import androidx.compose.material.icons.outlined.FolderOpen
import androidx.compose.material.icons.outlined.PictureAsPdf
import androidx.compose.material.icons.outlined.Slideshow
import androidx.compose.material3.Icon
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.vector.ImageVector
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import com.sevenfive.app.data.Item
import com.sevenfive.app.ui.AppViewModel
import com.sevenfive.app.ui.components.AppCard
import com.sevenfive.app.ui.components.EmptyState
import com.sevenfive.app.ui.components.IconTile
import com.sevenfive.app.ui.components.RouteBadge
import com.sevenfive.app.ui.components.ScreenIntro
import com.sevenfive.app.ui.components.TabScaffold
import com.sevenfive.app.ui.theme.LocalAppColors
import com.sevenfive.app.ui.theme.Motion
import com.sevenfive.app.ui.theme.glassSurface
import com.sevenfive.app.ui.theme.pressable

private const val ALL = "All"
private const val MISC = "Miscellaneous"

/** Subjects in the order they first appear, with Miscellaneous last. */
fun subjectsOf(items: List<Item>): List<String> {
    val names = items.mapNotNull { it.subject?.takeIf(String::isNotBlank) }.distinct()
    return names.filter { it != MISC } + names.filter { it == MISC }
}

@Composable
fun MaterialsScreen(vm: AppViewModel, onSettings: () -> Unit) {
    val state by vm.cards.collectAsStateWithLifecycle()
    val busy by vm.busy.collectAsStateWithLifecycle()
    var chosen by rememberSaveable { mutableStateOf(ALL) }
    val materials = state.cards?.materials.orEmpty()
    val subjects = subjectsOf(materials)
    if (chosen != ALL && chosen !in subjects) chosen = ALL
    val shown = if (chosen == ALL) materials else materials.filter { it.subject == chosen }

    TabScaffold("Materials", vm, onSettings) { padding ->
        if (state.cards == null) {
            LoadingOrError(state.loading, padding)
            return@TabScaffold
        }
        LazyColumn(contentPadding = padding, verticalArrangement = Arrangement.spacedBy(10.dp)) {
            item(key = "intro") { ScreenIntro("Notes, slides, manuals and papers, by subject.") }
            if (subjects.isNotEmpty()) {
                item(key = "chips") {
                    // The chip row runs edge to edge, past the list's side padding.
                    LazyRow(
                        Modifier.fillMaxWidth().padding(vertical = 2.dp),
                        horizontalArrangement = Arrangement.spacedBy(8.dp),
                        contentPadding = PaddingValues(horizontal = 2.dp),
                    ) {
                        items(listOf(ALL) + subjects, key = { it }) { subject ->
                            val count = if (subject == ALL) materials.size else materials.count { it.subject == subject }
                            SubjectChip(subject, count, chosen == subject) { chosen = subject }
                        }
                    }
                }
            }
            if (shown.isEmpty()) {
                item(key = "empty") {
                    EmptyState(Icons.Outlined.FolderOpen, "No materials yet",
                        "Forward notes and slides to the 7even5ive bot and they're filed here by subject.")
                }
            }
            items(shown, key = { it.id }) { item ->
                MaterialRow(item, "file:${item.id}" in busy, Modifier.animateItem(placementSpec = Motion.item)) {
                    if (item.hasFile) vm.openFile(item)
                    else vm.say("Only the name came through for this one: the file stayed in WhatsApp.")
                }
            }
        }
    }
}

/** A segmented-style capsule: filled in the brand colour when chosen, glass otherwise. */
@Composable
private fun SubjectChip(subject: String, count: Int, selected: Boolean, onClick: () -> Unit) {
    val primary = MaterialTheme.colorScheme.primary
    val fill by animateColorAsState(if (selected) primary else Color.Transparent, label = "chip")
    val text by animateColorAsState(
        if (selected) MaterialTheme.colorScheme.onPrimary else MaterialTheme.colorScheme.onSurface,
        label = "chip text",
    )
    Row(
        Modifier
            .pressable(scaleTo = 0.94f, haptic = true, onClick = onClick)
            .glassSurface(shape = CircleShape, strong = true)
            .background(fill, CircleShape)
            .padding(horizontal = 14.dp, vertical = 8.dp),
        verticalAlignment = Alignment.CenterVertically,
    ) {
        Text(subject, style = MaterialTheme.typography.labelLarge, color = text, maxLines = 1)
        Spacer(Modifier.width(6.dp))
        Text("$count", style = MaterialTheme.typography.labelMedium, color = text.copy(alpha = 0.7f), fontWeight = FontWeight.SemiBold)
    }
}

private data class FileLook(val icon: ImageVector, val kind: String)

private fun fileLook(name: String): FileLook {
    return when (name.substringAfterLast('.', "").lowercase()) {
        "pdf" -> FileLook(Icons.Outlined.PictureAsPdf, "pdf")
        "ppt", "pptx", "key" -> FileLook(Icons.Outlined.Slideshow, "slides")
        else -> FileLook(Icons.Outlined.Description, "doc")
    }
}

@Composable
private fun MaterialRow(item: Item, opening: Boolean, modifier: Modifier = Modifier, onOpen: () -> Unit) {
    val name = item.title ?: "Untitled file"
    val look = fileLook(name)
    val app = LocalAppColors.current
    val color = when (look.kind) {
        "pdf" -> app.exam
        "slides" -> app.deadline
        else -> app.material
    }
    AppCard(modifier.pressable(scaleTo = 0.98f, onClick = onOpen)) {
        Row(verticalAlignment = Alignment.CenterVertically) {
            IconTile(look.icon, color)
            Spacer(Modifier.width(12.dp))
            Column(Modifier.weight(1f)) {
                Text(name, style = MaterialTheme.typography.bodyLarge, fontWeight = FontWeight.Medium,
                    maxLines = 2, overflow = TextOverflow.Ellipsis)
                Row(verticalAlignment = Alignment.CenterVertically) {
                    Text(
                        (item.subject ?: MISC) + if (item.hasFile) "" else " · name only",
                        style = MaterialTheme.typography.bodySmall,
                        color = app.secondaryLabel,
                    )
                    Spacer(Modifier.width(8.dp))
                    RouteBadge(item.route)
                }
            }
            if (opening) {
                androidx.compose.material3.CircularProgressIndicator(
                    Modifier.size(18.dp), strokeWidth = 2.dp, color = MaterialTheme.colorScheme.primary,
                )
            } else {
                Icon(Icons.AutoMirrored.Outlined.KeyboardArrowRight, contentDescription = null, tint = app.tertiaryLabel)
            }
        }
    }
}
