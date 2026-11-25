package com.sevenfive.app.ui.components

import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.padding
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.outlined.Settings
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.LargeTopAppBar
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Text
import androidx.compose.material3.TopAppBarDefaults
import androidx.compose.material3.pulltorefresh.PullToRefreshBox
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.input.nestedscroll.nestedScroll
import androidx.compose.ui.unit.dp
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import com.sevenfive.app.ui.AppViewModel
import kotlinx.coroutines.delay
import kotlinx.coroutines.launch

/** The frame every tab shares: a collapsing title, the offline banner, pull to refresh. */
@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun TabScaffold(
    title: String,
    vm: AppViewModel,
    onSettings: () -> Unit,
    subtitle: String? = null,
    content: @Composable () -> Unit,
) {
    val state by vm.cards.collectAsStateWithLifecycle()
    val searching by vm.searching.collectAsStateWithLifecycle()
    val scroll = TopAppBarDefaults.exitUntilCollapsedScrollBehavior()
    val scope = rememberCoroutineScope()
    var pulling by remember { mutableStateOf(false) }

    Scaffold(
        modifier = Modifier.nestedScroll(scroll.nestedScrollConnection),
        topBar = {
            LargeTopAppBar(
                title = { Text(title, maxLines = 1) },
                actions = {
                    IconButton(onClick = onSettings) {
                        Icon(Icons.Outlined.Settings, contentDescription = "Server settings")
                    }
                },
                scrollBehavior = scroll,
                colors = TopAppBarDefaults.topAppBarColors(
                    containerColor = MaterialTheme.colorScheme.background,
                    scrolledContainerColor = MaterialTheme.colorScheme.surfaceContainer,
                ),
            )
        },
    ) { inner ->
        Column(Modifier.padding(inner).fillMaxSize()) {
            OfflineBanner(state.error, state.updatedAt, onSettings, searching)
            if (subtitle != null) {
                Text(
                    subtitle,
                    style = MaterialTheme.typography.bodyMedium,
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                    modifier = Modifier.padding(horizontal = 16.dp),
                )
            }
            PullToRefreshBox(
                isRefreshing = pulling,
                onRefresh = {
                    pulling = true
                    scope.launch {
                        val started = System.currentTimeMillis()
                        vm.container.cards.refresh(wait = true)
                        // A laptop on the same Wi-Fi answers in ~50 ms: without a floor the
                        // spinner pops up and snaps away before it can be seen turning.
                        val shown = System.currentTimeMillis() - started
                        if (shown < MIN_SPINNER_MILLIS) delay(MIN_SPINNER_MILLIS - shown)
                        pulling = false
                    }
                },
                modifier = Modifier.fillMaxSize(),
            ) {
                Box(Modifier.fillMaxSize()) { content() }
            }
        }
    }
}

private const val MIN_SPINNER_MILLIS = 800L
