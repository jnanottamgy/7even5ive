package com.sevenfive.app.ui

import android.app.Application
import androidx.compose.ui.semantics.SemanticsNode
import androidx.compose.ui.semantics.SemanticsProperties
import androidx.compose.ui.semantics.getOrNull
import androidx.compose.ui.test.assertCountEquals
import androidx.compose.ui.test.assertIsDisplayed
import androidx.compose.ui.test.assertIsSelected
import androidx.compose.ui.test.hasClickAction
import androidx.compose.ui.test.hasContentDescription
import androidx.compose.ui.test.hasText
import androidx.compose.ui.test.junit4.createComposeRule
import androidx.compose.ui.test.onAllNodesWithText
import androidx.compose.ui.test.onRoot
import androidx.compose.ui.test.performClick
import androidx.compose.ui.test.performScrollTo
import androidx.compose.ui.test.performTouchInput
import androidx.compose.ui.test.click
import androidx.compose.ui.unit.dp
import com.github.takahirom.roborazzi.captureRoboImage
import org.junit.After
import org.junit.Assert.assertTrue
import org.junit.Before
import org.junit.Rule
import org.junit.Test
import org.junit.runner.RunWith
import org.robolectric.RobolectricTestRunner
import org.robolectric.annotation.Config
import org.robolectric.annotation.GraphicsMode
import java.util.TimeZone

/**
 * The real app, on a phone-sized screen, without a phone: its own container, view models and
 * navigation, signed in as the demo, talking to a local server that answers with the real
 * server's recorded answers (Recorded.kt). Each test drives it as a student would and saves
 * screenshots to app/build/outputs/roborazzi for review.
 */
@RunWith(RobolectricTestRunner::class)
@Config(application = Application::class, qualifiers = "w411dp-h891dp-xxhdpi")
@GraphicsMode(GraphicsMode.Mode.NATIVE)
class AppUiTest {
    @get:Rule val rule = createComposeRule()

    private lateinit var server: RecordedServer
    private val zone = TimeZone.getDefault()

    @Before
    fun start() {
        server = demoServer()
        rule.startDemoApp(server)
    }

    @After
    fun stop() {
        server.close()
        TimeZone.setDefault(zone)
    }

    private fun shot(name: String) = rule.onRoot().captureRoboImage("build/outputs/roborazzi/$name.png")

    private fun tab(label: String) = rule.tab(label)

    private fun segment(label: String) = rule.segment(label)

    private fun waitFor(text: String) = rule.waitFor(text)

    @Test
    fun `every tab opens with the demo's data, and Home always comes back to Today`() {
        tab("This week").assertIsSelected()
        segment("Today").assertIsSelected()
        shot("1-home-today")
        assertTrue(accessibility("Home, Today").joinToString("\n"), accessibility("Home, Today").isEmpty())

        segment("Week").performClick()
        rule.waitForIdle()
        segment("Week").assertIsSelected()
        shot("2-home-week")

        tab("Attendance").performClick()
        rule.waitForIdle()
        tab("Attendance").assertIsSelected()
        waitFor("Database Management Systems")
        shot("3-attendance")

        tab("Files").performClick()
        rule.waitForIdle()
        waitFor("Database Management Systems")
        shot("4-files")

        tab("Inbox").performClick()
        rule.waitForIdle()
        tab("Inbox").assertIsSelected()
        shot("5-inbox")
        segment("Placements").performClick()
        rule.waitForIdle()
        shot("6-inbox-placements")

        // Back to Home from anywhere: Home, on its first page (Today), whatever page it was left on.
        tab("This week").performClick()
        rule.waitForIdle()
        tab("This week").assertIsSelected()
        segment("Today").assertIsSelected()
        segment("Week").performClick()
        rule.waitForIdle()
        tab("This week").performClick()
        rule.waitForIdle()
        segment("Today").assertIsSelected()
    }

