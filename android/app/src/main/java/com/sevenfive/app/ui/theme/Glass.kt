package com.sevenfive.app.ui.theme

import androidx.compose.foundation.BorderStroke
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.material3.MaterialTheme
import androidx.compose.animation.core.animateFloat
import androidx.compose.runtime.Composable
import androidx.compose.ui.graphics.drawscope.rotate
import androidx.compose.runtime.getValue
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
 * The room under everything: the flat neo ground, and the brand's open ring drawn very large and
 * faint, turning slowly. One thin orange arc off the top-right corner, one fainter ink arc off the
 * bottom-left; a turn takes a minute and a half to two and a half, so it reads as a clock face
 * breathing, not as motion. Still when the phone's animations are off. Seen only between cards.
 */
@Composable
fun AuroraBackground(modifier: Modifier = Modifier) {
    val base = MaterialTheme.colorScheme.background
    val context = androidx.compose.ui.platform.LocalContext.current
    val still = androidx.compose.runtime.remember {
        android.provider.Settings.Global.getFloat(
            context.contentResolver, android.provider.Settings.Global.ANIMATOR_DURATION_SCALE, 1f,
        ) == 0f
    }
    val turn = androidx.compose.animation.core.rememberInfiniteTransition(label = "rings")
    val slow by turn.animateFloat(
        initialValue = 0f,
        targetValue = if (still) 0f else 360f,
        animationSpec = androidx.compose.animation.core.infiniteRepeatable(
            androidx.compose.animation.core.tween(90_000, easing = androidx.compose.animation.core.LinearEasing),
        ),
        label = "ring one",
    )
    val slower by turn.animateFloat(
        initialValue = 0f,
        targetValue = if (still) 0f else -360f,
        animationSpec = androidx.compose.animation.core.infiniteRepeatable(
            androidx.compose.animation.core.tween(150_000, easing = androidx.compose.animation.core.LinearEasing),
        ),
        label = "ring two",
    )
    Box(
        modifier.fillMaxSize().drawBehind {
            drawRect(base)
            fun ring(center: Offset, radius: Float, angle: Float, sweep: Float, color: Color, width: Float) {
                rotate(angle, pivot = center) {
                    drawArc(
                        color = color,
                        startAngle = -90f,
                        sweepAngle = sweep,
                        useCenter = false,
                        topLeft = Offset(center.x - radius, center.y - radius),
                        size = androidx.compose.ui.geometry.Size(radius * 2, radius * 2),
                        style = androidx.compose.ui.graphics.drawscope.Stroke(
                            width = width, cap = androidx.compose.ui.graphics.StrokeCap.Round,
                        ),
                    )
                }
            }
            val w = size.width
            // The brand ring, huge and faint, off the top-right corner.
            ring(Offset(w * 0.98f, size.height * 0.10f), w * 0.62f, slow, 270f, Orange.copy(alpha = 0.10f), w * 0.028f)
            // A fine ink echo around it.
            ring(Offset(w * 0.98f, size.height * 0.10f), w * 0.80f, slower, 200f, NeoInk.copy(alpha = 0.05f), 1.2.dp.toPx())
            // And one off the bottom-left, fainter still.
            ring(Offset(w * 0.04f, size.height * 0.94f), w * 0.55f, slower * 0.8f, 240f, NeoInk.copy(alpha = 0.04f), w * 0.02f)
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
        // A solid bar (the neo theme) needs no blur: and none means the slowly turning rings
        // behind it never make the bar re-blur on every frame.
        blurRadius = if (app.glassTint.alpha >= 1f) 0.dp else 22.dp,
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
