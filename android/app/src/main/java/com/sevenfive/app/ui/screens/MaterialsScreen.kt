package com.sevenfive.app.ui.screens

import androidx.compose.foundation.clickable
import androidx.compose.foundation.horizontalScroll
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.rememberScrollState
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.outlined.Description
import androidx.compose.material.icons.outlined.FolderOpen
import androidx.compose.material.icons.outlined.PictureAsPdf
import androidx.compose.material.icons.outlined.Slideshow
import androidx.compose.material3.FilterChip
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
import androidx.compose.ui.graphics.vector.ImageVector
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import com.sevenfive.app.data.Item
import com.sevenfive.app.ui.AppViewModel
import com.sevenfive.app.ui.components.AppCard
import com.sevenfive.app.ui.components.EmptyState
import com.sevenfive.app.ui.components.RouteBadge
import com.sevenfive.app.ui.components.ScreenPadding
import com.sevenfive.app.ui.components.TabScaffold

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
    var chosen by rememberSaveable { mutableStateOf(ALL) }
    val materials = state.cards?.materials.orEmpty()
    val subjects = subjectsOf(materials)
    if (chosen != ALL && chosen !in subjects) chosen = ALL
    val shown = if (chosen == ALL) materials else materials.filter { it.subject == chosen }

    TabScaffold("Materials", vm, onSettings, subtitle = "Notes, slides, manuals and papers by subject") {
        if (state.cards == null) {
            LoadingOrError(state.loading)
            return@TabScaffold
        }
        Column {
            if (subjects.isNotEmpty()) {
                Row(
                    Modifier.horizontalScroll(rememberScrollState()).padding(horizontal = 16.dp, vertical = 8.dp),
                    horizontalArrangement = Arrangement.spacedBy(8.dp),
                ) {
                    (listOf(ALL) + subjects).forEach { subject ->
                        val count = if (subject == ALL) materials.size else materials.count { it.subject == subject }
                        FilterChip(
                            selected = chosen == subject,
                            onClick = { chosen = subject },
                            label = { Text("$subject  $count", maxLines = 1) },
                        )
                    }
                }
            }
            LazyColumn(contentPadding = ScreenPadding, verticalArrangement = Arrangement.spacedBy(8.dp)) {
                if (shown.isEmpty()) {
                    item {
                        EmptyState(Icons.Outlined.FolderOpen, "No materials yet",
                            "Forward notes and slides to the 7even5ive bot and they're filed here by subject.")
                    }
                }
                items(shown, key = { it.id }) { item ->
                    MaterialRow(item) {
                        vm.say("Opening files comes next: the file stays with the WhatsApp bot for now.")
                    }
                }
            }
        }
    }
}

private fun fileIcon(name: String): ImageVector {
    val ext = name.substringAfterLast('.', "").lowercase()
    return when (ext) {
        "pdf" -> Icons.Outlined.PictureAsPdf
        "ppt", "pptx", "key" -> Icons.Outlined.Slideshow
        else -> Icons.Outlined.Description
    }
}

@Composable
private fun MaterialRow(item: Item, onOpen: () -> Unit) {
    val name = item.title ?: "Untitled file"
    AppCard(Modifier.clickable(onClick = onOpen)) {
        Row(verticalAlignment = Alignment.CenterVertically) {
            Icon(fileIcon(name), contentDescription = null, tint = MaterialTheme.colorScheme.primary)
            Spacer(Modifier.width(12.dp))
            Column(Modifier.weight(1f)) {
                Text(name, style = MaterialTheme.typography.bodyLarge, maxLines = 2, overflow = TextOverflow.Ellipsis)
                Text(item.subject ?: MISC, style = MaterialTheme.typography.bodySmall,
                    color = MaterialTheme.colorScheme.onSurfaceVariant)
            }
            RouteBadge(item.route)
        }
    }
}
