package com.sevenfive.app.data

import kotlinx.serialization.SerialName
import kotlinx.serialization.Serializable
import kotlinx.serialization.json.buildJsonObject
import kotlinx.serialization.json.decodeFromJsonElement
import kotlinx.serialization.json.put

/*
 * The student's file library, read live from the WhatsApp bot through 7even5ive's gateway.
 * Why live: the bot's database is the one library, so the phone never shows a file the bot
 * renamed, moved or deleted. Why through the gateway: the phone never holds the bot's key,
 * and every read is checked and logged like any other tool call.
 * A file opens through a link that works for a few minutes; a note comes back as text.
 */

@Serializable
data class LibraryTree(
    val subjects: List<LibrarySubject> = emptyList(),
    val unsorted: Int = 0,
    /** False when the bot can't be reached; [reason] says so in plain words. */
    val available: Boolean = true,
    val reason: String? = null,
)

@Serializable
data class LibrarySubject(
    val id: Int = 0,
    val name: String = "",
    val shelves: List<LibraryShelf> = emptyList(),
) {
    val total: Int get() = shelves.sumOf { it.files }
}

/** One of the bot's three fixed shelves: material, pyq, info. */
@Serializable
data class LibraryShelf(val shelf: String = "", val label: String = "", val files: Int = 0)

@Serializable
data class LibraryFile(
    val id: Int = 0,
    /** "file" (bytes in storage) or "note" (text the student sent). */
    val kind: String = "file",
    val title: String = "",
    val filename: String? = null,
    @SerialName("mime_type") val mimeType: String? = null,
    val shelf: String = "",
    @SerialName("created_at") val createdAt: String? = null,
)

@Serializable
data class FilePage(
    val files: List<LibraryFile> = emptyList(),
    @SerialName("next_offset") val nextOffset: Int? = null,
    val available: Boolean = true,
    val reason: String? = null,
)

@Serializable
data class OpenedFile(
    val kind: String = "",
    val url: String? = null,
    val filename: String? = null,
    @SerialName("mime_type") val mimeType: String? = null,
    val title: String? = null,
    val text: String? = null,
    val available: Boolean = true,
    val reason: String? = null,
)

suspend fun CoreApi.library(): LibraryTree =
    tool("list_library").result?.let { AppJson.decodeFromJsonElement<LibraryTree>(it) }
        ?: LibraryTree()

suspend fun CoreApi.libraryFiles(subjectId: Int?, shelf: String?, unsorted: Boolean, offset: Int): FilePage {
    val args = buildJsonObject {
        if (unsorted) {
            put("unsorted", true)
        } else {
            put("subject_id", subjectId)
            if (shelf != null) put("shelf", shelf)
        }
        put("offset", offset)
    }
    return tool("list_library_files", args).result
        ?.let { AppJson.decodeFromJsonElement<FilePage>(it) } ?: FilePage()
}

suspend fun CoreApi.openFile(id: Int): OpenedFile =
    tool("open_file", buildJsonObject { put("file_id", id) }).result
        ?.let { AppJson.decodeFromJsonElement<OpenedFile>(it) } ?: OpenedFile()
