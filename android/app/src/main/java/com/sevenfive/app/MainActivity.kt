package com.sevenfive.app

import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.activity.enableEdgeToEdge
import androidx.lifecycle.Lifecycle
import androidx.lifecycle.ViewModelProvider
import androidx.lifecycle.lifecycleScope
import androidx.lifecycle.repeatOnLifecycle
import androidx.lifecycle.viewmodel.initializer
import androidx.lifecycle.viewmodel.viewModelFactory
import com.sevenfive.app.portal.ForegroundSync
import com.sevenfive.app.ui.AppViewModel
import com.sevenfive.app.ui.SevenFiveRoot
import com.sevenfive.app.ui.theme.SevenFiveTheme
import kotlinx.coroutines.launch

class MainActivity : ComponentActivity() {
    private lateinit var sync: ForegroundSync

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        enableEdgeToEdge()
        val container = (application as SevenFiveApp).container
        sync = ForegroundSync(this, container.portal, container.portalStore, container.servers)

        val factory = viewModelFactory { initializer { AppViewModel(container) } }
        val viewModel = ViewModelProvider(this, factory)[AppViewModel::class.java]

        // Poll the cards and keep the portal fresh only while the app is on screen.
        lifecycleScope.launch {
            repeatOnLifecycle(Lifecycle.State.STARTED) {
                launch { container.cards.pollForever() }
                launch { sync.runWhileStarted() }
            }
        }

        setContent {
            SevenFiveTheme {
                SevenFiveRoot(viewModel)
            }
        }
    }

    override fun onDestroy() {
        sync.destroy()
        super.onDestroy()
    }
}
