package com.sevenfive.app

import kotlinx.serialization.decodeFromString
import com.sevenfive.app.data.AppJson
import com.sevenfive.app.data.Cards
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNotNull
import org.junit.Assert.assertTrue
import org.junit.Test

class CardsParsingTest {
    private fun fixture(): String =
        requireNotNull(javaClass.classLoader?.getResource("cards.json")) { "cards.json missing" }.readText()

    @Test
    fun `parses a real cards response from the demo`() {
        val cards = AppJson.decodeFromString<Cards>(fixture())
        assertEquals("Demo Student", cards.student?.name)
        assertEquals("DBMS Assignment 3", cards.dueThisWeek.first().title)
        assertEquals("bot", cards.dueThisWeek.first().route)
        assertTrue(cards.attendance.connected)
        val dbms = cards.attendance.subjects.first()
        assertEquals("CS52", dbms.code)
        assertEquals("short", dbms.status)
        assertEquals(2, dbms.mustAttend)
        assertEquals(5, dbms.semester?.canSkipRest)
        assertTrue(dbms.message.startsWith("CS52 73.33%"))
        assertEquals(2, cards.filtered)
        assertEquals(0.88, cards.opportunities.first().relevance!!, 1e-9)
        assertEquals(1, cards.reminders.size)
    }

    @Test
    fun `an approval's title comes from the cards`() {
        val cards = AppJson.decodeFromString<Cards>(fixture())
        val approval = cards.approvals.first()
        assertEquals("add_to_calendar", approval.action)
        assertEquals(1, approval.itemId)
        assertEquals("DBMS Assignment 3", cards.itemById(approval.itemId)?.title)
    }

    @Test
    fun `unknown fields and missing sections never crash`() {
        val cards = AppJson.decodeFromString<Cards>(
            """{"brand_new": {"x": 1}, "attendance": {"connected": false}, "due_this_week": [{"id": 3, "kind": "exam"}]}"""
        )
        assertFalse(cards.attendance.connected)
        assertTrue(cards.attendance.subjects.isEmpty())
        assertEquals("exam", cards.dueThisWeek.single().kind)
        assertNotNull(cards.reminders)
    }
}
