package com.sevenfive.app.util

import android.app.ActivityManager
import android.app.ApplicationExitInfo
import android.content.Context
import android.os.Build
import androidx.annotation.RequiresApi
import java.io.File
import java.time.Instant

/**
 * Why the app last closed, readable on the phone itself (Settings → Diagnostics), so a crash
 * on a student's phone can be reported without a cable or adb.
 *
 * Only stack traces and Android's exit reasons are kept: never message text, mail text, the
 * token or portal pages. Exception messages here are our own (hosts, codes), not content.
 */
object Diagnostics {
    private const val CRASH_FILE = "last_crash.txt"
    private const val SEEN_PREFS = "diagnostics"
    private const val TRAIL_FILE = "trail.txt"
    private const val TRAIL_LINES = 40

    /**
     * One line per step of risky work (opening the portal WebView), written before the next
     * step starts. A native crash inside WebView skips every Java handler, so the last line
     * here is the only record of how far the app got.
     */
    @Synchronized
    fun step(context: Context, what: String) {
        runCatching {
            val file = File(context.applicationContext.filesDir, TRAIL_FILE)
            val kept = if (file.exists()) file.readLines().takeLast(TRAIL_LINES - 1) else emptyList()
            file.writeText((kept + "${Instant.now()}  $what").joinToString("\n") + "\n")
        }
    }

    fun install(context: Context) {
        val app = context.applicationContext
        val previous = Thread.getDefaultUncaughtExceptionHandler()
        Thread.setDefaultUncaughtExceptionHandler { thread, error ->
            runCatching {
                File(app.filesDir, CRASH_FILE).writeText(
                    "Crash at ${Instant.now()} on thread \"${thread.name}\"\n" +
                        error.stackTraceToString().take(16_000)
                )
            }
            previous?.uncaughtException(thread, error)
        }
    }

    /** Everything known about the last bad exit, newest first, or null if there was none. */
    fun report(context: Context): String? {
        val parts = mutableListOf<String>()
        File(context.filesDir, CRASH_FILE).takeIf { it.exists() }?.let { parts += it.readText() }
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.R) parts += exitReasons(context)
        val problems = parts.joinToString("\n\n")
        val trail = File(context.filesDir, TRAIL_FILE).takeIf { it.exists() }?.readText().orEmpty()
        return listOf(
            problems,
            if (trail.isBlank()) "" else "Last steps:\n$trail",
        ).filter { it.isNotBlank() }.joinToString("\n\n").ifBlank { null }
    }

    /** True once per new problem, so the app can say "it closed last time" exactly once. */
    fun hasUnseen(context: Context): Boolean {
        val report = problems(context) ?: return false
        val prefs = context.getSharedPreferences(SEEN_PREFS, Context.MODE_PRIVATE)
        val hash = report.hashCode()
        if (prefs.getInt("seen", 0) == hash) return false
        prefs.edit().putInt("seen", hash).apply()
        return true
    }

    private fun problems(context: Context): String? {
        val parts = mutableListOf<String>()
        File(context.filesDir, CRASH_FILE).takeIf { it.exists() }?.let { parts += it.readText() }
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.R) parts += exitReasons(context)
        return parts.joinToString("\n\n").ifBlank { null }
    }

    fun clear(context: Context) {
        File(context.filesDir, CRASH_FILE).delete()
        File(context.filesDir, TRAIL_FILE).delete()
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.R) {
            context.getSharedPreferences(SEEN_PREFS, Context.MODE_PRIVATE).edit()
                .putLong("cleared_at", System.currentTimeMillis()).apply()
        }
    }

    private fun exitReasons(context: Context): List<String> {
        if (Build.VERSION.SDK_INT < Build.VERSION_CODES.R) return emptyList()
        val clearedAt = context.getSharedPreferences(SEEN_PREFS, Context.MODE_PRIVATE).getLong("cleared_at", 0L)
        val am = context.getSystemService(ActivityManager::class.java) ?: return emptyList()
        val exits = runCatching { am.getHistoricalProcessExitReasons(context.packageName, 0, 5) }
            .getOrDefault(emptyList())
        return exits
            .filter { it.timestamp > clearedAt }
            .filter {
                it.reason == ApplicationExitInfo.REASON_ANR ||
                    it.reason == ApplicationExitInfo.REASON_CRASH ||
                    it.reason == ApplicationExitInfo.REASON_CRASH_NATIVE
            }
            .take(2)
            .map { info ->
                val kind = when (info.reason) {
                    ApplicationExitInfo.REASON_ANR -> "Not responding (ANR)"
                    ApplicationExitInfo.REASON_CRASH -> "Crash"
                    else -> "Native crash"
                }
                buildString {
                    append("$kind at ${Instant.ofEpochMilli(info.timestamp)}")
                    info.description?.let { append(": ").append(it.take(500)) }
                    if (info.reason == ApplicationExitInfo.REASON_ANR) {
                        mainThread(info)?.let { append("\n").append(it) }
                    }
                }
            }
    }

    /** The main thread's stack from an ANR trace: the part that says what it was stuck on. */
    @RequiresApi(Build.VERSION_CODES.R)
    private fun mainThread(info: ApplicationExitInfo): String? = runCatching {
        info.traceInputStream?.bufferedReader()?.use { reader ->
            val lines = reader.lineSequence().take(4_000).toList()
            val start = lines.indexOfFirst { it.startsWith("\"main\"") }
            if (start < 0) lines.take(60).joinToString("\n")
            else lines.drop(start).takeWhile { it.isNotBlank() }.take(80).joinToString("\n")
        }
    }.getOrNull()
}