    @Test
    fun `the raised AI button answers a tap on its top, above the bar`() {
        tab("Talk to your AI").performTouchInput { click(androidx.compose.ui.geometry.Offset(centerX, 4f)) }
        rule.waitForIdle()
        rule.onNode(hasContentDescription("Start talking")).assertIsDisplayed()
    }

    @Test
    fun `the AI button opens the assistant`() {
        tab("Talk to your AI").performClick()
        rule.waitForIdle()
        rule.onNode(hasContentDescription("Start talking")).assertIsDisplayed()
        shot("7-voice")
    }

    @Test
    fun `a pushed screen covers the tab bar, and its back arrow returns`() {
        rule.onNode(hasText("Reminders") and hasClickAction()).performClick()
        rule.waitForIdle()
        rule.onAllNodes(hasContentDescription("Talk to your AI")).assertCountEquals(0)
        shot("8-reminders")
        rule.onNode(hasContentDescription("Back")).performClick()
        rule.waitForIdle()
        tab("This week").assertIsSelected()
        segment("Today").assertIsSelected()
    }

    @Test
    fun `every tappable thing on every page can be heard and is big enough to hit`() {
        val pages = listOf(
            "This week" to listOf("Today", "Week", "Needs you", "AI"),
            "Attendance" to listOf("Overview", "Subjects", "Portal"),
            "Files" to listOf("Subjects", "Unsorted"),
            "Inbox" to listOf("Overview", "Placements", "Internships", "Exam notices", "Events & more"),
        )
        val problems = mutableListOf<String>()
        for ((name, segments) in pages) {
            tab(name).performClick()
            settle()
            for (page in segments) {
                // Five or more segments scroll sideways; fewer share the width and don't.
                if (segments.size > 4) segment(page).performScrollTo()
                segment(page).performClick()
                settle()
                problems += accessibility("$name > $page")
            }
        }
        assertTrue("found ${problems.size}:\n" + problems.joinToString("\n"), problems.isEmpty())
    }

    /** Lets what a page asks the (local) server for arrive and be drawn. */
    private fun settle() {
        rule.waitForIdle()
        Thread.sleep(250)
        rule.waitForIdle()
    }

    /** What TalkBack and a thumb need: each tappable node says something, and is 48 dp or more to touch. */
    private fun accessibility(screen: String): List<String> {
        val min = with(rule.density) { 48.dp.toPx() } - 0.5f
        fun dp(px: Float) = with(rule.density) { px.toDp().value.toInt() }
        val tappable = rule.onAllNodes(hasClickAction()).fetchSemanticsNodes()
        println("accessibility: $screen, ${tappable.count { it.boundsInRoot.width > 0f && it.boundsInRoot.height > 0f }} tappable on screen checked")
        return tappable.mapNotNull { node: SemanticsNode ->
            val c = node.config
            val label = buildList {
                c.getOrNull(SemanticsProperties.ContentDescription)?.let { addAll(it) }
                c.getOrNull(SemanticsProperties.Text)?.let { texts -> addAll(texts.map { it.text }) }
            }.joinToString(" ").trim()
            val touch = node.touchBoundsInRoot
            val shown = node.boundsInRoot
            // Scrolled out of sight (a page further down, a segment off the side): not on screen
            // to be heard or touched until it is scrolled to.
            if (shown.width <= 0f || shown.height <= 0f) return@mapNotNull null
            // Partly scrolled out (cut by the edge of a list or of the segment bar): its size is
            // its own, not what the scroll position happens to show of it.
            val cut = shown.width < node.size.width - 1 || shown.height < node.size.height - 1
            when {
                label.isEmpty() -> "$screen: something tappable says nothing (at ${node.boundsInRoot})"
                !cut && (touch.width < min || touch.height < min) ->
                    "$screen: \"${label.take(48)}\" is ${dp(touch.width)}x${dp(touch.height)} dp to touch"
                else -> null
            }
        }
    }
}
