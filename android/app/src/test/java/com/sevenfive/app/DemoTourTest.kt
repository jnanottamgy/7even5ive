package com.sevenfive.app

import com.sevenfive.app.ui.DemoTour
import com.sevenfive.app.ui.Routes
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test

class DemoTourTest {
    @Test
    fun `the tour has every step of the demo script, each on a tab`() {
        assertEquals(13, DemoTour.steps.size)
        val tabs = setOf(Routes.HOME, Routes.ATTENDANCE, Routes.MATERIALS, Routes.INBOX, Routes.REMINDERS)
        assertTrue(DemoTour.steps.all { it.route in tabs && it.title.isNotBlank() && it.say.isNotBlank() })
    }

    @Test
    fun `every live action appears exactly once`() {
        val actions = DemoTour.steps.mapNotNull { it.action }
        assertEquals(actions.toSet().size, actions.size)
        assertEquals(9, actions.size)
    }
}
