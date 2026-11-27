package com.sevenfive.app.util

import android.content.ActivityNotFoundException
import android.content.Context
import android.content.Intent
import android.provider.CalendarContract
import androidx.core.content.FileProvider
import com.sevenfive.app.data.Item
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import java.io.File

/** Handing things to other apps on the phone: a material's file, a deadline to the calendar. */
object Opener {
    private val types = mapOf(
        "pdf" to "application/pdf",
        "doc" to "application/msword",
        "docx" to "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        "ppt" to "application/vnd.ms-powerpoint",
        "pptx" to "application/vnd.openxmlformats-officedocument.presentationml.presentation",
        "txt" to "text/plain",
        "png" to "image/png",
        "jpg" to "image/jpeg",
        "jpeg" to "image/jpeg",
    )

    fun mimeOf(name: String): String = types[name.substringAfterLast('.', "").lowercase()] ?: "*/*"

    /**
     * Saves the bytes in the app's cache (opened/) and opens them in whatever app the phone has
     * for that type. Returns a sentence for the student when nothing can open it.
     */
    suspend fun openFile(context: Context, name: String, bytes: ByteArray): String? {
        val safe = name.map { if (it.isLetterOrDigit() || it in "._- ") it else '_' }.joinToString("").ifBlank { "file" }
        val file = withContext(Dispatchers.IO) {
            File(context.cacheDir, "opened").apply { mkdirs() }.let { dir -> File(dir, safe).apply { writeBytes(bytes) } }
        }
        val uri = FileProvider.getUriForFile(context, "${context.packageName}.files", file)
        val view = Intent(Intent.ACTION_VIEW)
            .setDataAndType(uri, mimeOf(safe))
            .addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION or Intent.FLAG_ACTIVITY_NEW_TASK)
        return try {
            context.startActivity(view)
            null
        } catch (e: ActivityNotFoundException) {
            "No app on this phone opens .${safe.substringAfterLast('.', "file")} files."
        }
    }

    /**
     * The phone's own calendar app, filled in: the student saves it there. No permission, and
     * nothing leaves the phone (this is not the Google Calendar write the AI asks to make).
     */
    fun addToPhoneCalendar(context: Context, item: Item): String? {
        val at = Time.parse(item.dueAt)?.toInstant()?.toEpochMilli() ?: return "This card has no date."
        val insert = Intent(Intent.ACTION_INSERT)
            .setData(CalendarContract.Events.CONTENT_URI)
            .putExtra(CalendarContract.EXTRA_EVENT_BEGIN_TIME, at - 60 * 60 * 1000)
            .putExtra(CalendarContract.EXTRA_EVENT_END_TIME, at)
            .putExtra(CalendarContract.Events.TITLE, item.title ?: "Due")
            .putExtra(CalendarContract.Events.DESCRIPTION, listOfNotNull(item.subject, "From 7even5ive").joinToString(" · "))
            .addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
        return try {
            context.startActivity(insert)
            null
        } catch (e: ActivityNotFoundException) {
            "No calendar app on this phone."
        }
    }
}
