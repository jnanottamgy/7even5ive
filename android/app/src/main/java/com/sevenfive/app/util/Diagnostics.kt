package com.sevenfive.app.util

import android.app.ActivityManager
import android.app.ApplicationExitInfo
import android.content.Context
import android.os.Build
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
        return parts.joinToString("\n\n").ifBlank { null }
    }

    /** True once per new problem, so the app can say "it closed last time" exactly once. */
    fun hasUnseen(context: Context): Boolean {
        val report = report(context) ?: return false
        val prefs = context.getSharedPreferences(SEEN_PREFS, Context.MODE_PRIVATE)
        val hash = report.hashCode()
        if (prefs.getInt("seen", 0) == hash) return false
        prefs.edit().putInt("seen", hash).apply()
        return true
    }

    fun clear(context: Context) {
        File(context.filesDir, CRASH_FILE).delete()
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
    private fun mainThread(info: ApplicationExitInfo): String? = runCatching {
        info.traceInputStream?.bufferedReader()?.use { reader ->
            val lines = reader.lineSequence().take(4_000).toList()
            val start = lines.indexOfFirst { it.startsWith("\"main\"") }
            if (start < 0) lines.take(60).joinToString("\n")
            else lines.drop(start).takeWhile { it.isNotBlank() }.take(80).joinToString("\n")
        }
    }.getOrNull()
}
