package com.sevenfive.app.ui

import androidx.compose.animation.AnimatedContentTransitionScope
import androidx.compose.animation.AnimatedVisibility
import androidx.compose.animation.EnterTransition
import androidx.compose.animation.ExitTransition
import androidx.compose.animation.core.Spring
import androidx.compose.animation.core.animateDpAsState
import androidx.compose.animation.core.animateFloatAsState
import androidx.compose.animation.core.FastOutSlowInEasing
import androidx.compose.animation.core.LinearOutSlowInEasing
import androidx.compose.animation.core.FastOutLinearInEasing
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
import androidx.compose.material.icons.filled.Mic
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
import androidx.compose.runtime.setValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.CompositionLocalProvider
import androidx.compose.runtime.staticCompositionLocalOf
import androidx.compose.ui.platform.LocalUriHandler
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.remember
import androidx.compose.runtime.staticCompositionLocalOf
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.shadow
import androidx.compose.foundation.layout.Spacer
import androidx.compose.ui.draw.drawBehind
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
import kotlinx.coroutines.launch

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
)

/** Screens pushed on top of the tabs: they slide in from the right, like an iOS navigation stack. */
private val pushed = setOf(
    Routes.SETTINGS, Routes.PORTAL, Routes.PORTAL_CHECK, Routes.VOICE, Routes.PROFILE, Routes.SEARCH, Routes.ASK,
    Routes.AI_LOG, Routes.PLANNER, Routes.TIMETABLE, Routes.GRADES, Routes.REMINDERS,
)

