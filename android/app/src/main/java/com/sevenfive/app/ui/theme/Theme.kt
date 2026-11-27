package com.sevenfive.app.ui.theme

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
import androidx.compose.ui.text.font.Font
import androidx.compose.ui.text.font.FontFamily
import com.sevenfive.app.R
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp

// The brand (brand/): ink, paper, and the mark's amber-to-orange gradient.
val Ink = Color(0xFF0B0C10)
val Paper = Color(0xFFF4F1EA)
val Orange = Color(0xFFFF8A1F)
val Amber = Color(0xFFFFB547)

/** Neo-minimal: one typeface at very different sizes. Inter Tight, bundled (res/font). */
val Neo = FontFamily(
    Font(R.font.inter_tight_regular, FontWeight.Normal),
    Font(R.font.inter_tight_medium, FontWeight.Medium),
    Font(R.font.inter_tight_semibold, FontWeight.SemiBold),
    Font(R.font.inter_tight_semibold, FontWeight.Bold),
)

/** The neo palette: soft off-white, near-black ink, one grey, and orange only where it matters. */
val NeoGround = Color(0xFFF3F3F0)
val NeoInk = Color(0xFF111111)
val NeoGrey = Color(0xFF66665F)
val NeoLine = Color(0xFFDADAD5)
val NeoFill = Color(0xFFE8E8E3)

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
    glassTint = NeoGround,
    glassFill = NeoFill,
    glassFallback = NeoGround,
    glassEdge = Color.Transparent,
    hairline = NeoLine,
    secondaryLabel = NeoGrey,
    tertiaryLabel = Color(0xFF8C8C85),
    auroraWarm = Color.Transparent,
    auroraPeach = Color.Transparent,
    auroraCool = Color.Transparent,
    // Kinds stay quiet: ink and grey, with orange kept for exams (the thing that can't move).
    deadline = NeoInk,
    exam = Color(0xFFE0670A),
    material = NeoGrey,
    event = NeoInk,
    notice = NeoGrey,
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

private val LightStatus = StatusColors(NeoInk, Color(0xFFE0670A), Color(0xFFC2410C), Color(0xFF9A3412))
private val DarkStatus = StatusColors(Color(0xFF30D158), Color(0xFFFF9F0A), Color(0xFFFF453A), Color(0xFFFF6961))

val LocalStatusColors = staticCompositionLocalOf { LightStatus }
val LocalAppColors = staticCompositionLocalOf { LightApp }

private val Light = lightColorScheme(
    primary = NeoInk,
    onPrimary = NeoGround,
    primaryContainer = NeoFill,
    onPrimaryContainer = NeoInk,
    secondary = NeoGrey,
    onSecondary = Color.White,
    secondaryContainer = NeoFill,
    onSecondaryContainer = NeoInk,
    tertiary = Orange,
    onTertiary = NeoInk,
    background = NeoGround,
    onBackground = NeoInk,
    surface = NeoGround,
    onSurface = NeoInk,
    surfaceVariant = NeoFill,
    onSurfaceVariant = NeoGrey,
    surfaceContainerLowest = Color.White,
    surfaceContainerLow = Color(0xFFF7F7F4),
    surfaceContainer = NeoFill,
    surfaceContainerHigh = Color(0xFFE2E2DC),
    surfaceContainerHighest = Color(0xFFDCDCD6),
    outline = Color(0xFF8C8C85),
    outlineVariant = NeoLine,
    error = Color(0xFFC2410C),
    onError = Color.White,
    errorContainer = Color(0xFFFBE7DA),
    onErrorContainer = Color(0xFF5A1D04),
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

/** Neo-minimal type: huge, tight headlines; calm body; small quiet labels. One family. */
private val AppTypography = Typography(
    displayLarge = TextStyle(fontFamily = Neo, fontSize = 96.sp, lineHeight = 88.sp, fontWeight = FontWeight.SemiBold, letterSpacing = (-4.5).sp),
    displayMedium = TextStyle(fontFamily = Neo, fontSize = 60.sp, lineHeight = 59.sp, fontWeight = FontWeight.SemiBold, letterSpacing = (-2.5).sp),
    displaySmall = TextStyle(fontFamily = Neo, fontSize = 44.sp, lineHeight = 46.sp, fontWeight = FontWeight.SemiBold, letterSpacing = (-1.5).sp),
    headlineLarge = TextStyle(fontFamily = Neo, fontSize = 36.sp, lineHeight = 40.sp, fontWeight = FontWeight.SemiBold, letterSpacing = (-1.2).sp),
    headlineMedium = TextStyle(fontFamily = Neo, fontSize = 36.sp, lineHeight = 40.sp, fontWeight = FontWeight.SemiBold, letterSpacing = (-1.2).sp),
    headlineSmall = TextStyle(fontFamily = Neo, fontSize = 28.sp, lineHeight = 32.sp, fontWeight = FontWeight.SemiBold, letterSpacing = (-0.8).sp),
    titleLarge = TextStyle(fontFamily = Neo, fontSize = 20.sp, lineHeight = 25.sp, fontWeight = FontWeight.Medium, letterSpacing = (-0.4).sp),
    titleMedium = TextStyle(fontFamily = Neo, fontSize = 17.sp, lineHeight = 22.sp, fontWeight = FontWeight.Medium, letterSpacing = (-0.2).sp),
    titleSmall = TextStyle(fontFamily = Neo, fontSize = 15.sp, lineHeight = 20.sp, fontWeight = FontWeight.Medium, letterSpacing = (-0.1).sp),
    bodyLarge = TextStyle(fontFamily = Neo, fontSize = 16.sp, lineHeight = 22.sp, fontWeight = FontWeight.Normal, letterSpacing = (-0.1).sp),
    bodyMedium = TextStyle(fontFamily = Neo, fontSize = 15.sp, lineHeight = 20.sp, fontWeight = FontWeight.Normal),
    bodySmall = TextStyle(fontFamily = Neo, fontSize = 13.sp, lineHeight = 18.sp, fontWeight = FontWeight.Normal),
    labelLarge = TextStyle(fontFamily = Neo, fontSize = 15.sp, lineHeight = 20.sp, fontWeight = FontWeight.SemiBold),
    labelMedium = TextStyle(fontFamily = Neo, fontSize = 13.sp, lineHeight = 18.sp, fontWeight = FontWeight.Medium),
    labelSmall = TextStyle(fontFamily = Neo, fontSize = 11.sp, lineHeight = 14.sp, fontWeight = FontWeight.Medium, letterSpacing = 0.6.sp),
)

private val AppShapes = Shapes(
    extraSmall = RoundedCornerShape(10.dp),
    small = RoundedCornerShape(14.dp),
    medium = RoundedCornerShape(20.dp),
    large = RoundedCornerShape(24.dp),
    extraLarge = RoundedCornerShape(32.dp),
)

/** Light only, by design: the app always looks the way it was designed, whatever the phone's setting. */
@Composable
fun SevenFiveTheme(dark: Boolean = false, content: @Composable () -> Unit) {
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
