package com.sevenfive.app

import android.Manifest
import android.os.Build
import android.os.Bundle
import androidx.activity.result.contract.ActivityResultContracts
import com.sevenfive.app.notify.Alerts
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
import com.sevenfive.app.portal.ForegroundSync
import com.sevenfive.app.ui.AppViewModel
import com.sevenfive.app.ui.SevenFiveRoot
import com.sevenfive.app.ui.theme.SevenFiveTheme
import kotlinx.coroutines.launch

class MainActivity : ComponentActivity() {
    private lateinit var sync: ForegroundSync

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
        val viewModel = ViewModelProvider(this, factory)[AppViewModel::class.java]

        // Poll the cards and keep the portal fresh only while the app is on screen.
        lifecycleScope.launch {
            repeatOnLifecycle(Lifecycle.State.STARTED) {
                launch { container.cards.pollForever() }
                launch { container.finder.runWhileStarted() }
                launch { sync.runWhileStarted() }
            }
        }

        askForNotificationsOnce()

        setContent {
            SevenFiveTheme {
                SevenFiveRoot(viewModel)
            }
        }
    }

    /** Android 13+: reminders and the digest need permission. Asked once, at first launch. */
    private fun askForNotificationsOnce() {
        if (Build.VERSION.SDK_INT < Build.VERSION_CODES.TIRAMISU || Alerts.canNotify(this)) return
        val prefs = getSharedPreferences("alerts", MODE_PRIVATE)
        if (prefs.getBoolean("asked", false)) return
        prefs.edit().putBoolean("asked", true).apply()
        registerForActivityResult(ActivityResultContracts.RequestPermission()) { }
            .launch(Manifest.permission.POST_NOTIFICATIONS)
    }

    override fun onDestroy() {
        sync.destroy()
        super.onDestroy()
    }
}