@Composable
fun SevenFiveRoot(vm: AppViewModel, auth: AuthViewModel) {
    val nav = rememberNavController()
    val snackbar = remember { SnackbarHostState() }
    val state by vm.cards.collectAsStateWithLifecycle()
    val backStack by nav.currentBackStackEntryAsState()
    val route = backStack?.destination?.route
    // Everything on screen is the source the floating glass blurs.

    LaunchedEffect(Unit) {
        // The newest message replaces the one showing: what was just tapped is what's said now,
        // never ten seconds later behind an older one.
        vm.messages.collect { m ->
            snackbar.currentSnackbarData?.dismiss()
            launch {
                val result = snackbar.showSnackbar(
                    m.text,
                    actionLabel = m.action,
                    duration = if (m.action != null) SnackbarDuration.Long else SnackbarDuration.Short,
                )
                if (result == SnackbarResult.ActionPerformed) m.onAction?.invoke()
            }
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

    // Screens with their own back arrow have no tab bar; every tab screen has it.
    val showTabs = route == null || route !in pushed
    // On a screen opened from a tab (Grades from Attendance), that tab stays lit.
    var lastTab by rememberSaveable { mutableStateOf(Routes.HOME) }
    LaunchedEffect(route) { if (route != null && tabs.any { it.route == route }) lastTab = route }
    val tour by vm.tour.collectAsStateWithLifecycle()
    // Each demo step opens the tab it talks about.
    LaunchedEffect(tour?.index, tour != null) {
        tour?.let { nav.goToTab(DemoTour.steps[it.index].route) }
    }
    Scaffold(
        // Each screen draws its own bar under the status bar; content runs under the floating tabs.
        // See-through: the app's one backdrop is drawn once, behind everything (MainActivity).
        containerColor = androidx.compose.ui.graphics.Color.Transparent,
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
                // Part of the tab screens' motion: gone with the one leaving, back with the one arriving.
                enter = barIn,
                exit = barOut,
            ) {
                Column(
                    Modifier
                        .fillMaxWidth()
                        .background(MaterialTheme.colorScheme.background)
                        .navigationBarsPadding(),
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
                                onBack = { vm.tourBack() },
                                onNext = { vm.tourNext() },
                                onAct = { vm.tourAct() },
                                onClose = { vm.endTour() },
                                modifier = Modifier.padding(start = 14.dp, end = 14.dp, top = 8.dp),
                            )
                        }
                    }
                    GlassTabBar(
                        selected = tabs.indexOfFirst { it.route == (if (tabs.any { t -> t.route == route }) route else lastTab) }.coerceAtLeast(0),
                        badge = { tab ->
                            when (tab.route) {
                                Routes.HOME -> state.cards?.approvals?.size ?: 0
                                else -> 0
                            }
                        },
                        onAi = { nav.navigate(Routes.VOICE) { launchSingleTop = true } },
                        onSelect = { tab ->
                            if (tab.route == Routes.HOME) {
                                // Already on Home: no navigation at all (that replayed the
                                // screen's entry animation), just back to Today, at the top.
                                if (route != Routes.HOME) nav.goHome()
                                vm.homeTapped()
                            } else if (tab.route != route) {
                                nav.goToTab(tab.route)
                            }
                        },
                    )
                }
            }
        },
    ) { inner ->
        CompositionLocalProvider(
            LocalBottomInset provides inner.calculateBottomPadding(),
            LocalOpenVoice provides { nav.navigate(Routes.VOICE) { launchSingleTop = true } },
            LocalNav provides { r: String -> if (tabs.any { it.route == r }) nav.goToTab(r) else nav.navigate(r) { launchSingleTop = true } },
        ) {
            Box(Modifier.fillMaxSize()) {
                NavHost(
                    nav,
                    startDestination = Routes.HOME,
                    enterTransition = { enter() },
                    exitTransition = { exit() },
                    popEnterTransition = { popEnter() },
                    popExitTransition = { popExit() },
                ) {
                    val settings = { nav.navigate(Routes.SETTINGS) { launchSingleTop = true } }
                    composable(Routes.HOME) { HomeScreen(vm, settings) }
                    composable(Routes.ATTENDANCE) { AttendanceScreen(vm, settings, onPortal = { nav.navigate(Routes.PORTAL) { launchSingleTop = true } }) }
                    composable(Routes.MATERIALS) { FilesScreen(vm, settings) }
                    composable(Routes.INBOX) { InboxScreen(vm, settings) }
                    composable(Routes.REMINDERS) { RemindersScreen(vm, onBack = { nav.popBackStack() }) }
                    composable(Routes.PORTAL) { PortalScreen(vm, onDone = { nav.popBackStack() }) }
                    composable(Routes.SETTINGS) {
                        SettingsScreen(
                            vm,
                            onBack = { nav.popBackStack() },
                            onPortalCheck = { nav.navigate(Routes.PORTAL_CHECK) { launchSingleTop = true } },
                            onEditProfile = { nav.navigate(Routes.PROFILE) { launchSingleTop = true } },
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
                        val url by vm.portalCheckUrl.collectAsStateWithLifecycle()
                        PortalCheckScreen(vm, url, onBack = { nav.popBackStack() })
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

// Navigation motion, "fade through": the screen you leave is gone (90 ms) before the one you open
// comes in (210 ms), so no screen ever shows through another, and the one backdrop under both
// stays still. A screen opened from a tab also travels a little from the side it comes from (in
// from the right, back out to the right), and so does the predictive back gesture, which runs
// the same motion under the finger. Tabs aren't a stack: they only fade.

private typealias Nav = AnimatedContentTransitionScope<NavBackStackEntry>

private val NavBackStackEntry.isPushed get() = destination.route in pushed

private fun Nav.enter(): EnterTransition =
    if (targetState.isPushed) slideInHorizontally(Motion.travel) { Motion.nudge(it) } + fadeIn(Motion.arrive)
    else fadeIn(Motion.arrive)

private fun Nav.exit(): ExitTransition =
    if (targetState.isPushed) slideOutHorizontally(Motion.travel) { -Motion.nudge(it) } + fadeOut(Motion.leave)
    else fadeOut(Motion.leave)

private fun Nav.popEnter(): EnterTransition =
    if (initialState.isPushed) slideInHorizontally(Motion.travel) { -Motion.nudge(it) } + fadeIn(Motion.arrive)
    else fadeIn(Motion.arrive)

private fun Nav.popExit(): ExitTransition =
    if (initialState.isPushed) slideOutHorizontally(Motion.travel) { Motion.nudge(it) } + fadeOut(Motion.leave)
    else fadeOut(Motion.leave)

/** The tab bar comes and goes with the tab screens: out as they leave, in as they arrive. */
private val barIn = fadeIn(Motion.arrive)
private val barOut = fadeOut(Motion.leave)

/**
 * The tab bar, iOS style: a frosted capsule floating over the content, with a soft selection
 * pill that glides between tabs on a spring.
 */
@Composable
private fun GlassTabBar(selected: Int, badge: (Tab) -> Int, onAi: () -> Unit, onSelect: (Tab) -> Unit) {
    val haptics = LocalHapticFeedback.current
    val app = LocalAppColors.current
    val primary = MaterialTheme.colorScheme.primary
    BoxWithConstraints(
        Modifier
            .fillMaxWidth()
            .height(68.dp)
            .drawBehind {
                drawLine(app.hairline, androidx.compose.ui.geometry.Offset(0f, 0f), androidx.compose.ui.geometry.Offset(size.width, 0f), strokeWidth = 1.dp.toPx())
            },
    ) {
        // Neo-minimal: an icon and a word per tab; the current one in ink with an orange dot.
        // In the middle, the AI: one orange button that opens the voice assistant.
        val itemWidth = maxWidth / (tabs.size + 1)
        Row(Modifier.fillMaxSize()) {
            tabs.forEachIndexed { index, tab ->
                if (index == AI_SLOT) {
                    // The AI: one big orange button lifted half out of the bar, ringed in the
                    // background colour so it sits on top of the bar, with a warm shadow.
                    Box(Modifier.width(itemWidth).fillMaxHeight()) {
                        AskAiButton(onAi, Modifier.align(Alignment.TopCenter).offset(y = -AI_RISE))
                        Text(
                            "Ask AI",
                            color = MaterialTheme.colorScheme.onSurface,
                            fontSize = 10.5.sp,
                            lineHeight = 13.sp,
                            fontFamily = com.sevenfive.app.ui.theme.Neo,
                            fontWeight = FontWeight.SemiBold,
                            maxLines = 1,
                            modifier = Modifier.align(Alignment.BottomCenter).padding(bottom = 9.dp),
                        )
                    }
                }
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
                    Box(Modifier.size(ICON_AREA), contentAlignment = Alignment.Center) {
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
                                    .offset(x = 2.dp, y = 0.dp)
                                    .defaultMinSize(minWidth = 15.dp)
                                    .background(com.sevenfive.app.ui.theme.Orange, CircleShape)
                                    .padding(horizontal = 3.dp, vertical = 1.dp),
                            )
                        }
                    }
                    Text(
                        tab.label,
                        color = tint,
                        fontSize = 10.5.sp,
                        lineHeight = 13.sp,
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

/** Where the AI button sits in the tab bar: after the first two tabs, in the middle. */
private const val AI_SLOT = 2

/** The square every tab's icon (and the AI's circle) sits in, so all of them line up. */
private val ICON_AREA = 34.dp

/** The Ask AI button: its size, and how far it rises above the tab bar's top edge. */
private val AI_SIZE = 58.dp
private val AI_RISE = 24.dp

/** A raised orange button: a lighter top, a soft orange shadow, ringed in the page's colour. */
@Composable
private fun AskAiButton(onClick: () -> Unit, modifier: Modifier = Modifier) {
    val ground = MaterialTheme.colorScheme.background
    Box(
        modifier
            .size(AI_SIZE)
            .shadow(10.dp, CircleShape, ambientColor = com.sevenfive.app.ui.theme.Orange, spotColor = com.sevenfive.app.ui.theme.Orange)
            .semantics { contentDescription = "Talk to your AI" }
            .pressable(scaleTo = 0.9f, haptic = true, role = Role.Button, onClick = onClick)
            .background(ground, CircleShape)
            .padding(4.dp)
            .background(
                androidx.compose.ui.graphics.Brush.verticalGradient(
                    listOf(androidx.compose.ui.graphics.Color(0xFFFFA64D), com.sevenfive.app.ui.theme.Orange, androidx.compose.ui.graphics.Color(0xFFEE7410)),
                ),
                CircleShape,
            ),
        contentAlignment = Alignment.Center,
    ) {
        Icon(Icons.Filled.Mic, contentDescription = null, tint = com.sevenfive.app.ui.theme.NeoInk, modifier = Modifier.size(24.dp))
    }
}

/** Home, its root, from anywhere: everything above it closes, nothing saved is brought back. */
private fun NavHostController.goHome() {
    if (currentDestination?.route == Routes.HOME) return
    if (!popBackStack(Routes.HOME, inclusive = false)) {
        navigate(Routes.HOME) {
            popUpTo(graph.findStartDestination().id) { inclusive = false }
            launchSingleTop = true
        }
    }
}

private fun NavHostController.goToTab(route: String) = navigate(route) {
    popUpTo(graph.findStartDestination().id) { saveState = true }
    launchSingleTop = true
    restoreState = true
}
