package com.sevenfive.app.portal

import android.net.Uri
import android.util.Log
import java.text.SimpleDateFormat
import java.util.Date
import java.util.Locale

/**
 * A step-by-step log of the portal test: every portal request and answer, the login's field
 * names, page loads, errors, check changes and the page's console messages. It goes to logcat
 * (tag "SevenFivePortal", readable with `adb logcat -s SevenFivePortal` when the phone is plugged
 * in) and is kept in memory for the test screen's Copy / Share buttons.
 *
 * Never logged: field values, cookie values, query strings. Only hosts, paths, names, counts.
 */
object PortalLog {
    const val TAG = "SevenFivePortal"
    private const val MAX = 600
    private val lines = ArrayDeque<String>()
    private val clock = SimpleDateFormat("HH:mm:ss.SSS", Locale.US)

    fun add(msg: String) {
        val line = "${clock.format(Date())} $msg"
        synchronized(lines) {
            lines.addLast(line)
            while (lines.size > MAX) lines.removeFirst()
        }
        Log.i(TAG, msg)
    }

    fun dump(): String = synchronized(lines) { lines.joinToString("\n") }

    fun clear() = synchronized(lines) { lines.clear() }

    /** Host and path only: a query string can carry personal details. */
    fun where(url: String?): String = url?.let { Uri.parse(it) }?.let { "${it.host.orEmpty()}${it.path.orEmpty()}" } ?: "?"
}
