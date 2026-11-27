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
import androidx.compose.material3.SnackbarDuration
import androidx.compose.material3.SnackbarHostState
import androidx.compose.material3.SnackbarResult
import androidx.compose.material3.Text
import android.Manifest
import android.os.Build
import androidx.activity.compose.LocalActivity
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.runtime.Composable
import androidx.compose.runtime.CompositionLocalProvider
import androidx.compose.runtime.staticCompositionLocalOf
import androidx.compose.ui.platform.LocalUriHandler
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
import com.sevenfive.app.data.AccountState
import com.sevenfive.app.ui.auth.AuthStep
import com.sevenfive.app.ui.auth.AuthViewModel
import com.sevenfive.app.ui.auth.ProfileEditScreen
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
import com.sevenfive.app.ui.screens.FilesScreen
import com.sevenfive.app.ui.screens.PortalScreen
import com.sevenfive.app.ui.screens.RemindersScreen
import com.sevenfive.app.ui.screens.SettingsScreen
import com.sevenfive.app.ui.screens.VoiceScreen
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
    const val VOICE = "voice"
    const val PROFILE = "profile"
    const val SEARCH = "search"
    const val ASK = "ask"
    const val AI_LOG = "ai-log"
    const val PLANNER = "planner"
    const val TIMETABLE = "timetable"
    const val GRADES = "grades"
}

/** Opens the voice assistant from any tab's header (null where there is none). */
val LocalOpenVoice = staticCompositionLocalOf<(() -> Unit)?> { null }

/** Opens a pushed screen by route, from anywhere under the root (cards, tiles, bar buttons). */
val LocalNav = staticCompositionLocalOf<(String) -> Unit> { {} }

private data class Tab(val route: String, val label: String, val on: ImageVector, val off: ImageVector)

private val tabs = listOf(
    Tab(Routes.HOME, "This week", Icons.Filled.Home, Icons.Outlined.Home),
    Tab(Routes.ATTENDANCE, "Attendance", Icons.Filled.PieChart, Icons.Outlined.PieChart),
    Tab(Routes.MATERIALS, "Files", Icons.AutoMirrored.Filled.LibraryBooks, Icons.AutoMirrored.Outlined.LibraryBooks),
    Tab(Routes.INBOX, "Inbox", Icons.Filled.Inbox, Icons.Outlined.Inbox),
    Tab(Routes.REMINDERS, "Reminders", Icons.Filled.Alarm, Icons.Outlined.Alarm),
)

/** Screens pushed on top of the tabs: they slide in from the right, like an iOS navigation stack. */
private val pushed = setOf(
    Routes.SETTINGS, Routes.PORTAL, Routes.PORTAL_CHECK, Routes.VOICE, Routes.PROFILE, Routes.SEARCH, Routes.ASK,
    Routes.AI_LOG, Routes.PLANNER, Routes.TIMETABLE, Routes.GRADES,
)

