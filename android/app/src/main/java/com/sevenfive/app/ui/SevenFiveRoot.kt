package com.sevenfive.app.ui

import androidx.compose.animation.AnimatedContentTransitionScope
import androidx.compose.animation.AnimatedVisibility
import androidx.compose.animation.EnterTransition
import androidx.compose.animation.ExitTransition
import androidx.compose.animation.core.Spring
import androidx.compose.animation.core.animateDpAsState
import androidx.compose.animation.core.animateFloatAsState
import androidx.compose.animation.core.FastOutSlowInEasing
import androidx.compose.animation.core.spring
import androidx.compose.animation.core.tween
import androidx.compose.animation.expandVertically
import androidx.compose.animation.fadeIn
import androidx.compose.animation.fadeOut
import androidx.compose.animation.shrinkVertically
import androidx.compose.animation.slideInHorizontally
import androidx.compose.animation.slideInVertically
import androidx.compose.animation.slideOutHorizontally
import androidx.compose.animation.slideOutVertically
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.BoxWithConstraints
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.WindowInsets
import androidx.compose.foundation.layout.defaultMinSize
import androidx.compose.foundation.layout.fillMaxHeight
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.navigationBarsPadding
import androidx.compose.foundation.layout.offset
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.filled.LibraryBooks
import androidx.compose.material.icons.automirrored.outlined.LibraryBooks
import androidx.compose.material.icons.filled.Alarm
import androidx.compose.material.icons.filled.Home
import androidx.compose.material.icons.filled.Inbox
import androidx.compose.material.icons.filled.PieChart
import androidx.compose.material.icons.outlined.Alarm
import androidx.compose.material.icons.outlined.Home
import androidx.compose.material.icons.outlined.Inbox
import androidx.compose.material.icons.outlined.PieChart
import androidx.compose.material3.Icon
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Snackbar
import androidx.compose.material3.SnackbarHost
import androidx.compose.material3.SnackbarHostState
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.CompositionLocalProvider
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.remember
import androidx.compose.runtime.staticCompositionLocalOf
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.graphicsLayer
import androidx.compose.ui.graphics.vector.ImageVector
import androidx.compose.ui.hapticfeedback.HapticFeedbackType
import androidx.compose.ui.platform.LocalHapticFeedback
import androidx.compose.ui.semantics.Role
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.selected
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.IntOffset
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import androidx.navigation.NavBackStackEntry
import androidx.navigation.NavGraph.Companion.findStartDestination
import androidx.navigation.NavHostController
import androidx.navigation.compose.NavHost
import androidx.navigation.compose.composable
import androidx.navigation.compose.currentBackStackEntryAsState
import androidx.navigation.compose.rememberNavController
import com.sevenfive.app.ui.screens.AiLogScreen
import com.sevenfive.app.ui.screens.AskScreen
import com.sevenfive.app.ui.screens.AttendanceScreen
import com.sevenfive.app.ui.screens.GradesScreen
import com.sevenfive.app.ui.screens.PlannerScreen
import com.sevenfive.app.ui.screens.SearchScreen
import com.sevenfive.app.ui.screens.TimetableScreen
import com.sevenfive.app.ui.screens.HomeScreen
import com.sevenfive.app.ui.screens.InboxScreen
import com.sevenfive.app.ui.screens.MaterialsScreen
import com.sevenfive.app.ui.screens.PortalCheckScreen
import com.sevenfive.app.ui.screens.PortalScreen
import com.sevenfive.app.ui.screens.RemindersScreen
import com.sevenfive.app.ui.screens.SettingsScreen
import com.sevenfive.app.ui.theme.LocalAppColors
import com.sevenfive.app.ui.theme.LocalBottomInset
import com.sevenfive.app.ui.theme.Motion
import com.sevenfive.app.ui.theme.frosted
import com.sevenfive.app.ui.theme.pressable
import dev.chrisbanes.haze.HazeState
import dev.chrisbanes.haze.hazeSource
import dev.chrisbanes.haze.rememberHazeState

