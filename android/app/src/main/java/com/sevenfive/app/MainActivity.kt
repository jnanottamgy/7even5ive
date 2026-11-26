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
import androidx.lifecycle.lifecycleScope
import androidx.lifecycle.repeatOnLifecycle
import androidx.lifecycle.viewmodel.initializer
import androidx.lifecycle.viewmodel.viewModelFactory
import com.sevenfive.app.portal.AppVisibility
import com.sevenfive.app.portal.ForegroundSync
import com.sevenfive.app.ui.AppViewModel
import com.sevenfive.app.ui.SevenFiveRoot
import com.sevenfive.app.ui.theme.SevenFiveTheme
import kotlinx.coroutines.launch

class MainActivity : ComponentActivity() {
    private lateinit var sync: ForegroundSync
    private lateinit var viewModel: AppViewModel

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
        // A fresh start from Google's sign-in page (not a rotation, which replays the intent).
        if (savedInstanceState == null) handleLink(intent)

        // Poll the cards and keep the portal fresh only while the app is on screen.
        lifecycleScope.launch {
            repeatOnLifecycle(Lifecycle.State.STARTED) {
                launch { container.cards.pollForever() }
                launch { container.finder.runWhileStarted() }
                launch { sync.runWhileStarted() }
                launch { container.outbox.pollWhileStarted() }
            }
        }

        setContent {
            SevenFiveTheme {
                SevenFiveRoot(viewModel)
            }
        }
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