@Composable
fun SevenFiveRoot(vm: AppViewModel, auth: AuthViewModel) {
    val nav = rememberNavController()
    val snackbar = remember { SnackbarHostState() }
    val state by vm.cards.collectAsStateWithLifecycle()
    val backStack by nav.currentBackStackEntryAsState()
    val route = backStack?.destination?.route
    // Everything on screen is the source the floating glass blurs.
    val haze = rememberHazeState()

    LaunchedEffect(Unit) {
        vm.messages.collect { m ->
            val result = snackbar.showSnackbar(
                m.text,
                actionLabel = m.action,
                duration = if (m.action != null) SnackbarDuration.Long else SnackbarDuration.Short,
            )
            if (result == SnackbarResult.ActionPerformed) m.onAction?.invoke()
        }
    }
    // Google's sign-in page opens in the phone's browser; the server finishes it there.
    val uri = LocalUriHandler.current
    LaunchedEffect(Unit) {
        vm.openUrl.collect { url -> runCatching { uri.openUri(url) }.onFailure { vm.say("No browser to open the sign-in page") } }
    }
    // Android 13+: asked once it makes sense (a reminder pending, the urgent call turned on, or
    // from the "Notifications are off" rows). Once Android would no longer show its prompt (the
    // student declined twice), those rows open the system settings instead.
    val askPermission = rememberLauncherForActivityResult(ActivityResultContracts.RequestPermission()) { granted ->
        if (!granted) vm.say("Reminders will stay in the app: notifications are off")
    }
    val activity = LocalActivity.current
    LaunchedEffect(Unit) {
        vm.askNotifications.collect {
            val shows = activity == null || com.sevenfive.app.notify.Notifications.promptStillShows(activity)
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.TIRAMISU && shows) {
                com.sevenfive.app.notify.Notifications.markAsked(vm.container.appContext)
                askPermission.launch(Manifest.permission.POST_NOTIFICATIONS)
            }
        }
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
            LocalOpenVoice provides { nav.navigate(Routes.VOICE) { launchSingleTop = true } },
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
                    composable(Routes.MATERIALS) { FilesScreen(vm, settings) }
                    composable(Routes.INBOX) { InboxScreen(vm, settings) }
                    composable(Routes.REMINDERS) { RemindersScreen(vm, settings) }
                    composable(Routes.PORTAL) { PortalScreen(vm, onDone = { nav.popBackStack() }) }
                    composable(Routes.SETTINGS) {
                        SettingsScreen(
                            vm,
                            onBack = { nav.popBackStack() },
                            onPortalCheck = { nav.navigate(Routes.PORTAL_CHECK) },
                            onEditProfile = { nav.navigate(Routes.PROFILE) },
                            // From the demo to signing up: the login flow opens on Sign up.
                            onCreateAccount = {
                                auth.go(AuthStep.SignUp)
                                vm.logOut()
                            },
                        )
                    }
                    composable(Routes.PROFILE) {
                        val account by vm.account.collectAsStateWithLifecycle()
                        val profile = (account as? AccountState.Ready)?.me?.profile
                        ProfileEditScreen(auth, profile, onBack = { nav.popBackStack() })
                    }
                    composable(Routes.PORTAL_CHECK) {
                        PortalCheckScreen(vm, vm.portalCheckUrl.value, onBack = { nav.popBackStack() })
                    }
                    composable(Routes.VOICE) { VoiceScreen(vm, onBack = { nav.popBackStack() }) }
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
        // Neo-minimal: an icon and a word per tab; the current one in ink with an orange dot.
        val itemWidth = maxWidth / tabs.size
        Row(Modifier.fillMaxSize()) {
            tabs.forEachIndexed { index, tab ->
                val on = index == selected
                val tint = if (on) MaterialTheme.colorScheme.onSurface else app.secondaryLabel
                val lift by animateFloatAsState(if (on) 1f else 0f, Motion.fade, label = "tab dot")
                Column(
                    Modifier
                        .width(itemWidth)
                        .fillMaxHeight()
                        .semantics {
                            this.selected = on
                            contentDescription = tab.label
                        }
                        .pressable(scaleTo = 0.94f, role = Role.Tab) {
                            if (!on) haptics.performHapticFeedback(HapticFeedbackType.TextHandleMove)
                            onSelect(tab)
                        },
                    horizontalAlignment = Alignment.CenterHorizontally,
                    verticalArrangement = Arrangement.Center,
                ) {
                    // An icon over a word: filled and ink when current, outlined and grey when not.
                    Box {
                        Icon(
                            if (on) tab.on else tab.off,
                            contentDescription = null,
                            tint = tint,
                            modifier = Modifier.size(22.dp),
                        )
                        val count = badge(tab)
                        if (count > 0) {
                            Text(
                                if (count > 9) "9+" else "$count",
                                color = com.sevenfive.app.ui.theme.NeoInk,
                                fontSize = 9.sp,
                                lineHeight = 10.sp,
                                fontWeight = FontWeight.SemiBold,
                                modifier = Modifier
                                    .align(Alignment.TopEnd)
                                    .offset(x = 9.dp, y = (-4).dp)
                                    .defaultMinSize(minWidth = 15.dp)
                                    .background(com.sevenfive.app.ui.theme.Orange, CircleShape)
                                    .padding(horizontal = 3.dp, vertical = 1.dp),
                            )
                        }
                    }
                    Text(
                        tab.label,
                        color = tint,
                        fontSize = 11.5.sp,
                        lineHeight = 14.sp,
                        fontFamily = com.sevenfive.app.ui.theme.Neo,
                        fontWeight = if (on) FontWeight.SemiBold else FontWeight.Medium,
                        maxLines = 1,
                        modifier = Modifier.padding(top = 4.dp),
                    )
                    // The one orange touch: a small dot under the current tab.
                    Box(
                        Modifier
                            .padding(top = 4.dp)
                            .size(4.dp)
                            .graphicsLayer { alpha = lift; scaleX = lift; scaleY = lift }
                            .background(com.sevenfive.app.ui.theme.Orange, CircleShape),
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
