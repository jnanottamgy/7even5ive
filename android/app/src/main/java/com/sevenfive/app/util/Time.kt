package com.sevenfive.app.util

import java.time.Duration
import java.time.Instant
import java.time.LocalDate
import java.time.OffsetDateTime
import java.time.ZoneId
import java.time.format.DateTimeFormatter
import java.time.temporal.ChronoUnit
import java.util.Locale

/** Times arrive as ISO 8601 with an offset (IST for cards, UTC for fetched_at). */
object Time {
    private val day = DateTimeFormatter.ofPattern("EEE d MMM", Locale.ENGLISH)
    private val clock = DateTimeFormatter.ofPattern("h:mm a", Locale.ENGLISH)

    fun parse(iso: String?): OffsetDateTime? =
        iso?.let { runCatching { OffsetDateTime.parse(it) }.getOrNull() }

    fun parseDate(iso: String?): LocalDate? =
        iso?.let { runCatching { LocalDate.parse(it.take(10)) }.getOrNull() }

    /** "Fri 27 Nov, 11:59 PM" in the phone's zone. */
    fun dayAndTime(at: OffsetDateTime, zone: ZoneId = ZoneId.systemDefault()): String {
        val local = at.atZoneSameInstant(zone)
        return "${day.format(local)}, ${clock.format(local).uppercase(Locale.ENGLISH)}"
    }

    fun dayOnly(date: LocalDate): String = day.format(date)

    /** "14:00" (a timetable slot, India time) -> "2:00 PM". Unreadable input comes back as it is. */
    fun hourMinute(hhmm: String): String =
        runCatching { java.time.LocalTime.parse(hhmm).format(clock).uppercase(Locale.ENGLISH) }.getOrDefault(hhmm)

    /** "in 2 days", "tomorrow", "in 3 h", "overdue" — how soon, at a glance. */
    fun until(at: OffsetDateTime, now: Instant = Instant.now(), zone: ZoneId = ZoneId.systemDefault()): String {
        val target = at.toInstant()
        if (target.isBefore(now)) return "overdue"
        val minutes = Duration.between(now, target).toMinutes()
        if (minutes < 60) return "in ${maxOf(1, minutes)} min"
        if (minutes < 12 * 60) return "in ${minutes / 60} h"
        val days = ChronoUnit.DAYS.between(
            now.atZone(zone).toLocalDate(), target.atZone(zone).toLocalDate()
        )
        return when (days) {
            0L -> "today"
            1L -> "tomorrow"
            else -> "in $days days"
        }
    }

    /** "just now", "5 min ago", "3 h ago", "2 days ago". */
    fun ago(then: Instant, now: Instant = Instant.now()): String {
        val minutes = Duration.between(then, now).toMinutes()
        return when {
            minutes < 1 -> "just now"
            minutes < 60 -> "$minutes min ago"
            minutes < 48 * 60 -> "${minutes / 60} h ago"
            else -> "${minutes / (24 * 60)} days ago"
        }
    }
}
