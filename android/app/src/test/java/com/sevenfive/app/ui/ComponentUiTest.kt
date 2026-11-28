package com.sevenfive.app.ui

import android.app.Application
import androidx.compose.ui.test.assertIsSelected
import androidx.compose.ui.test.hasClickAction
import androidx.compose.ui.test.hasContentDescription
import androidx.compose.ui.test.junit4.createComposeRule
import androidx.compose.ui.test.onNodeWithContentDescription
import androidx.compose.ui.test.onNodeWithText
import androidx.compose.ui.test.onRoot
import androidx.compose.ui.test.performClick
import androidx.test.core.app.ApplicationProvider
import com.github.takahirom.roborazzi.captureRoboImage
import com.sevenfive.app.data.Cards
import com.sevenfive.app.data.LocalLog
import com.sevenfive.app.ui.components.OPENING_SEQUENCE_MILLIS
import com.sevenfive.app.ui.components.OpeningScreen
import com.sevenfive.app.ui.screens.PlacementCard
import com.sevenfive.app.ui.screens.cgpaCutoff
import com.sevenfive.app.ui.theme.SevenFiveTheme
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Rule
import org.junit.Test
import org.junit.runner.RunWith
import org.robolectric.RobolectricTestRunner
import org.robolectric.annotation.Config
import org.robolectric.annotation.GraphicsMode

/** Single pieces of the app, driven frame by frame where timing is the point. */
@RunWith(RobolectricTestRunner::class)
@Config(application = Application::class, qualifiers = "w411dp-h891dp-xxhdpi")
@GraphicsMode(GraphicsMode.Mode.NATIVE)
class ComponentUiTest {
    @get:Rule val rule = createComposeRule()

    @Test
    fun `the opening hands over the moment its sequence ends, and is read out once`() {
        var finished = false
        rule.mainClock.autoAdvance = false
        rule.setContent { SevenFiveTheme { OpeningScreen(onFinished = { finished = true }) } }
        rule.mainClock.advanceTimeBy(2_600L) // "sorted." on its way in from the right
        rule.onRoot().captureRoboImage("build/outputs/roborazzi/0-opening-2600ms.png")
        rule.mainClock.advanceTimeBy(OPENING_SEQUENCE_MILLIS - 2_600L - 100L)
        assertFalse("not before the sequence ends", finished)
        rule.mainClock.advanceTimeBy(200L)
        assertTrue("the app opens as it ends", finished)
        rule.onNodeWithContentDescription("Your semester, sorted.").assertExists()
    }

    @Test
    fun `a placement drive works out eligibility, and its steps are remembered and announced`() {
        val cards = Recorded.model<Cards>("cards")
        val drive = cards.opportunities.first { cgpaCutoff(it.details) != null }
        val context = ApplicationProvider.getApplicationContext<Application>()
        val sid = cards.student!!.id
        rule.setContent { SevenFiveTheme { PlacementCard(drive, cards) } }

        rule.onNodeWithText("You clear the cut-off", substring = true).assertExists()
        rule.onNode(hasContentDescription("Test") and hasClickAction()).performClick()
        rule.waitForIdle()
        rule.onNode(hasContentDescription("Registered, reached")).assertIsSelected()
        rule.onNode(hasContentDescription("Test, reached")).assertIsSelected()
        rule.onNode(hasContentDescription("Interview") and hasClickAction()).assertExists()
        assertEquals("kept on the phone", 2, LocalLog.stage(context, sid, drive.id))
        rule.onRoot().captureRoboImage("build/outputs/roborazzi/9-placement-card.png")

        rule.onNode(hasContentDescription("Test, reached")).performClick() // tap again: a step back
        rule.waitForIdle()
        assertEquals(1, LocalLog.stage(context, sid, drive.id))
    }
}
