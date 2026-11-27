package com.sevenfive.app.notify

import android.annotation.SuppressLint
import android.content.Context

/**
 * A reminder reaches this phone two ways: its own alarm ([Alerts], on time even offline) and the
 * server's outbox ([OutboxPuller], which also brings reminders this phone never heard of). Both
 * ask here before showing one; the second to ask for the same reminder stays quiet, so a student
 * never gets the same reminder twice (decision 41).
 */
object ReminderLog {
    private const val PREFS = "reminder_log"
    private const val KEY = "shown"

    /** True the first time [reminderId] asks: show it. False after that. */
    @Synchronized
    @SuppressLint("ApplySharedPref") // on purpose: see below
    fun claim(context: Context, reminderId: Int, now: Long = System.currentTimeMillis()): Boolean {
        val prefs = context.getSharedPreferences(PREFS, Context.MODE_PRIVATE)
        val (first, kept) = ShownReminders.parse(prefs.getString(KEY, null)).claim(reminderId, now)
        // commit, not apply: an alarm's receiver can be the last thing this process does.
        prefs.edit().putString(KEY, kept.encode()).commit()
        return first
    }

    /** Someone else uses the phone now: their reminders' ids mean nothing here any more. */
    @Synchronized
    @SuppressLint("ApplySharedPref") // on disk before the next person's reminders arrive
    fun forget(context: Context) {
        context.getSharedPreferences(PREFS, Context.MODE_PRIVATE).edit().remove(KEY).commit()
    }
}

/** Reminders already shown, oldest first, with when. Pure, so its rules are tested on their own. */
data class ShownReminders(val entries: List<Pair<Int, Long>> = emptyList()) {
    /** Whether [id] is new, and what to keep: a week of entries, at most [MAX]. */
    fun claim(id: Int, now: Long): Pair<Boolean, ShownReminders> {
        // A phone that was offline for days can still pull a reminder its alarm showed then.
        val recent = entries.filter { now - it.second < KEEP_MILLIS }
        if (recent.any { it.first == id }) return false to ShownReminders(recent)
        return true to ShownReminders((recent + (id to now)).takeLast(MAX))
    }

    fun encode(): String = entries.joinToString(",") { (id, at) -> "$id@$at" }

    companion object {
        const val KEEP_MILLIS = 7 * 24 * 60 * 60 * 1000L
        const val MAX = 200

        fun parse(raw: String?): ShownReminders = ShownReminders(
            raw.orEmpty().split(',').mapNotNull { part ->
                val fields = part.split('@')
                val id = fields.getOrNull(0)?.toIntOrNull()
                val at = fields.getOrNull(1)?.toLongOrNull()
                if (fields.size == 2 && id != null && at != null) id to at else null
            },
        )
    }
}
