package com.sevenfive.app.ui.theme

import androidx.compose.foundation.BorderStroke
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.material3.MaterialTheme
import androidx.compose.runtime.Composable
import androidx.compose.runtime.compositionLocalOf
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.draw.drawBehind
import androidx.compose.ui.graphics.graphicsLayer
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.Shape
import androidx.compose.ui.unit.Dp
import androidx.compose.ui.unit.dp
import dev.chrisbanes.haze.ExperimentalHazeApi
import dev.chrisbanes.haze.HazeInputScale
import dev.chrisbanes.haze.HazeState
import dev.chrisbanes.haze.HazeStyle
import dev.chrisbanes.haze.HazeTint
import dev.chrisbanes.haze.hazeEffect
import kotlin.math.max

/**
 * The room under the glass: the theme's base colour with three soft pools of light (brand warm,
 * peach, a cool accent). Static on purpose: a moving backdrop would make every frosted bar
 * re-blur on every frame, and scrolling must stay smooth on mid-range phones.
 */
@Composable
fun AuroraBackground(modifier: Modifier = Modifier) {
    val base = MaterialTheme.colorScheme.background
    val app = LocalAppColors.current
    Box(
        // Its own layer: drawn once and reused, not redrawn as lists scroll over it.
        modifier.fillMaxSize().graphicsLayer().drawBehind {
            drawRect(base)
            val r = max(size.width, size.height)
            fun pool(color: Color, x: Float, y: Float, radius: Float) {
                val center = Offset(size.width * x, size.height * y)
                drawCircle(
                    Brush.radialGradient(listOf(color, Color.Transparent), center = center, radius = r * radius),
                    radius = r * radius,
                    center = center,
                )
            }
            // Neo-minimal: a flat ground. The pools only draw if a theme gives them colour.
            if (app.auroraWarm.alpha > 0f) pool(app.auroraWarm, 0.05f, 0.0f, 0.62f)
            if (app.auroraPeach.alpha > 0f) pool(app.auroraPeach, 1.0f, 0.22f, 0.55f)
            if (app.auroraCool.alpha > 0f) pool(app.auroraCool, 0.15f, 1.0f, 0.65f)
        },
    )
}

/** Frosted glass for bars: blur what scrolls underneath, tinted; a plain tint before Android 12. */
@Composable
fun frostedStyle(): HazeStyle {
    val app = LocalAppColors.current
    return HazeStyle(
        backgroundColor = MaterialTheme.colorScheme.background,
        tint = HazeTint(app.glassTint),
        blurRadius = 22.dp,
        noiseFactor = 0f,
        fallbackTint = HazeTint(app.glassFallback.copy(alpha = 0.97f)),
    )
}

/**
 * A glass card: a translucent fill over the backdrop and a hairline edge that is brighter on
 * top, like light catching the rim. [strong] is for things that need more presence.
 */
@Composable
fun Modifier.glassSurface(
    shape: Shape = MaterialTheme.shapes.large,
    strong: Boolean = false,
    tint: Color = Color.Unspecified,
    edgeWidth: Dp = 0.8.dp,
): Modifier {
    val app = LocalAppColors.current
    // Neo-minimal: a flat, quiet fill and no rim. [strong] is a touch darker for controls.
    val fill = if (strong) MaterialTheme.colorScheme.surfaceContainerHigh else app.glassFill
    val edge = app.glassEdge
    return this
        .clip(shape)
        .background(fill)
        .then(if (tint != Color.Unspecified) Modifier.background(tint) else Modifier)
        .then(if (edge.alpha > 0f) Modifier.border(BorderStroke(edgeWidth, edge), shape) else Modifier)
}

/**
 * Real frosted glass for things that float over content (the tab bar, the demo guide): what is
 * behind is blurred and tinted, with the same bright rim as [glassSurface].
 */
@OptIn(ExperimentalHazeApi::class)
@Composable
fun Modifier.frosted(state: HazeState, shape: Shape, edgeWidth: Dp = 0.8.dp): Modifier {
    val app = LocalAppColors.current
    return this
        .clip(shape)
        .hazeEffect(state = state, style = frostedStyle()) { inputScale = HazeInputScale.Auto }
        .then(if (app.glassEdge.alpha > 0f) Modifier.border(BorderStroke(edgeWidth, app.glassEdge), shape) else Modifier)
}

/** How much room the floating tab bar takes at the bottom, so lists can scroll under it. */
val LocalBottomInset = compositionLocalOf { 0.dp }
