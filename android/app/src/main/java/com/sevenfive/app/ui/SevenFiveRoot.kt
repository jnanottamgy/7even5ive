package com.sevenfive.app.ui

import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.WindowInsets
import androidx.compose.foundation.layout.consumeWindowInsets
import androidx.compose.foundation.layout.padding
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Alarm
import androidx.compose.material.icons.filled.Home
import androidx.compose.material.icons.filled.Inbox
import androidx.compose.material.icons.automirrored.filled.LibraryBooks
import androidx.compose.material.icons.filled.PieChart
import androidx.compose.material.icons.outlined.Alarm
import androidx.compose.material.icons.outlined.Home
import androidx.compose.material.icons.outlined.Inbox
import androidx.compose.material.icons.automirrored.outlined.LibraryBooks
import androidx.compose.material.icons.outlined.PieChart
import androidx.compose.material3.Badge
import androidx.compose.material3.BadgedBox
import androidx.compose.material3.Icon
import androidx.compose.material3.NavigationBar
import androidx.compose.material3.NavigationBarItem
import androidx.compose.material3.Scaffold
import androidx.compose.material3.SnackbarHost
import androidx.compose.material3.SnackbarHostState
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.remember
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.vector.ImageVector
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import androidx.navigation.NavGraph.Companion.findStartDestination
import androidx.navigation.NavHostController
import androidx.navigation.compose.NavHost
import androidx.navigation.compose.composable
import androidx.navigation.compose.currentBackStackEntryAsState
import androidx.navigation.compose.rememberNavController
import com.sevenfive.app.ui.screens.AttendanceScreen
import com.sevenfive.app.ui.screens.HomeScreen
import com.sevenfive.app.ui.screens.InboxScreen
import com.sevenfive.app.ui.screens.MaterialsScreen
import com.sevenfive.app.ui.screens.PortalCheckScreen
import com.sevenfive.app.ui.screens.PortalScreen
import com.sevenfive.app.ui.screens.RemindersScreen
import com.sevenfive.app.ui.screens.SettingsScreen

object Routes {
    const val HOME = "home"
    const val ATTENDANCE = "attendance"
    const val MATERIALS = "materials"
    const val INBOX = "inbox"
    const val REMINDERS = "reminders"
    const val PORTAL = "portal"
    const val SETTINGS = "settings"
    const val PORTAL_CHECK = "portal-check"
}

private data class Tab(val route: String, val label: String, val on: ImageVector, val off: ImageVector)

private val tabs = listOf(
    Tab(Routes.HOME, "This week", Icons.Filled.Home, Icons.Outlined.Home),
    Tab(Routes.ATTENDANCE, "Attendance", Icons.Filled.PieChart, Icons.Outlined.PieChart),
    Tab(Routes.MATERIALS, "Materials", Icons.AutoMirrored.Filled.LibraryBooks, Icons.AutoMirrored.Outlined.LibraryBooks),
    Tab(Routes.INBOX, "Inbox", Icons.Filled.Inbox, Icons.Outlined.Inbox),
    Tab(Routes.REMINDERS, "Reminders", Icons.Filled.Alarm, Icons.Outlined.Alarm),
)

@Composable
fun SevenFiveRoot(vm: AppViewModel) {
    val nav = rememberNavController()
    val snackbar = remember { SnackbarHostState() }
    val state by vm.cards.collectAsStateWithLifecycle()
    val backStack by nav.currentBackStackEntryAsState()
    val route = backStack?.destination?.route

    LaunchedEffect(Unit) {
        vm.messages.collect { snackbar.showSnackbar(it) }
    }

    val showTabs = route in tabs.map { it.route }
    val tour by vm.tour.collectAsStateWithLifecycle()
    // Each demo step opens the tab it talks about.
    LaunchedEffect(tour?.index, tour != null) {
        tour?.let { nav.goToTab(DemoTour.steps[it.index].route) }
    }
    Scaffold(
        // Each screen draws its own top bar under the status bar; this only adds the tabs.
        contentWindowInsets = WindowInsets(0, 0, 0, 0),
        snackbarHost = { SnackbarHost(snackbar) },
        bottomBar = {
            if (showTabs) Column {
                tour?.let { t ->
                    DemoBar(t, onBack = { vm.tourBack() }, onNext = { vm.tourNext() },
                        onAct = { vm.tourAct() }, onClose = { vm.endTour() })
                }
                NavigationBar {
                    tabs.forEach { tab ->
                        val selected = route == tab.route
                        val count = when (tab.route) {
                            Routes.HOME -> state.cards?.approvals?.size ?: 0
                            Routes.REMINDERS -> state.cards?.reminders?.size ?: 0
                            else -> 0
                        }
                        NavigationBarItem(
                            selected = selected,
                            onClick = { nav.goToTab(tab.route) },
                            icon = {
                                BadgedBox(badge = { if (count > 0) Badge { Text("$count") } }) {
                                    Icon(if (selected) tab.on else tab.off, contentDescription = null)
                                }
                            },
                            label = { Text(tab.label, maxLines = 1) },
                        )
                    }
                }
            }
        },
    ) { inner ->
        Box(Modifier.padding(inner).consumeWindowInsets(inner)) {
            NavHost(nav, startDestination = Routes.HOME) {
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
            }
        }
    }
}

private fun NavHostController.goToTab(route: String) = navigate(route) {
    popUpTo(graph.findStartDestination().id) { saveState = true }
    launchSingleTop = true
    restoreState = true
}