object Routes {
    const val HOME = "home"
    const val ATTENDANCE = "attendance"
    const val MATERIALS = "materials"
    const val INBOX = "inbox"
    const val REMINDERS = "reminders"
    const val PORTAL = "portal"
    const val SETTINGS = "settings"
    const val PORTAL_CHECK = "portal-check"
    const val SEARCH = "search"
    const val ASK = "ask"
    const val AI_LOG = "ai-log"
    const val PLANNER = "planner"
    const val TIMETABLE = "timetable"
    const val GRADES = "grades"
}

/** Opens a pushed screen by route, from anywhere under the root (cards, tiles, bar buttons). */
val LocalNav = staticCompositionLocalOf<(String) -> Unit> { {} }

private data class Tab(val route: String, val label: String, val on: ImageVector, val off: ImageVector)

private val tabs = listOf(
    Tab(Routes.HOME, "This week", Icons.Filled.Home, Icons.Outlined.Home),
    Tab(Routes.ATTENDANCE, "Attendance", Icons.Filled.PieChart, Icons.Outlined.PieChart),
    Tab(Routes.MATERIALS, "Materials", Icons.AutoMirrored.Filled.LibraryBooks, Icons.AutoMirrored.Outlined.LibraryBooks),
    Tab(Routes.INBOX, "Inbox", Icons.Filled.Inbox, Icons.Outlined.Inbox),
    Tab(Routes.REMINDERS, "Reminders", Icons.Filled.Alarm, Icons.Outlined.Alarm),
)

/** Screens pushed on top of the tabs: they slide in from the right, like an iOS navigation stack. */
private val pushed = setOf(
    Routes.SETTINGS, Routes.PORTAL, Routes.PORTAL_CHECK, Routes.SEARCH, Routes.ASK, Routes.AI_LOG,
    Routes.PLANNER, Routes.TIMETABLE, Routes.GRADES,
)

