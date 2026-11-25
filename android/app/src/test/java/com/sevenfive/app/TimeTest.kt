package com.sevenfive.app

import com.sevenfive.app.util.Time
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNotNull
import org.junit.Test
import java.time.Instant
import java.time.ZoneId

class TimeTest {
    private val ist = ZoneId.of("Asia/Kolkata")

    @Test
    fun `parses IST card times without seconds and UTC fetch times with micros`() {
        assertNotNull(Time.parse("2026-11-27T23:59+05:30"))
        assertNotNull(Time.parse("2026-11-25T18:49:25.800171+00:00"))
        assertEquals(null, Time.parse("not a date"))
    }

    @Test
    fun `formats a due time in the phone's zone`() {
        val due = Time.parse("2026-11-27T23:59+05:30")!!
        assertEquals("Fri 27 Nov, 11:59 PM", Time.dayAndTime(due, ist))
    }

    @Test
    fun `says how soon`() {
        val now = Instant.parse("2026-11-25T10:00:00Z") // 15:30 IST
        assertEquals("in 2 days", Time.until(Time.parse("2026-11-27T23:59+05:30")!!, now, ist))
        assertEquals("tomorrow", Time.until(Time.parse("2026-11-26T18:00+05:30")!!, now, ist))
        assertEquals("in 3 h", Time.until(Time.parse("2026-11-25T18:30+05:30")!!, now, ist))
        assertEquals("in 20 min", Time.until(Time.parse("2026-11-25T15:50+05:30")!!, now, ist))
        assertEquals("overdue", Time.until(Time.parse("2026-11-24T09:00+05:30")!!, now, ist))
    }

    @Test
    fun `says how long ago`() {
        val now = Instant.parse("2026-11-25T10:00:00Z")
        assertEquals("just now", Time.ago(now.minusSeconds(20), now))
        assertEquals("5 min ago", Time.ago(now.minusSeconds(300), now))
        assertEquals("3 h ago", Time.ago(now.minusSeconds(3 * 3600), now))
        assertEquals("2 days ago", Time.ago(now.minusSeconds(2 * 86400 + 60), now))
    }
}
