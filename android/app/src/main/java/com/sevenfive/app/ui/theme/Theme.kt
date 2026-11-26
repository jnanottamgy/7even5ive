package com.sevenfive.app.ui.theme

import androidx.compose.foundation.isSystemInDarkTheme
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Shapes
import androidx.compose.material3.Typography
import androidx.compose.material3.darkColorScheme
import androidx.compose.material3.lightColorScheme
import androidx.compose.runtime.Composable
import androidx.compose.runtime.CompositionLocalProvider
import androidx.compose.runtime.Immutable
import androidx.compose.runtime.staticCompositionLocalOf
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.TextStyle
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp

// The brand (brand/): ink, paper, and the mark's amber-to-orange gradient.
val Ink = Color(0xFF0B0C10)
val Paper = Color(0xFFF4F1EA)
val Orange = Color(0xFFFF8A1F)
val Amber = Color(0xFFFFB547)

/** Attendance status colours, iOS system colours, the same on every screen. */
@Immutable
data class StatusColors(val safe: Color, val atRisk: Color, val short: Color, val unrecoverable: Color) {
    fun of(status: String): Color = when (status) {
        "safe" -> safe
        "at_risk" -> atRisk
        "short" -> short
        else -> unrecoverable
    }
}

/**
 * What Material's colour scheme doesn't carry: the glass, the hairlines, the backdrop's colour
 * blobs and one colour per kind of card. Read through [LocalAppColors].
 */
@Immutable
data class AppColors(
    val dark: Boolean,
    /** The frosted tint over blurred content (bars). */
    val glassTint: Color,
    /** A glass card's fill: translucent, so the backdrop shows through. */
    val glassFill: Color,
    /** The fallback when blur isn't available (Android 11 and older): nearly opaque. */
    val glassFallback: Color,
    /** The thin top highlight and edge of glass. */
    val glassEdge: Color,
    val hairline: Color,
    val secondaryLabel: Color,
    val tertiaryLabel: Color,
    val auroraWarm: Color,
    val auroraPeach: Color,
    val auroraCool: Color,
    val deadline: Color,
    val exam: Color,
    val material: Color,
    val event: Color,
    val notice: Color,
)

private val LightApp = AppColors(
    dark = false,
    glassTint = Color(0xFFFFFFFF).copy(alpha = 0.62f),
    glassFill = Color(0xFFFFFFFF).copy(alpha = 0.66f),
    glassFallback = Color(0xFFFBFAF8),
    glassEdge = Color(0xFFFFFFFF).copy(alpha = 0.9f),
    hairline = Color(0xFF3C3C43).copy(alpha = 0.14f),
    secondaryLabel = Color(0xFF3C3C43).copy(alpha = 0.64f),
    tertiaryLabel = Color(0xFF3C3C43).copy(alpha = 0.36f),
    auroraWarm = Color(0xFFFFA45C).copy(alpha = 0.42f),
    auroraPeach = Color(0xFFFFD9A8).copy(alpha = 0.55f),
    auroraCool = Color(0xFF8FD8E6).copy(alpha = 0.30f),
    deadline = Color(0xFFFF9500),
    exam = Color(0xFFFF2D55),
    material = Color(0xFF007AFF),
    event = Color(0xFFAF52DE),
    notice = Color(0xFF30B0C7),
)

private val DarkApp = AppColors(
    dark = true,
    glassTint = Color(0xFF1C1C1E).copy(alpha = 0.58f),
    glassFill = Color(0xFF2C2C2E).copy(alpha = 0.52f),
    glassFallback = Color(0xFF1C1C1E),
    glassEdge = Color(0xFFFFFFFF).copy(alpha = 0.14f),
    hairline = Color(0xFFFFFFFF).copy(alpha = 0.12f),
    secondaryLabel = Color(0xFFEBEBF5).copy(alpha = 0.62f),
    tertiaryLabel = Color(0xFFEBEBF5).copy(alpha = 0.32f),
    auroraWarm = Color(0xFFFF8A1F).copy(alpha = 0.26f),
    auroraPeach = Color(0xFF7A4DFF).copy(alpha = 0.16f),
    auroraCool = Color(0xFF2FB7C9).copy(alpha = 0.14f),
    deadline = Color(0xFFFF9F0A),
    exam = Color(0xFFFF375F),
    material = Color(0xFF0A84FF),
    event = Color(0xFFBF5AF2),
    notice = Color(0xFF40C8E0),
)

private val LightStatus = StatusColors(Color(0xFF34C759), Color(0xFFFF9500), Color(0xFFFF3B30), Color(0xFFD70015))
private val DarkStatus = StatusColors(Color(0xFF30D158), Color(0xFFFF9F0A), Color(0xFFFF453A), Color(0xFFFF6961))

val LocalStatusColors = staticCompositionLocalOf { LightStatus }
val LocalAppColors = staticCompositionLocalOf { LightApp }

