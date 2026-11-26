package com.sevenfive.app.ui.screens

import android.content.ActivityNotFoundException
import android.content.Intent
import android.net.Uri
import androidx.activity.compose.BackHandler
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.clickable
import androidx.compose.foundation.horizontalScroll
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.rememberScrollState
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.outlined.ArrowBack
import androidx.compose.material.icons.outlined.CloudOff
import androidx.compose.material.icons.outlined.Description
import androidx.compose.material.icons.outlined.Folder
import androidx.compose.material.icons.outlined.FolderOpen
import androidx.compose.material.icons.outlined.Image
import androidx.compose.material.icons.outlined.PictureAsPdf
import androidx.compose.material.icons.outlined.Slideshow
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.FilterChip
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.vector.ImageVector
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import com.sevenfive.app.data.ApiException
import com.sevenfive.app.data.LibraryFile
import com.sevenfive.app.data.LibraryTree
import com.sevenfive.app.data.OpenedFile
import com.sevenfive.app.data.library
import com.sevenfive.app.data.libraryFiles
import com.sevenfive.app.data.openFile
import com.sevenfive.app.ui.AppViewModel
import com.sevenfive.app.ui.components.AppCard
import com.sevenfive.app.ui.components.EmptyState
import com.sevenfive.app.ui.components.TabScaffold
import kotlinx.coroutines.launch

/*
 * Files: the student's library as the WhatsApp bot keeps it, Subject -> shelf -> files.
 * Read live on every visit (nothing cached on the phone), so it is always the bot's truth.
 * Not: a copy of the library in 7even5ive. If the bot is down this tab says so, and every
 * other tab keeps working.
 */

private const val DEFAULT_SHELF = "material"

@Composable
fun FilesScreen(vm: AppViewModel, onSettings: () -> Unit) {
    val core = vm.container.core
    val scope = rememberCoroutineScope()
    val context = LocalContext.current

    var tree by remember { mutableStateOf<LibraryTree?>(null) }
    var problem by remember { mutableStateOf<String?>(null) }
    var loading by remember { mutableStateOf(false) }
    var subjectId by rememberSaveable { mutableStateOf<Int?>(null) }
    var unsorted by rememberSaveable { mutableStateOf(false) }
    var shelf by rememberSaveable { mutableStateOf(DEFAULT_SHELF) }
    var files by remember { mutableStateOf<List<LibraryFile>>(emptyList()) }
    var nextOffset by remember { mutableStateOf<Int?>(null) }
    var filesLoading by remember { mutableStateOf(false) }
    var note by remember { mutableStateOf<OpenedFile?>(null) }

    fun loadTree() = scope.launch {
        loading = true
        problem = null
        try {
            val got = core.library()
            if (got.available) {
                tree = got
            } else {
                problem = got.reason ?: "The library can't be reached right now."
            }
        } catch (e: ApiException) {
            problem = e.detail
        } finally {
            loading = false
        }
    }

    fun loadFiles(offset: Int) = scope.launch {
        filesLoading = true
        try {
            val page = core.libraryFiles(subjectId, shelf, unsorted, offset)
            if (!page.available) {
                vm.say(page.reason ?: "The library can't be reached right now.")
            } else {
                // A file added or removed between pages shifts the next page: one already shown
                // can come again, and a repeated key would close the app.
                files = (if (offset == 0) page.files else files + page.files).distinctBy { it.id }
                nextOffset = page.nextOffset
            }
        } catch (e: ApiException) {
            vm.say(e.detail)
        } finally {
            filesLoading = false
        }
    }

    fun open(file: LibraryFile) = scope.launch {
        try {
            val opened = core.openFile(file.id)
            when {
                !opened.available -> vm.say(opened.reason ?: "The library can't be reached right now.")
                opened.kind == "note" -> {
                    note = opened
                }
                opened.url != null -> try {
                    // The link works for a few minutes: the viewer app downloads it straight away.
                    context.startActivity(
                        Intent(Intent.ACTION_VIEW, Uri.parse(opened.url))
                            .addFlags(Intent.FLAG_ACTIVITY_NEW_TASK),
                    )
                } catch (e: ActivityNotFoundException) {
                    vm.say("No app on this phone can open ${opened.filename ?: "this file"}.")
                }
                else -> vm.say("That file has nothing to open.")
            }
        } catch (e: ApiException) {
            vm.say(e.detail)
        }
    }

    LaunchedEffect(Unit) { loadTree() }
    LaunchedEffect(subjectId, shelf, unsorted) {
        files = emptyList()
        nextOffset = null
        if (subjectId != null || unsorted) loadFiles(0)
    }
    BackHandler(enabled = subjectId != null || unsorted) {
        subjectId = null
        unsorted = false
    }

    note?.let { shown ->
        AlertDialog(
            onDismissRequest = { note = null },
            confirmButton = { TextButton(onClick = { note = null }) { Text("Close") } },
            title = { Text(shown.title ?: "Note") },
            text = { Text(shown.text.orEmpty()) },
        )
    }

    TabScaffold("Files", vm, onSettings) { padding ->
        val current = tree
        if (current == null) {
            if (loading) {
                Box(Modifier.padding(padding)) { Centered { CircularProgressIndicator() } }
            } else {
                Column(Modifier.fillMaxWidth().padding(padding), horizontalAlignment = Alignment.CenterHorizontally) {
                    EmptyState(Icons.Outlined.CloudOff, "Library unavailable", problem ?: "Couldn't load your files.")
                    TextButton(onClick = { loadTree() }) { Text("Try again") }
                }
            }
            return@TabScaffold
        }
        when {
            subjectId == null && !unsorted -> SubjectList(current, padding, onSubject = { id ->
                subjectId = id
                shelf = current.subjects.firstOrNull { it.id == id }
                    ?.shelves?.firstOrNull { it.files > 0 }?.shelf ?: DEFAULT_SHELF
            }, onUnsorted = { unsorted = true })
            else -> {
                val subject = current.subjects.firstOrNull { it.id == subjectId }
                Column(Modifier.padding(top = padding.calculateTopPadding())) {
                    Row(Modifier.padding(horizontal = 8.dp), verticalAlignment = Alignment.CenterVertically) {
                        IconButton(onClick = { subjectId = null; unsorted = false }) {
                            Icon(Icons.AutoMirrored.Outlined.ArrowBack, contentDescription = "All subjects")
                        }
                        Text(
                            if (unsorted) "Waiting for a subject" else subject?.name ?: "Subject",
                            style = MaterialTheme.typography.titleMedium,
                        )
                    }
                    if (!unsorted && subject != null) {
                        Row(
                            Modifier.horizontalScroll(rememberScrollState()).padding(horizontal = 16.dp, vertical = 4.dp),
                            horizontalArrangement = Arrangement.spacedBy(8.dp),
                        ) {
                            subject.shelves.forEach { s ->
                                FilterChip(
                                    selected = shelf == s.shelf,
                                    onClick = { shelf = s.shelf },
                                    label = { Text("${s.label}  ${s.files}", maxLines = 1) },
                                )
                            }
                        }
                    }
                    LazyColumn(
                        contentPadding = PaddingValues(start = 16.dp, end = 16.dp, top = 8.dp, bottom = padding.calculateBottomPadding() + 24.dp),
                        verticalArrangement = Arrangement.spacedBy(8.dp),
                    ) {
                        if (files.isEmpty() && !filesLoading) {
                            item { EmptyState(Icons.Outlined.FolderOpen, "Nothing here yet", "Forward files to the bot and they're filed here.") }
                        }
                        items(files, key = { it.id }) { file -> FileRow(file) { open(file) } }
                        if (filesLoading) {
                            item { Centered { CircularProgressIndicator() } }
                        } else if (nextOffset != null) {
                            item {
                                TextButton(onClick = { loadFiles(nextOffset ?: 0) }, modifier = Modifier.fillMaxWidth()) {
                                    Text("Show more")
                                }
                            }
                        }
                    }
                }
            }
        }
    }
}

