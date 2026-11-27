package com.sevenfive.app

import com.sevenfive.app.data.AppJson
import com.sevenfive.app.data.Cards
import com.sevenfive.app.data.Slot
import com.sevenfive.app.data.SubjectAttendance
import com.sevenfive.app.ui.screens.matches
import com.sevenfive.app.ui.screens.toolLabel
import com.sevenfive.app.util.Week
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test
import java.time.LocalDate
import java.time.LocalDateTime

class WeekTest {
    private val slots = listOf(
        Slot("Mon", "09:00:00", "09:55:00", "CS52"),
        Slot("Mon", "10:00:00", "10:55:00", "CS54"),
        Slot("Wed", "09:00:00", "09:55:00", "CS52"),
        Slot("Fri", "09:00:00", "09:55:00", "CS52"),
        Slot("Fri", "11:00:00", "11:55:00", "CS51"),
    )

    @Test
    fun `projected percent adds attended and skipped classes to the portal's counts`() {
        val s = SubjectAttendance(code = "CS52", attended = 22, held = 30)
        assertEquals(73.33, Week.projected(s, 0, 0), 0.01)
        assertEquals(22 * 100.0 / 32, Week.projected(s, 0, 2), 1e-9)
        assertEquals(24 * 100.0 / 33, Week.projected(s, 2, 1), 1e-9)
        assertEquals(0.0, Week.projected(SubjectAttendance(), 0, 0), 0.0)
    }

    @Test
    fun `classes before a day count from now, not from midnight`() {
        // Monday 2026-11-23, 09:30: the 09:00 class has started, the 10:00 one hasn't.
        val now = LocalDateTime.of(2026, 11, 23, 9, 30)
        val friday = LocalDate.of(2026, 11, 27)
        assertEquals(mapOf("CS54" to 1, "CS52" to 1), Week.before(slots, now, friday))
        assertEquals(mapOf("CS52" to 1, "CS51" to 1), Week.on(slots, friday))
        assertEquals(emptyMap<String, Int>(), Week.before(slots, now, now.toLocalDate()))
    }

    @Test
    fun `search needs every word somewhere, in any order`() {
        assertTrue(matches("os notes", "OS_Unit4_Deadlocks notes", "Operating Systems"))
        assertTrue(matches("systems deadlocks", "OS_Unit4_Deadlocks", "Operating Systems"))
        assertFalse(matches("dbms notes", "OS_Unit4_Deadlocks", "Operating Systems"))
    }

    @Test
    fun `the AI log names tools in plain words`() {
        assertEquals("Send an email", toolLabel("send_email"))
        assertEquals("Some new tool", toolLabel("some_new_tool"))
    }

    @Test
    fun `new card fields parse, and old servers without them still parse`() {
        val json = """
            {"subjects": ["Operating Systems"],
             "materials": [{"id": 3, "kind": "material", "title": "OS.pdf", "has_file": true}],
             "timetable": {"connected": true, "data": [{"day": "Mon", "start": "09:00:00", "end": "09:55:00", "subject_code": "CS54"}]},
             "marks": {"connected": true, "data": [{"subject_code": "CS54", "component": "CIE-1", "scored": 24.0, "maximum": 30.0}]},
             "results": {"connected": true, "data": {"subjects": [], "semesters": [{"semester": 4, "sgpa": 8.45, "cgpa": 8.58}]}},
             "audit": [{"id": 9, "tool": "send_email", "decision": "deny", "reason": "policy", "at": "2026-11-26T10:00:00+05:30"}]}
        """.trimIndent()
        val cards = AppJson.decodeFromString(Cards.serializer(), json)
        assertTrue(cards.materials.single().hasFile)
        assertEquals("CS54", cards.timetable.data.single().code)
        assertEquals(8.58, cards.results.data.semesters.single().cgpa!!, 0.0)
        assertEquals("deny", cards.audit.single().decision)
        assertFalse(AppJson.decodeFromString(Cards.serializer(), "{}").timetable.connected)
    }
}
