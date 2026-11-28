package com.sevenfive.app.ui

import android.app.Application
import androidx.compose.ui.test.assertIsSelected
import androidx.compose.ui.test.hasClickAction
import androidx.compose.ui.test.hasContentDescription
import androidx.compose.ui.test.hasText
import androidx.compose.ui.test.junit4.createComposeRule
import androidx.compose.ui.test.onAllNodesWithText
import androidx.compose.ui.test.onNodeWithContentDescription
import androidx.compose.ui.test.onNodeWithText
import androidx.compose.ui.test.onRoot
import androidx.compose.ui.test.performClick
import com.github.takahirom.roborazzi.captureRoboImage
import java.util.TimeZone
import org.junit.After
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Before
import org.junit.Rule
import org.junit.Test
import org.junit.runner.RunWith
import org.robolectric.RobolectricTestRunner
import org.robolectric.annotation.Config
import org.robolectric.annotation.GraphicsMode

/**
 * Taps that change the screen at once, against a server that takes its time (or says no): the
 * screen never waits for an answer it can show without, and takes a change back when refused.
 */
@RunWith(RobolectricTestRunner::class)
@Config(application = Application::class, qualifiers = "w411dp-h891dp-xxhdpi")
@GraphicsMode(GraphicsMode.Mode.NATIVE)
class SeamlessUiTest {
    @get:Rule val rule = createComposeRule()

    private lateinit var server: RecordedServer
    private val zone = TimeZone.getDefault()

    @Before
    fun start() {
        server = demoServer()
        rule.startDemoApp(server)
        rule.segment("Week").performClick()
        rule.waitForIdle()
    }

    @After
    fun stop() {
        server.close()
        TimeZone.setDefault(zone)
    }

    /** The first card of the week: due soonest. */
    private val first = "DCN CIE-2 (units 3 and 4)"

    @Test
    fun `Done takes the card away at once, and Undo brings it back, before the server has answered`() {
        server.slow["POST /api/tools/mark_done"] = 3_000
        server.slow["POST /api/tools/reopen"] = 3_000
        assertTrue(rule.shown(first))

        rule.onAllNodesWithText("Done")[0].performClick()
        rule.waitForIdle()
        assertFalse("gone on the tap, not after the server", rule.shown(first))

        rule.onNodeWithText("Undo").performClick()
        rule.waitForIdle()
        assertTrue("back on the tap of Undo", rule.shown(first))

        // Both reach the server, in the order they were tapped.
        rule.waitForServer(15_000) { "POST /api/tools/reopen" in server.asked }
        assertTrue(server.asked.indexOf("POST /api/tools/mark_done") < server.asked.indexOf("POST /api/tools/reopen"))
        rule.waitForServer(15_000) { server.asked.count { it == "GET /api/cards" } >= 3 }
        rule.waitForIdle()
        assertTrue("still there once the server has caught up", rule.shown(first))
    }

    @Test
    fun `a Done the server refuses comes back, with its reason`() {
        server.refuse["POST /api/tools/mark_done"] = 403 to "That item has gone from your list."
        rule.onAllNodesWithText("Done")[0].performClick()
        rule.waitForIdle()
        rule.waitForServer { rule.shown(first) }
        rule.waitFor("That item has gone from your list.")
    }

    @Test
    fun `a Done the server takes stays done after the next poll`() {
        rule.onAllNodesWithText("Done")[0].performClick()
        rule.waitForServer { "POST /api/tools/mark_done" in server.asked }
        rule.waitForServer { server.asked.count { it == "GET /api/cards" } >= 2 } // the one after it
        rule.waitForIdle()
        assertFalse(rule.shown(first))
    }

    @Test
    fun `a reminder shows as set the moment it is chosen`() {
        server.slow["POST /api/tools/set_reminder"] = 3_000
        // The card's own button says when ("Reminder Sat 28 Nov, 9:15 PM"); the message says so too.
        fun buttons() = rule.onAllNodes(hasText("Reminder ", substring = true) and hasClickAction()).fetchSemanticsNodes().size
        val before = buttons()
        // The second card (due in two days): three hours before is still ahead.
        rule.onAllNodesWithText("Remind me")[1].performClick()
        rule.waitForIdle()
        rule.onNodeWithText("3 hours before").performClick()
        rule.waitForIdle()
        assertEquals("the card says when, before the server has answered", before + 1, buttons())
        // And it stays so once the server has it.
        rule.waitForServer(15_000) { server.asked.count { it == "GET /api/cards" } >= 2 }
        rule.waitForIdle()
        assertEquals(before + 1, buttons())
    }

    @Test
    fun `a quick double tap on Settings opens it once`() {
        rule.mainClock.autoAdvance = false
        val gear = rule.onNodeWithContentDescription("Settings")
        gear.performClick()
        gear.performClick() // before the first has drawn a frame
        rule.mainClock.autoAdvance = true
        rule.waitForIdle()
        rule.onNode(hasContentDescription("Back")).performClick()
        rule.waitForIdle()
        rule.tab("This week").assertIsSelected() // one Back, and the tabs are back
    }

    @Test
    fun `a screen change never shows two screens at once`() {
        rule.segment("Today").performClick()
        rule.waitForIdle()
        // Frames of a tab switch, a pushed screen and Back, every 30 ms (build/outputs/roborazzi/frames).
        rule.mainClock.autoAdvance = false
        rule.tab("Inbox").performClick()
        film("1-tab")
        rule.onNodeWithContentDescription("Settings").performClick()
        film("2-push")
        rule.onNode(hasContentDescription("Back")).performClick()
        film("3-back")
        rule.mainClock.autoAdvance = true
        rule.waitForIdle()
        rule.tab("Inbox").assertIsSelected()
    }

    private fun film(name: String) {
        var at = 0L
        for (t in listOf(0L, 30L, 60L, 90L, 120L, 150L, 210L, 300L, 400L)) {
            rule.mainClock.advanceTimeBy(t - at)
            at = t
            rule.onRoot().captureRoboImage("build/outputs/roborazzi/frames/$name-${"%03d".format(t)}ms.png")
        }
    }

    @Test
    fun `Files opens at once the second time, and a subject at once the first time`() {
        rule.tab("Files").performClick()
        rule.waitFor("Database Management Systems")
        // Each subject's first shelf is fetched ahead, behind the list.
        rule.waitForServer { server.asked.count { it == "POST /api/tools/list_library_files" } >= 3 }
        server.slow["POST /api/tools/list_library"] = 5_000
        server.slow["POST /api/tools/list_library_files"] = 5_000

        rule.tab("Inbox").performClick()
        rule.waitForIdle()
        rule.tab("Files").performClick()
        rule.waitForIdle()
        assertTrue("kept: no skeleton while it is read again", rule.shown("Database Management Systems"))

        rule.onNodeWithText("Database Management Systems").performClick()
        rule.waitForIdle()
        assertTrue("fetched ahead: no spinner", rule.shown("DBMS unit 3 notes"))
    }
}