@Composable
fun SevenFiveRoot(vm: AppViewModel) {
    val nav = rememberNavController()
    val snackbar = remember { SnackbarHostState() }
    val state by vm.cards.collectAsStateWithLifecycle()
    val backStack by nav.currentBackStackEntryAsState()
    val route = backStack?.destination?.route
    // Everything on screen is the source the floating glass blurs.
    val haze = rememberHazeState()

    LaunchedEffect(Unit) {
        vm.messages.collect { snackbar.showSnackbar(it) }
    }

    val showTabs = route == null || route !in pushed
    val tour by vm.tour.collectAsStateWithLifecycle()
    // Each demo step opens the tab it talks about.
    LaunchedEffect(tour?.index, tour != null) {
        tour?.let { nav.goToTab(DemoTour.steps[it.index].route) }
    }
    Scaffold(
        // Each screen draws its own bar under the status bar; content runs under the floating tabs.
        containerColor = MaterialTheme.colorScheme.background,
        contentWindowInsets = WindowInsets(0, 0, 0, 0),
        snackbarHost = {
            SnackbarHost(snackbar) { data ->
                Snackbar(
                    data,
                    shape = MaterialTheme.shapes.medium,
                    containerColor = MaterialTheme.colorScheme.inverseSurface.copy(alpha = 0.94f),
                    modifier = Modifier.padding(horizontal = 4.dp),
                )
            }
        },
        bottomBar = {
            AnimatedVisibility(
                visible = showTabs,
                enter = slideInVertically(spring(stiffness = Spring.StiffnessMediumLow)) { it } + fadeIn(),
                exit = slideOutVertically(spring(stiffness = Spring.StiffnessMedium)) { it } + fadeOut(),
            ) {
                Column(
                    Modifier.navigationBarsPadding().padding(start = 14.dp, end = 14.dp, bottom = 8.dp),
                    verticalArrangement = Arrangement.spacedBy(8.dp),
                ) {
                    AnimatedVisibility(
                        visible = tour != null,
                        enter = fadeIn() + expandVertically(spring(stiffness = Spring.StiffnessMediumLow)),
                        exit = fadeOut() + shrinkVertically(spring(stiffness = Spring.StiffnessMedium)),
                    ) {
                        tour?.let { t ->
                            DemoBar(
                                t,
                                haze = haze,
                                onBack = { vm.tourBack() },
                                onNext = { vm.tourNext() },
                                onAct = { vm.tourAct() },
                                onClose = { vm.endTour() },
                            )
                        }
                    }
                    GlassTabBar(
                        haze = haze,
                        selected = tabs.indexOfFirst { it.route == route }.coerceAtLeast(0),
                        badge = { tab ->
                            when (tab.route) {
                                Routes.HOME -> state.cards?.approvals?.size ?: 0
                                Routes.REMINDERS -> state.cards?.reminders?.size ?: 0
                                else -> 0
                            }
                        },
                        onSelect = { nav.goToTab(it.route) },
                    )
                }
            }
        },
    ) { inner ->
        CompositionLocalProvider(
            LocalBottomInset provides inner.calculateBottomPadding(),
            LocalNav provides { r: String -> nav.navigate(r) { launchSingleTop = true } },
        ) {
            Box(Modifier.fillMaxSize().hazeSource(haze)) {
                NavHost(
                    nav,
                    startDestination = Routes.HOME,
                    enterTransition = { enter() },
                    exitTransition = { exit() },
                    popEnterTransition = { popEnter() },
                    popExitTransition = { popExit() },
                ) {
                    val settings = { nav.navigate(Routes.SETTINGS) }
                    composable(Routes.HOME) { HomeScreen(vm, settings) }
                    composable(Routes.ATTENDANCE) { AttendanceScreen(vm, settings, onPortal = { nav.navigate(Routes.PORTAL) }) }
                    composable(Routes.MATERIALS) { MaterialsScreen(vm, settings) }
                    composable(Routes.INBOX) { InboxScreen(vm, settings) }
                    composable(Routes.REMINDERS) { RemindersScreen(vm, settings) }
                    composable(Routes.PORTAL) { PortalScreen(vm, onDone = { nav.popBackStack() }) }
                    composable(Routes.SETTINGS) {
                        SettingsScreen(vm, onBack = { nav.popBackStack() }, onPortalCheck = { nav.navigate(Routes.PORTAL_CHECK) })
                    }
                    composable(Routes.PORTAL_CHECK) {
                        PortalCheckScreen(vm, vm.portalCheckUrl.value, onBack = { nav.popBackStack() })
                    }
                    val back = { nav.popBackStack(); Unit }
                    composable(Routes.SEARCH) { SearchScreen(vm, back) }
                    composable(Routes.ASK) { AskScreen(vm, back) }
                    composable(Routes.AI_LOG) { AiLogScreen(vm, back) }
                    composable(Routes.PLANNER) { PlannerScreen(vm, back) }
                    composable(Routes.TIMETABLE) { TimetableScreen(vm, back) }
                    composable(Routes.GRADES) { GradesScreen(vm, back) }
                }
            }
        }
    }
}

// Navigation motion. A pushed screen slides in over the one below, which drifts a quarter of the
// way left and dims, and the reverse on back (also driven by the predictive back gesture).
// Switching tabs is a quick cross-fade with a hint of depth, as tabs aren't a stack.

private typealias Nav = AnimatedContentTransitionScope<NavBackStackEntry>

private val NavBackStackEntry.isPushed get() = destination.route in pushed

private val tabFadeIn = tween<Float>(durationMillis = 180, easing = FastOutSlowInEasing)
private val tabFadeOut = tween<Float>(durationMillis = 120, easing = FastOutSlowInEasing)

private fun Nav.enter(): EnterTransition =
    if (targetState.isPushed) slideInHorizontally(Motion.screen) { it }
    else fadeIn(tabFadeIn)

private fun Nav.exit(): ExitTransition =
    if (targetState.isPushed) slideOutHorizontally(Motion.screen) { -it / 4 } + fadeOut(Motion.fade, targetAlpha = 0.7f)
    else fadeOut(tabFadeOut)

