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
 * The room under everything: the flat neo ground, a warm glow drifting slowly across, and small
 * particles rising with a gentle sway, like dust in light. Quiet: seen only between cards, and
 * still when the phone's animations are off.
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
    // The particles' clock: one long loop; every particle's motion fits it exactly.
    val float by turn.animateFloat(
        initialValue = 0f,
        targetValue = if (still) 0f else 1f,
        animationSpec = androidx.compose.animation.core.infiniteRepeatable(
            androidx.compose.animation.core.tween(150_000, easing = androidx.compose.animation.core.LinearEasing),
        ),
        label = "particles",
    )
    // The glow's wander: once round a slow figure-of-eight a minute.
    val drift by turn.animateFloat(
        initialValue = 0f,
        targetValue = if (still) 0f else 1f,
        animationSpec = androidx.compose.animation.core.infiniteRepeatable(
            androidx.compose.animation.core.tween(60_000, easing = androidx.compose.animation.core.LinearEasing),
        ),
        label = "glow",
    )
    Box(
        modifier.fillMaxSize().drawBehind {
            drawRect(base)
            // A soft warm glow drifting across, like light moving over paper. Barely there.
            val phase = drift * 2f * Math.PI.toFloat()
            val glow = Offset(
                size.width * (0.45f + 0.30f * kotlin.math.sin(phase)),
                size.height * (0.40f + 0.18f * kotlin.math.sin(2f * phase + 1f)),
            )
            val reach = size.width * 0.95f
            drawCircle(
                Brush.radialGradient(
                    listOf(Orange.copy(alpha = 0.16f), Orange.copy(alpha = 0.06f), Color.Transparent),
                    center = glow,
                    radius = reach,
                ),
                radius = reach,
                center = glow,
            )
            // Particles: small dots drifting slowly up with a gentle sway, mostly soft ink, a few
            // orange. Each one's speed and sway are whole turns of the loop, so it never jumps.
            val t = float
            particles.forEach { p ->
                val y = ((p.y - t * p.rise) % 1f + 1f) % 1f
                val x = p.x + p.sway * kotlin.math.sin((t * p.waves + p.phase) * 2f * Math.PI.toFloat())
                // Fade in near the bottom, out near the top.
                val edge = (kotlin.math.min(y, 1f - y) / 0.12f).coerceIn(0f, 1f)
                drawCircle(
                    (if (p.warm) Orange else NeoInk).copy(alpha = p.alpha * edge),
                    radius = p.size.dp.toPx(),
                    center = Offset(x * size.width, y * size.height),
                )
            }
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


/** One background particle: where it starts, how it moves, how it looks. */
private data class Particle(
    val x: Float, val y: Float, val rise: Float, val sway: Float, val waves: Float,
    val phase: Float, val size: Float, val alpha: Float, val warm: Boolean,
)

/** The same 34 particles every time (a fixed seed), so the background never reshuffles. */
private val particles: List<Particle> = kotlin.random.Random(75).let { r ->
    List(34) { i ->
        Particle(
            x = r.nextFloat(),
            y = r.nextFloat(),
            rise = (1 + r.nextInt(3)).toFloat(), // 1 to 3 screen heights per loop: slow
            sway = 0.01f + r.nextFloat() * 0.03f,
            waves = (2 + r.nextInt(4)).toFloat(),
            phase = r.nextFloat(),
            size = 1.5f + r.nextFloat() * 2.5f,
            alpha = 0.10f + r.nextFloat() * 0.22f,
            warm = i % 4 == 0,
        )
    }
}
