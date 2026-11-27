package com.sevenfive.app.util

import com.sevenfive.app.data.Slot
import com.sevenfive.app.data.SubjectAttendance
import java.time.DayOfWeek
import java.time.LocalDate
import java.time.LocalDateTime
import java.time.LocalTime

/**
 * The week from the portal's timetable, and the planner's what-if maths. Plain arithmetic on
 * the portal's own counts: attended / held, with the classes you'd attend or skip added in.
 */
object Week {
    private val names = listOf("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun")

    fun dayOf(slot: Slot): DayOfWeek? = names.indexOf(slot.day).takeIf { it >= 0 }?.let { DayOfWeek.of(it + 1) }

    fun time(value: String): LocalTime? = runCatching { LocalTime.parse(value) }.getOrNull()

    fun short(day: DayOfWeek): String = names[day.value - 1]

    fun on(slots: List<Slot>, day: DayOfWeek): List<Slot> =
        slots.filter { dayOf(it) == day }.sortedBy { time(it.start) }

    /**
     * Classes per subject code that start after [now] and before [date] (that day excluded):
     * the ones you'd attend on the way to a day you plan to skip.
     */
    fun before(slots: List<Slot>, now: LocalDateTime, date: LocalDate): Map<String, Int> {
        val out = mutableMapOf<String, Int>()
        var day = now.toLocalDate()
        while (day.isBefore(date)) {
            for (s in on(slots, day.dayOfWeek)) {
                val start = time(s.start) ?: continue
                if (LocalDateTime.of(day, start).isAfter(now)) out[s.code] = (out[s.code] ?: 0) + 1
            }
            day = day.plusDays(1)
        }
        return out
    }

    /** Per subject code, the classes held on [date]. */
    fun on(slots: List<Slot>, date: LocalDate): Map<String, Int> =
        on(slots, date.dayOfWeek).groupingBy { it.code }.eachCount()

    /** Percent after attending [attend] more classes and missing [skip]. */
    fun projected(s: SubjectAttendance, attend: Int, skip: Int): Double {
        val held = s.held + attend + skip
        return if (held == 0) 0.0 else (s.attended + attend) * 100.0 / held
    }
}
