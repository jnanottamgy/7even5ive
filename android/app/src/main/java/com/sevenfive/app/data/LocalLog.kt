package com.sevenfive.app.data

import android.content.Context
import java.time.Instant
import java.time.OffsetDateTime
import java.time.ZoneId

/**
 * What the student does that only this phone needs to remember: how far they got with each
 * placement drive, and when they marked things done (for "on time this month"). Kept in the
 * app's private storage, keyed by student, so two people on one phone never see each other's;
 * nothing here leaves the phone.
 */
object LocalLog {
    private const val PREFS = "local_log"
    private fun prefs(context: Context) = context.getSharedPreferences(PREFS, Context.MODE_PRIVATE)

    /** Android reads the file on a background thread from this first call; later reads don't wait. */
    fun warm(context: Context) {
        prefs(context)
    }

    // --- placement pipeline ------------------------------------------------------------------------

    /** The steps of a placement drive, in order; 0 is "not started". */
    val stages = listOf("Registered", "Test", "Interview", "Offer")
    const val NOT_APPLYING = -1

    fun stage(context: Context, sid: Int, itemId: Int): Int = prefs(context).getInt("s${sid}_stage_$itemId", 0)

    fun setStage(context: Context, sid: Int, itemId: Int, stage: Int) {
        prefs(context).edit().putInt("s${sid}_stage_$itemId", stage).apply()
    }

    // --- done history ------------------------------------------------------------------------------

    /** Every item seen with a due date, so a deadline that passed without "done" still counts. */
    fun noteSeen(context: Context, sid: Int, items: List<Item>) {
        val p = prefs(context)
        val edit = p.edit()
        var changed = false
        items.forEach { item ->
            val due = item.dueAt ?: return@forEach
            if (item.kind != "deadline" && item.kind != "exam") return@forEach
            if (p.getString("s${sid}_seen_${item.id}", null) != due) {
                edit.putString("s${sid}_seen_${item.id}", due)
                changed = true
            }
        }
        if (changed) edit.apply()
    }

    fun noteDone(context: Context, sid: Int, item: Item, at: Instant = Instant.now()) {
        val edit = prefs(context).edit().putLong("s${sid}_done_${item.id}", at.toEpochMilli())
        item.dueAt?.let { edit.putString("s${sid}_seen_${item.id}", it) }
        edit.apply()
    }

    fun forgetDone(context: Context, sid: Int, itemId: Int) {
        prefs(context).edit().remove("s${sid}_done_$itemId").apply()
    }

    /** This month's deadlines whose time has come (or that are done): how many were done on time. */
    data class Month(val onTime: Int, val total: Int)

    fun thisMonth(context: Context, sid: Int, now: Instant = Instant.now(), zone: ZoneId = ZoneId.systemDefault()): Month {
        val p = prefs(context)
        val month = now.atZone(zone).let { it.year to it.monthValue }
        var onTime = 0
        var total = 0
        p.all.forEach { (key, value) ->
            val seen = "s${sid}_seen_"
            if (!key.startsWith(seen) || value !is String) return@forEach
            val id = key.removePrefix(seen)
            val due = runCatching { OffsetDateTime.parse(value).toInstant() }.getOrNull() ?: return@forEach
            val dueZoned = due.atZone(zone)
            if ((dueZoned.year to dueZoned.monthValue) != month) return@forEach
            val doneKey = "s${sid}_done_$id"
            val doneAt = if (p.contains(doneKey)) Instant.ofEpochMilli(p.getLong(doneKey, 0)) else null
            if (doneAt == null && due.isAfter(now)) return@forEach // not due yet, not done: doesn't count yet
            total += 1
            if (doneAt != null && !doneAt.isAfter(due)) onTime += 1
        }
        return Month(onTime, total)
    }
}