@Composable
private fun SubjectList(tree: LibraryTree, padding: PaddingValues, onSubject: (Int) -> Unit, onUnsorted: () -> Unit) {
    LazyColumn(contentPadding = padding, verticalArrangement = Arrangement.spacedBy(8.dp)) {
        if (tree.subjects.isEmpty() && tree.unsorted == 0) {
            item {
                EmptyState(Icons.Outlined.FolderOpen, "No files yet",
                    "Forward notes, slides and papers to the bot and they appear here by subject.")
            }
        }
        items(tree.subjects, key = { it.id }) { subject ->
            FolderRow(subject.name, "${subject.total} files") { onSubject(subject.id) }
        }
        if (tree.unsorted > 0) {
            item { FolderRow("Waiting for a subject", "${tree.unsorted} files") { onUnsorted() } }
        }
    }
}

@Composable
private fun FolderRow(name: String, detail: String, onClick: () -> Unit) {
    AppCard(Modifier.clickable(onClick = onClick)) {
        Row(verticalAlignment = Alignment.CenterVertically) {
            Icon(Icons.Outlined.Folder, contentDescription = null, tint = MaterialTheme.colorScheme.primary)
            Spacer(Modifier.width(12.dp))
            Column(Modifier.weight(1f)) {
                Text(name, style = MaterialTheme.typography.bodyLarge, maxLines = 1, overflow = TextOverflow.Ellipsis)
                Text(detail, style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
            }
        }
    }
}

@Composable
private fun FileRow(file: LibraryFile, onOpen: () -> Unit) {
    AppCard(Modifier.clickable(onClick = onOpen)) {
        Row(verticalAlignment = Alignment.CenterVertically) {
            Icon(iconFor(file), contentDescription = null, tint = MaterialTheme.colorScheme.primary)
            Spacer(Modifier.width(12.dp))
            Column(Modifier.weight(1f)) {
                Text(file.title, style = MaterialTheme.typography.bodyLarge, maxLines = 2, overflow = TextOverflow.Ellipsis)
                val detail = if (file.kind == "note") "Note" else file.filename ?: ""
                if (detail.isNotBlank()) {
                    Text(detail, style = MaterialTheme.typography.bodySmall,
                        color = MaterialTheme.colorScheme.onSurfaceVariant, maxLines = 1, overflow = TextOverflow.Ellipsis)
                }
            }
        }
    }
}

private fun iconFor(file: LibraryFile): ImageVector {
    if (file.kind == "note") return Icons.Outlined.Description
    val mime = file.mimeType.orEmpty()
    val ext = (file.filename ?: file.title).substringAfterLast('.', "").lowercase()
    return when {
        mime == "application/pdf" || ext == "pdf" -> Icons.Outlined.PictureAsPdf
        mime.startsWith("image/") -> Icons.Outlined.Image
        ext in setOf("ppt", "pptx", "key") || "presentation" in mime -> Icons.Outlined.Slideshow
        else -> Icons.Outlined.Description
    }
}

@Composable
private fun Centered(content: @Composable () -> Unit) {
    Box(Modifier.fillMaxWidth().padding(top = 48.dp), contentAlignment = Alignment.TopCenter) { content() }
}
