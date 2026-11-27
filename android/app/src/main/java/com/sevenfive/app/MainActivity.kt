package com.sevenfive.app

import android.content.Intent
import android.os.Bundle
import android.graphics.Color
import androidx.activity.ComponentActivity
import androidx.activity.SystemBarStyle
import androidx.activity.compose.setContent
import androidx.activity.enableEdgeToEdge
import androidx.lifecycle.Lifecycle
import androidx.lifecycle.ViewModelProvider
import androidx.lifecycle.createSavedStateHandle
import androidx.lifecycle.lifecycleScope
import androidx.lifecycle.repeatOnLifecycle
import androidx.lifecycle.viewmodel.initializer
import androidx.lifecycle.viewmodel.viewModelFactory
import com.sevenfive.app.portal.AppVisibility
import com.sevenfive.app.portal.ForegroundSync
import androidx.compose.animation.AnimatedVisibility
import androidx.compose.animation.Crossfade
import androidx.compose.animation.EnterTransition
import androidx.compose.animation.core.tween
import androidx.compose.animation.fadeOut
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.snapshotFlow
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import com.sevenfive.app.ui.components.OpeningScreen
import kotlinx.coroutines.flow.first
import kotlinx.coroutines.withTimeoutOrNull
import androidx.compose.runtime.getValue
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import com.sevenfive.app.data.AccountState
import com.sevenfive.app.data.CardsRepository
import com.sevenfive.app.ui.AppViewModel
import com.sevenfive.app.ui.SevenFiveRoot
import com.sevenfive.app.ui.auth.AuthFlow
import com.sevenfive.app.ui.auth.AuthViewModel
import com.sevenfive.app.ui.auth.CheckingScreen
import com.sevenfive.app.ui.auth.OnboardingScreen
import com.sevenfive.app.ui.auth.StartingScreen
import com.sevenfive.app.ui.theme.SevenFiveTheme
import kotlinx.coroutines.coroutineScope
import kotlinx.coroutines.delay
import kotlinx.coroutines.flow.collectLatest
import kotlinx.coroutines.flow.distinctUntilChanged
import kotlinx.coroutines.flow.map
import kotlinx.coroutines.launch

class MainActivity : ComponentActivity() {
    private lateinit var sync: ForegroundSync
    private lateinit var viewModel: AppViewModel
    private lateinit var auth: AuthViewModel

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        // Light theme always: dark status and gesture-bar icons over the light backdrop.
        enableEdgeToEdge(
            statusBarStyle = SystemBarStyle.light(Color.TRANSPARENT, Color.TRANSPARENT),
            navigationBarStyle = SystemBarStyle.light(Color.TRANSPARENT, Color.TRANSPARENT),
        )
        val container = (application as SevenFiveApp).container
        sync = ForegroundSync(this, container.portal, container.portalStore, container.servers)

        val factory = viewModelFactory { initializer { AppViewModel(container) } }
        viewModel = ViewModelProvider(this, factory)[AppViewModel::class.java]
        // The sign-up and reset steps outlive Android closing the app in the background.
        val authFactory = viewModelFactory { initializer { AuthViewModel(container, createSavedStateHandle()) } }
        auth = ViewModelProvider(this, authFactory)[AuthViewModel::class.java]
        // A fresh start from Google's sign-in page (not a rotation, which replays the intent).
        if (savedInstanceState == null) handleLink(intent)

        // Poll the cards and keep the portal fresh only while the app is on screen, and only for
        // someone signed in (or trying the demo): signed out, nothing is asked for.
        lifecycleScope.launch {
            repeatOnLifecycle(Lifecycle.State.STARTED) {
                launch { container.finder.runWhileStarted() }
                container.accounts.state.map { it.usesApp }.distinctUntilChanged().collectLatest { using ->
                    if (using) {
                        coroutineScope {
                            // The cards first, on their own: a server that was asleep (a cold
                            // Lambda) wakes once for them, and the rest follow on the warm server
                            // instead of all arriving at once and each waking one of its own.
                            container.cards.refresh(wait = true)
                            launch { container.cards.pollForever(firstAfter = CardsRepository.POLL_MILLIS) }
                            launch { container.outbox.pollWhileStarted() }
                            launch {
                                delay(PORTAL_AFTER_MILLIS)
                                sync.runWhileStarted()
                            }
                        }
                    }
                }
            }
        }

        setContent {
            SevenFiveTheme {
                val account by container.accounts.state.collectAsStateWithLifecycle()
                // The opening screen: once per launch (not again on rotation). The app opens the
                // moment its sequence ends (3 s), or up to 2 s later if the account is still
                // being checked.
                var opened by rememberSaveable { mutableStateOf(false) }
                var sequenceDone by remember { mutableStateOf(false) }
                LaunchedEffect(Unit) {
                    if (opened) return@LaunchedEffect
                    snapshotFlow { sequenceDone }.first { it }
                    withTimeoutOrNull(OPENING_EXTRA_MILLIS) {
                        container.accounts.state.first { it !is AccountState.Starting }
                    }
                    opened = true
                }
                Box(Modifier.fillMaxSize()) {
                    Crossfade(targetState = gate(account), label = "account") { screen ->
                        when (screen) {
                            Gate.START -> StartingScreen()
                            Gate.CHECK -> CheckingScreen(auth, account as? AccountState.Checking ?: AccountState.Checking())
                            Gate.OUT -> AuthFlow(auth)
                            Gate.PROFILE -> OnboardingScreen(auth, (account as? AccountState.NeedsProfile)?.email)
                            Gate.APP -> SevenFiveRoot(viewModel, auth)
                        }
                    }
                    AnimatedVisibility(
                        visible = !opened,
                        enter = EnterTransition.None,
                        exit = fadeOut(tween(220)),
                    ) {
                        OpeningScreen(onFinished = { sequenceDone = true })
                    }
                }
            }
        }
    }

    private enum class Gate { START, CHECK, OUT, PROFILE, APP }

    private companion object {
        /** The portal refresh (its upload goes to the server) waits a moment after the outbox pull. */
        const val PORTAL_AFTER_MILLIS = 2_000L
        /** After the 3 s opening sequence, how much longer it may wait for the account check. */
        const val OPENING_EXTRA_MILLIS = 2_000L
    }

    private fun gate(state: AccountState): Gate = when (state) {
        AccountState.Starting -> Gate.START
        is AccountState.Checking -> Gate.CHECK
        is AccountState.SignedOut -> Gate.OUT
        is AccountState.NeedsProfile -> Gate.PROFILE
        AccountState.Demo, is AccountState.Ready -> Gate.APP
    }

    override fun onNewIntent(intent: Intent) {
        super.onNewIntent(intent)
        handleLink(intent)
    }

    /** sevenfive://google?code=…&state=… from the sign-in page: finish connecting Google. */
    private fun handleLink(intent: Intent?) {
        val link = intent?.data ?: return
        if (link.scheme != "sevenfive" || link.host != "google") return
        val code = link.getQueryParameter("code")
        val state = link.getQueryParameter("state")
        if (code != null && state != null) viewModel.finishGoogle(code, state)
    }

    override fun onStart() {
        super.onStart()
        AppVisibility.foreground = true
    }

    override fun onStop() {
        AppVisibility.foreground = false
        super.onStop()
    }

    override fun onDestroy() {
        sync.destroy()
        super.onDestroy()
    }
}
