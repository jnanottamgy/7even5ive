package com.sevenfive.app.ui

import android.app.Application
import android.provider.Settings
import androidx.compose.ui.semantics.Role
import androidx.compose.ui.semantics.SemanticsProperties
import androidx.compose.ui.test.SemanticsMatcher
import androidx.compose.ui.test.hasClickAction
import androidx.compose.ui.test.hasContentDescription
import androidx.compose.ui.test.hasText
import androidx.compose.ui.test.junit4.ComposeContentTestRule
import androidx.compose.ui.test.onAllNodesWithText
import androidx.lifecycle.SavedStateHandle
import androidx.test.core.app.ApplicationProvider
import com.sevenfive.app.AppContainer
import com.sevenfive.app.data.ServerConfig
import com.sevenfive.app.ui.auth.AuthViewModel
import com.sevenfive.app.ui.theme.SevenFiveTheme
import kotlinx.coroutines.runBlocking
import java.util.Locale
import java.util.TimeZone

/**
 * The real app (its own container, view models and navigation) signed in as the demo, talking to
 * [server], shown in this rule on a phone-sized screen in India's time zone.
 */
internal fun ComposeContentTestRule.startDemoApp(server: RecordedServer): AppContainer {
    TimeZone.setDefault(TimeZone.getTimeZone("Asia/Kolkata"))
    Locale.setDefault(Locale.ENGLISH)
    val context = ApplicationProvider.getApplicationContext<Application>()
    // As with "Remove animations" on: the moving background stands still, so the screen can
    // settle between steps.
    Settings.Global.putFloat(context.contentResolver, Settings.Global.ANIMATOR_DURATION_SCALE, 0f)
    val container = AppContainer(context)
    // Before anything is asked of it: the build's own server is the live one.
    container.servers.save(ServerConfig(server.url, server.url, server.url))
    container.accounts.onArrive = {}
    container.accounts.start()
    runBlocking {
        container.accounts.useDemo()
        container.cards.refresh(wait = true)
    }
    val vm = AppViewModel(container)
    val auth = AuthViewModel(container, SavedStateHandle())
    // As MainActivity draws it: the one backdrop, then the app over it.
    setContent {
        SevenFiveTheme {
            androidx.compose.foundation.layout.Box(androidx.compose.ui.Modifier) {
                com.sevenfive.app.ui.theme.AuroraBackground()
                SevenFiveRoot(vm, auth)
            }
        }
    }
    waitForIdle()
    return container
}

/** The server as the demo sees it: the busier cards (a reminder, an approval waiting). */
internal fun demoServer() = RecordedServer(overrides = mapOf(
    "GET /api/cards" to "cards_busy",
    "POST /api/google/start" to "error_demo_google",
))

internal fun ComposeContentTestRule.tab(label: String) = onNode(hasContentDescription(label) and hasClickAction())

internal fun ComposeContentTestRule.segment(label: String) =
    onNode(hasText(label, substring = true) and SemanticsMatcher.expectValue(SemanticsProperties.Role, Role.Tab))

internal fun ComposeContentTestRule.waitFor(text: String, millis: Long = 10_000) = waitUntil(millis) {
    onAllNodesWithText(text, substring = true).fetchSemanticsNodes().isNotEmpty()
}

/** Whether [text] is on screen: the whole of some text, unless [part] (then within one). */
internal fun ComposeContentTestRule.shown(text: String, part: Boolean = false) =
    onAllNodesWithText(text, substring = part).fetchSemanticsNodes().isNotEmpty()

/** Waits for [condition] on the server's side, letting the app's main thread run in between:
 * under Robolectric it only runs when a test lets it, and what follows each answer runs there. */
internal fun ComposeContentTestRule.waitForServer(millis: Long = 10_000, condition: () -> Boolean) =
    waitUntil(millis) {
        waitForIdle()
        condition()
    }
