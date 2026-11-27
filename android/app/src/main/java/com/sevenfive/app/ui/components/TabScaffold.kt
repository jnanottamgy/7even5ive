package com.sevenfive.app.ui.components

import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.WindowInsets
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.outlined.Mic
import androidx.compose.material.icons.outlined.Search
import androidx.compose.material.icons.outlined.Settings
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.Icon
import androidx.compose.material3.TopAppBar
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Text
import androidx.compose.material3.TopAppBarDefaults
import androidx.compose.material3.pulltorefresh.PullToRefreshBox
import androidx.compose.material3.pulltorefresh.PullToRefreshDefaults
import androidx.compose.material3.pulltorefresh.rememberPullToRefreshState
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.drawBehind
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.graphicsLayer
import androidx.compose.ui.input.nestedscroll.nestedScroll
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import com.sevenfive.app.ui.AppViewModel
import com.sevenfive.app.ui.LocalOpenVoice
import com.sevenfive.app.ui.LocalNav
import com.sevenfive.app.ui.Routes
import com.sevenfive.app.ui.theme.AuroraBackground
import com.sevenfive.app.ui.theme.LocalAppColors
import com.sevenfive.app.ui.theme.LocalBottomInset
import com.sevenfive.app.ui.theme.glassSurface
import com.sevenfive.app.ui.theme.pressable
import kotlinx.coroutines.delay
import kotlinx.coroutines.launch

/**
 * The frame every tab shares, the iOS way: a large bold title that collapses into a frosted bar
 * as you scroll. The bar is clear at the top of the page and turns to frosted glass once content
 * slides under it; the list scrolls under both the bar and the floating tab bar.
 *
 * [content] gets the padding that keeps its first and last items clear of the bars: pass it as
 * the list's contentPadding, not as a modifier, so the content can scroll underneath.
 */
@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun TabScaffold(
    title: String,
    vm: AppViewModel,
    onSettings: () -> Unit,
    content: @Composable (PaddingValues) -> Unit,
) {
    val state by vm.cards.collectAsStateWithLifecycle()
    val searching by vm.searching.collectAsStateWithLifecycle()
    val scroll = TopAppBarDefaults.pinnedScrollBehavior()
    val bottomInset = LocalBottomInset.current
    val app = LocalAppColors.current

    Scaffold(
        modifier = Modifier.nestedScroll(scroll.nestedScrollConnection),
        containerColor = Color.Transparent,
        contentWindowInsets = WindowInsets(0, 0, 0, 0),
        topBar = {
            // Solid once content slides under it; clear at the top. No blur: nothing to re-process.
            val barColor = MaterialTheme.colorScheme.background
            Column(Modifier.drawBehind { drawRect(barColor.copy(alpha = scroll.state.overlappedFraction)) }) {
                TopAppBar(
                    title = { Text(title, style = MaterialTheme.typography.headlineSmall, maxLines = 1, overflow = TextOverflow.Ellipsis) },
                    actions = {
                        // The AI's button lives in the tab bar now (the orange one in the middle).
                        val nav = LocalNav.current
                        Box(
                            Modifier
                                .padding(end = 8.dp)
                                .size(38.dp)
                                .pressable { nav(Routes.SEARCH) }
                                .glassSurface(shape = CircleShape, strong = true),
                            contentAlignment = Alignment.Center,
                        ) {
                            Icon(
                                Icons.Outlined.Search,
                                contentDescription = "Search",
                                tint = MaterialTheme.colorScheme.onSurface,
                                modifier = Modifier.size(20.dp),
                            )
                        }
                        Box(
                            Modifier
                                .padding(end = 8.dp)
                                .size(38.dp)
                                .pressable(onClick = onSettings)
                                .glassSurface(shape = CircleShape, strong = true),
                            contentAlignment = Alignment.Center,
                        ) {
                            Icon(
                                Icons.Outlined.Settings,
                                contentDescription = "Settings",
                                tint = MaterialTheme.colorScheme.onSurface,
                                modifier = Modifier.size(20.dp),
                            )
                        }
                    },
                    scrollBehavior = scroll,
                    colors = TopAppBarDefaults.topAppBarColors(
                        containerColor = Color.Transparent,
                        scrolledContainerColor = Color.Transparent,
                    ),
                )
                OfflineBanner(state.error, state.updatedAt, onSettings, searching)
                // The hairline under the bar appears only once content is underneath.
                Box(
                    Modifier
                        .fillMaxWidth()
                        .height(0.6.dp)
                        .graphicsLayer { alpha = scroll.state.overlappedFraction }
                        .background(app.hairline),
                )
            }
        },
    ) { inner ->
        Box(Modifier.fillMaxSize()) {
            AuroraBackground()
            // No pull-to-refresh: the cards refresh on their own, and a first load shows a
            // skeleton of the screen instead of a spinner.
            Box(Modifier.fillMaxSize()) {
                content(
                    PaddingValues(
                        start = 16.dp,
                        end = 16.dp,
                        top = inner.calculateTopPadding() + 4.dp,
                        bottom = bottomInset + 28.dp,
                    ),
                )
            }
        }
    }
}

/** The line under a large title: what this screen is, in a sentence. Scrolls with the content. */
@Composable
fun ScreenIntro(text: String?) {
    if (text.isNullOrBlank()) return
    Text(
        text,
        style = MaterialTheme.typography.bodyLarge,
        color = LocalAppColors.current.secondaryLabel,
        modifier = Modifier.padding(bottom = 6.dp),
    )
}

private const val MIN_SPINNER_MILLIS = 800L
