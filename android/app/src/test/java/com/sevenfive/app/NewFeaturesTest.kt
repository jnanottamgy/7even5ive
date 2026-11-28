package com.sevenfive.app

import com.sevenfive.app.data.Item
import com.sevenfive.app.ui.screens.cgpaCutoff
import com.sevenfive.app.ui.screens.eligible
import com.sevenfive.app.ui.screens.finalNeeded
import com.sevenfive.app.ui.screens.findClash
import com.sevenfive.app.ui.screens.internalOutOf50
import com.sevenfive.app.ui.screens.shortName
import com.sevenfive.app.util.Time
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNotNull
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test
import java.time.OffsetDateTime

class NewFeaturesTest {
    // --- placement eligibility -------------------------------------------------------------------

    @Test fun `the cut-off is read from the mail's words`() {
        assertEquals(7.0, cgpaCutoff("Eligibility: CGPA 7.0 and above, no active backlogs.")!!, 0.0)
        assertEquals(6.5, cgpaCutoff("Min. CGPA of 6.5 required")!!, 0.0)
        assertNull(cgpaCutoff("Open to all branches"))
        assertNull(cgpaCutoff(null))
    }

    @Test fun `eligibility compares the student's CGPA with the cut-off`() {
        val drive = Item(id = 1, kind = "deadline", details = "Eligibility: CGPA 7.0 and above")
        assertEquals(true, eligible(drive, 8.1))
        assertEquals(true, eligible(drive, 7.0))
        assertEquals(false, eligible(drive, 6.9))
        assertNull(eligible(drive, null))
        assertNull(eligible(Item(id = 2, details = "No conditions"), 8.0))
    }

    // --- grade what-if ---------------------------------------------------------------------------

    @Test fun `internal marks are scaled to 50`() {
        assertEquals(40.0, internalOutOf50(24.0, 30.0), 1e-9)
        assertEquals(0.0, internalOutOf50(0.0, 0.0), 1e-9)
    }

    @Test fun `the final exam needs twice what's missing, never below the pass mark`() {
        // 40 internal: an A (70) needs 30 more of 50, so 60 of 100.
        assertEquals(60, finalNeeded(40.0, 70))
        // A pass (40) is already there, but the final exam still has its own minimum.
        assertEquals(35, finalNeeded(40.0, 40))
        // An O (90) from 30 internal needs 120: out of reach.
        assertNull(finalNeeded(30.0, 90))
        // Rounds up: 42.5 internal, B+ (60) needs 35 of 100.
        assertEquals(35, finalNeeded(42.5, 60))
        assertEquals(39, finalNeeded(40.5, 60))
    }

    // --- clash warning ---------------------------------------------------------------------------

    private fun due(id: Int, kind: String, at: String) = Item(id = id, kind = kind, title = "T$id", dueAt = at)

    @Test fun `two things within 48 hours make a clash, things further apart don't`() {
        val now = OffsetDateTime.parse("2026-11-27T09:00+05:30").toInstant()
        val clash = findClash(
            listOf(
                due(1, "exam", "2026-11-30T09:00+05:30"),
                due(2, "deadline", "2026-11-30T23:59+05:30"),
                due(3, "deadline", "2026-12-06T23:59+05:30"),
                due(4, "material", "2026-11-30T10:00+05:30"),
            ),
            now,
        )
        assertNotNull(clash)
        assertEquals(listOf(1, 2), clash!!.items.map { it.first.id })
        assertTrue(clash.advice.startsWith("Finish T2 early"))

        assertNull(findClash(listOf(due(1, "deadline", "2026-11-28T10:00+05:30"), due(2, "deadline", "2026-12-02T10:00+05:30")), now))
    }

    @Test fun `past items never make a clash`() {
        val now = OffsetDateTime.parse("2026-12-01T09:00+05:30").toInstant()
        assertNull(findClash(listOf(due(1, "exam", "2026-11-30T09:00+05:30"), due(2, "deadline", "2026-11-30T23:59+05:30")), now))
    }

    // --- countdown -------------------------------------------------------------------------------

    @Test fun `the countdown reads to the second, with days when it's further out`() {
        val now = OffsetDateTime.parse("2026-11-27T09:00:00+05:30").toInstant()
        assertEquals("07:22:19", Time.countdown(OffsetDateTime.parse("2026-11-27T16:22:19+05:30"), now))
        assertEquals("2d 01:00:00", Time.countdown(OffsetDateTime.parse("2026-11-29T10:00:00+05:30"), now))
        assertEquals("now", Time.countdown(OffsetDateTime.parse("2026-11-27T08:00:00+05:30"), now))
    }

    @Test fun `subjects get the short names students use`() {
        assertEquals("DBMS", shortName("Database Management Systems", "CS52"))
        assertEquals("DAA", shortName("Design and Analysis of Algorithms", "CS53"))
        assertEquals("CN", shortName("Computer Networks", "CS51"))
        assertEquals("Physics", shortName("Physics", "PH1"))
        assertEquals("CS9", shortName("", "CS9"))
    }
}