private val Light = lightColorScheme(
    primary = Color(0xFFF27A0C),
    onPrimary = Color.White,
    primaryContainer = Color(0xFFFFE3C7),
    onPrimaryContainer = Color(0xFF3D1E00),
    secondary = Color(0xFF6E6E73),
    onSecondary = Color.White,
    secondaryContainer = Color(0xFFEDE7DD),
    onSecondaryContainer = Ink,
    tertiary = Color(0xFF248A3D),
    onTertiary = Color.White,
    background = Color(0xFFF6F3EE),
    onBackground = Color(0xFF111114),
    surface = Color(0xFFF6F3EE),
    onSurface = Color(0xFF111114),
    surfaceVariant = Color(0xFFE9E5DE),
    onSurfaceVariant = Color(0xFF3C3C43).copy(alpha = 0.64f),
    surfaceContainerLowest = Color.White,
    surfaceContainerLow = Color(0xFFFBFAF8),
    surfaceContainer = Color(0xFFF2EFEA),
    surfaceContainerHigh = Color(0xFFECE8E1),
    surfaceContainerHighest = Color(0xFFE6E1D9),
    outline = Color(0xFF8E8E93),
    outlineVariant = Color(0xFF3C3C43).copy(alpha = 0.16f),
    error = Color(0xFFFF3B30),
    onError = Color.White,
    errorContainer = Color(0xFFFFE5E3),
    onErrorContainer = Color(0xFF5C0A05),
)

private val Dark = darkColorScheme(
    primary = Color(0xFFFF9F0A),
    onPrimary = Ink,
    primaryContainer = Color(0xFF4A2A00),
    onPrimaryContainer = Color(0xFFFFDDB5),
    secondary = Color(0xFF98989F),
    onSecondary = Ink,
    secondaryContainer = Color(0xFF2C2C2E),
    onSecondaryContainer = Color(0xFFF2F2F7),
    tertiary = Color(0xFF30D158),
    onTertiary = Ink,
    background = Ink,
    onBackground = Color(0xFFF2F2F7),
    surface = Ink,
    onSurface = Color(0xFFF2F2F7),
    surfaceVariant = Color(0xFF2C2C2E),
    onSurfaceVariant = Color(0xFFEBEBF5).copy(alpha = 0.62f),
    surfaceContainerLowest = Color(0xFF050608),
    surfaceContainerLow = Color(0xFF151619),
    surfaceContainer = Color(0xFF1C1C1E),
    surfaceContainerHigh = Color(0xFF242427),
    surfaceContainerHighest = Color(0xFF2C2C2E),
    outline = Color(0xFF8E8E93),
    outlineVariant = Color(0xFFFFFFFF).copy(alpha = 0.12f),
    error = Color(0xFFFF453A),
    onError = Ink,
    errorContainer = Color(0xFF4A0F0B),
    onErrorContainer = Color(0xFFFFDAD6),
)

/** iOS's type scale, on the system font: large bold titles, 17 pt body, tight tracking up top. */
private val AppTypography = Typography(
    headlineLarge = TextStyle(fontSize = 34.sp, lineHeight = 41.sp, fontWeight = FontWeight.Bold, letterSpacing = (-0.6).sp),
    headlineMedium = TextStyle(fontSize = 34.sp, lineHeight = 41.sp, fontWeight = FontWeight.Bold, letterSpacing = (-0.6).sp),
    headlineSmall = TextStyle(fontSize = 28.sp, lineHeight = 34.sp, fontWeight = FontWeight.Bold, letterSpacing = (-0.5).sp),
    titleLarge = TextStyle(fontSize = 17.sp, lineHeight = 22.sp, fontWeight = FontWeight.SemiBold, letterSpacing = (-0.2).sp),
    titleMedium = TextStyle(fontSize = 17.sp, lineHeight = 22.sp, fontWeight = FontWeight.SemiBold, letterSpacing = (-0.2).sp),
    titleSmall = TextStyle(fontSize = 15.sp, lineHeight = 20.sp, fontWeight = FontWeight.SemiBold, letterSpacing = (-0.1).sp),
    bodyLarge = TextStyle(fontSize = 17.sp, lineHeight = 22.sp, fontWeight = FontWeight.Normal, letterSpacing = (-0.2).sp),
    bodyMedium = TextStyle(fontSize = 15.sp, lineHeight = 20.sp, fontWeight = FontWeight.Normal, letterSpacing = (-0.1).sp),
    bodySmall = TextStyle(fontSize = 13.sp, lineHeight = 18.sp, fontWeight = FontWeight.Normal),
    labelLarge = TextStyle(fontSize = 15.sp, lineHeight = 20.sp, fontWeight = FontWeight.SemiBold, letterSpacing = (-0.1).sp),
    labelMedium = TextStyle(fontSize = 13.sp, lineHeight = 18.sp, fontWeight = FontWeight.Medium),
    labelSmall = TextStyle(fontSize = 11.sp, lineHeight = 13.sp, fontWeight = FontWeight.SemiBold, letterSpacing = 0.1.sp),
)

private val AppShapes = Shapes(
    extraSmall = RoundedCornerShape(8.dp),
    small = RoundedCornerShape(12.dp),
    medium = RoundedCornerShape(16.dp),
    large = RoundedCornerShape(22.dp),
    extraLarge = RoundedCornerShape(28.dp),
)

@Composable
fun SevenFiveTheme(dark: Boolean = isSystemInDarkTheme(), content: @Composable () -> Unit) {
    CompositionLocalProvider(
        LocalStatusColors provides if (dark) DarkStatus else LightStatus,
        LocalAppColors provides if (dark) DarkApp else LightApp,
    ) {
        MaterialTheme(
            colorScheme = if (dark) Dark else Light,
            typography = AppTypography,
            shapes = AppShapes,
            content = content,
        )
    }
}