private fun Nav.popEnter(): EnterTransition =
    if (initialState.isPushed) slideInHorizontally(Motion.screen) { -it / 4 } + fadeIn(Motion.fade, initialAlpha = 0.7f)
    else fadeIn(tabFadeIn)

private fun Nav.popExit(): ExitTransition =
    if (initialState.isPushed) slideOutHorizontally(Motion.screen) { it }
    else fadeOut(tabFadeOut)

/**
 * The tab bar, iOS style: a frosted capsule floating over the content, with a soft selection
 * pill that glides between tabs on a spring.
 */
@Composable
private fun GlassTabBar(haze: HazeState, selected: Int, badge: (Tab) -> Int, onSelect: (Tab) -> Unit) {
    val haptics = LocalHapticFeedback.current
    val app = LocalAppColors.current
    val primary = MaterialTheme.colorScheme.primary
    BoxWithConstraints(
        Modifier
            .fillMaxWidth()
            .height(64.dp)
            .frosted(haze, CircleShape),
    ) {
        val itemWidth = maxWidth / tabs.size
        val pillX by animateDpAsState(itemWidth * selected, Motion.glide, label = "tab pill")
        Box(
            Modifier
                .offset { IntOffset(pillX.roundToPx(), 0) }
                .width(itemWidth)
                .fillMaxHeight()
                .padding(5.dp)
                .background(primary.copy(alpha = if (app.dark) 0.20f else 0.13f), CircleShape),
        )
        Row(Modifier.fillMaxSize()) {
            tabs.forEachIndexed { index, tab ->
                val on = index == selected
                val tint = if (on) primary else app.secondaryLabel
                val lift by animateFloatAsState(if (on) 1f else 0f, Motion.fade, label = "tab lift")
                Column(
                    Modifier
                        .width(itemWidth)
                        .fillMaxHeight()
                        .semantics {
                            this.selected = on
                            contentDescription = tab.label
                        }
                        .pressable(scaleTo = 0.9f, role = Role.Tab) {
                            if (!on) haptics.performHapticFeedback(HapticFeedbackType.TextHandleMove)
                            onSelect(tab)
                        },
                    horizontalAlignment = Alignment.CenterHorizontally,
                    verticalArrangement = Arrangement.Center,
                ) {
                    Box {
                        Icon(
                            if (on) tab.on else tab.off,
                            contentDescription = null,
                            tint = tint,
                            modifier = Modifier
                                .size(24.dp)
                                .graphicsLayer {
                                    val s = 1f + 0.06f * lift
                                    scaleX = s
                                    scaleY = s
                                },
                        )
                        val count = badge(tab)
                        if (count > 0) {
                            Box(
                                Modifier
                                    .align(Alignment.TopEnd)
                                    .offset(x = 9.dp, y = (-5).dp)
                                    .defaultMinSize(minWidth = 17.dp, minHeight = 17.dp)
                                    .background(MaterialTheme.colorScheme.error, CircleShape)
                                    .padding(horizontal = 4.dp),
                                contentAlignment = Alignment.Center,
                            ) {
                                Text(
                                    if (count > 9) "9+" else "$count",
                                    color = Color.White,
                                    fontSize = 10.sp,
                                    fontWeight = FontWeight.Bold,
                                    lineHeight = 12.sp,
                                )
                            }
                        }
                    }
                    Text(
                        tab.label,
                        color = tint,
                        fontSize = 10.sp,
                        lineHeight = 12.sp,
                        fontWeight = if (on) FontWeight.SemiBold else FontWeight.Medium,
                        maxLines = 1,
                        modifier = Modifier.padding(top = 3.dp),
                    )
                }
            }
        }
    }
}

private fun NavHostController.goToTab(route: String) = navigate(route) {
    popUpTo(graph.findStartDestination().id) { saveState = true }
    launchSingleTop = true
    restoreState = true
}
