package com.sevenfive.app.ui.theme

import androidx.compose.foundation.isSystemInDarkTheme
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.darkColorScheme
import androidx.compose.material3.lightColorScheme
import androidx.compose.runtime.Composable
import androidx.compose.runtime.Immutable
import androidx.compose.runtime.staticCompositionLocalOf
import androidx.compose.ui.graphics.Color

// From brand/: ink, paper, and the mark's amber-to-orange gradient.
val Ink = Color(0xFF0B0C10)
val Paper = Color(0xFFF4F1EA)
val Orange = Color(0xFFFF8A1F)
val DeepOrange = Color(0xFFF08C00)
val Amber = Color(0xFFFFB547)
val Peach = Color(0xFFFFD08A)

/** Attendance status colours, the same in every screen. */
@Immutable
data class StatusColors(val safe: Color, val atRisk: Color, val short: Color, val unrecoverable: Color) {
    fun of(status: String): Color = when (status) {
        "safe" -> safe
        "at_risk" -> atRisk
        "short" -> short
        else -> unrecoverable
    }
}

private val LightStatus = StatusColors(Color(0xFF1F8A4C), Color(0xFFB86E00), Color(0xFFD9480F), Color(0xFFB3261E))
private val DarkStatus = StatusColors(Color(0xFF5BD18B), Color(0xFFFFB547), Color(0xFFFF8A4C), Color(0xFFFF6B60))

val LocalStatusColors = staticCompositionLocalOf { LightStatus }

private val Light = lightColorScheme(
    primary = DeepOrange,
    onPrimary = Color.White,
    primaryContainer = Peach,
    onPrimaryContainer = Ink,
    secondary = Color(0xFF6B5E4B),
    onSecondary = Color.White,
    secondaryContainer = Color(0xFFEDE4D3),
    onSecondaryContainer = Ink,
    tertiary = Color(0xFF2F6F73),
    background = Paper,
    onBackground = Ink,
    surface = Paper,
    onSurface = Ink,
    surfaceVariant = Color(0xFFE9E3D7),
    onSurfaceVariant = Color(0xFF4D4639),
    surfaceContainerLowest = Color.White,
    surfaceContainerLow = Color(0xFFFBF8F2),
    surfaceContainer = Color(0xFFF7F3EC),
    surfaceContainerHigh = Color(0xFFEFEAE0),
    surfaceContainerHighest = Color(0xFFE9E3D7),
    outline = Color(0xFF8A8172),
    outlineVariant = Color(0xFFD6CEBF),
)

private val Dark = darkColorScheme(
    primary = Amber,
    onPrimary = Ink,
    primaryContainer = Color(0xFF5A3400),
    onPrimaryContainer = Peach,
    secondary = Color(0xFFD6C6AC),
    onSecondary = Ink,
    secondaryContainer = Color(0xFF2A2620),
    onSecondaryContainer = Paper,
    tertiary = Color(0xFF8FD3D6),
    background = Ink,
    onBackground = Paper,
    surface = Ink,
    onSurface = Paper,
    surfaceVariant = Color(0xFF26272D),
    onSurfaceVariant = Color(0xFFC9C2B5),
    surfaceContainerLowest = Color(0xFF07080B),
    surfaceContainerLow = Color(0xFF121318),
    surfaceContainer = Color(0xFF17181E),
    surfaceContainerHigh = Color(0xFF1E1F25),
    surfaceContainerHighest = Color(0xFF26272D),
    outline = Color(0xFF8E8778),
    outlineVariant = Color(0xFF3A3A40),
)

@Composable
fun SevenFiveTheme(dark: Boolean = isSystemInDarkTheme(), content: @Composable () -> Unit) {
    androidx.compose.runtime.CompositionLocalProvider(
        LocalStatusColors provides if (dark) DarkStatus else LightStatus
    ) {
        MaterialTheme(colorScheme = if (dark) Dark else Light, content = content)
    }
}
