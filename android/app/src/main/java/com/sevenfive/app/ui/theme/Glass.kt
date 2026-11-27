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
import androidx.compose.ui.draw.drawWithCache
import androidx.compose.ui.graphics.graphicsLayer
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.Shape
import androidx.compose.ui.unit.Dp
import androidx.compose.ui.unit.dp
import kotlin.math.max

/**
 * The room under everything: the flat neo ground, a warm glow drifting slowly across, and fine
 * contour lines spreading from the top-right corner that slowly breathe, like a map's or a sound's.
 * Quiet: seen only between cards, and still when the phone's animations are off.
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
    // One slow clock for the whole background, ticking 10 times a second instead of every frame:
    // the motion is so slow (at most a pixel or two per tick) it looks the same, and the phone
    // draws it 6 to 12 times less often than at full frame rate.
    // It pauses by itself whenever the app isn't on screen (no frames are drawn then).
    val clock = androidx.compose.runtime.remember { androidx.compose.runtime.mutableLongStateOf(0L) }
    androidx.compose.runtime.LaunchedEffect(still) {
        if (still) return@LaunchedEffect
        val start = androidx.compose.runtime.withFrameMillis { it }
        while (true) {
            kotlinx.coroutines.delay(100)
            clock.longValue = androidx.compose.runtime.withFrameMillis { it } - start
        }
    }
    // The contour paths are made once and reshaped in place, so drawing makes no garbage.
    val paths = androidx.compose.runtime.remember { List(8) { androidx.compose.ui.graphics.Path() } }
    Box(
        // Its own layer: redrawing the background never redraws what sits on top of it.
        modifier.fillMaxSize().graphicsLayer().drawBehind {
            val ms = clock.longValue
            val drift = (ms % 60_000L) / 60_000f
            val float = (ms % 40_000L) / 40_000f
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
            // Contour lines, like a map's or a sound's: loops spreading from the top-right corner,
            // each gently wobbling; the wobble's phase turns slowly, so the lines breathe and flow.
            val wobble = float * 2f * Math.PI.toFloat()
            val center = Offset(size.width * 0.92f, size.height * 0.16f)
            val step = size.width * 0.15f
            val line = 1.dp.toPx()
            for (n in 0 until 8) {
                val base = size.width * 0.22f + n * step
                val path = paths[n]
                path.reset()
                val points = 96
                for (k in 0..points) {
                    val a = k / points.toFloat() * 2f * Math.PI.toFloat()
                    val r = base +
                        step * 0.16f * kotlin.math.sin(3f * a + wobble + n * 0.55f) +
                        step * 0.10f * kotlin.math.sin(5f * a - 2f * wobble + n * 0.9f)
                    val x = center.x + r * kotlin.math.cos(a)
                    val y = center.y + r * kotlin.math.sin(a)
                    if (k == 0) path.moveTo(x, y) else path.lineTo(x, y)
                }
                path.close()
                val warm = n == 2
                drawPath(
                    path,
                    color = if (warm) Orange.copy(alpha = 0.30f) else NeoInk.copy(alpha = 0.10f - n * 0.005f),
                    style = androidx.compose.ui.graphics.drawscope.Stroke(width = if (warm) line * 1.6f else line),
                )
            }
        },
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
    // Frosted glass, without a live blur (that would redraw every frame): translucent white,
    // a little brighter at the top; a soft sheen in the top-left corner; and a rim that catches
    // the light, bright white along the top fading to a fine dark line at the bottom.
    val top = if (strong) 0.82f else app.glassFill.alpha + 0.12f
    val bottom = if (strong) 0.66f else app.glassFill.alpha - 0.08f
    // Made once per look, not on every recomposition.
    val fill = androidx.compose.runtime.remember(top, bottom) {
        Brush.verticalGradient(listOf(Color.White.copy(alpha = top), Color.White.copy(alpha = bottom)))
    }
    val rim = androidx.compose.runtime.remember(app.glassEdge) {
        Brush.verticalGradient(
            0f to app.glassEdge,
            0.45f to Color.White.copy(alpha = 0.35f),
            1f to NeoInk.copy(alpha = 0.07f),
        )
    }
    return this
        .clip(shape)
        .background(fill)
        .drawWithCache {
            val sheen = Brush.radialGradient(
                listOf(Color.White.copy(alpha = 0.55f), Color.Transparent),
                center = Offset(size.width * 0.12f, 0f),
                radius = size.maxDimension * 0.7f,
            )
            onDrawBehind { drawRect(sheen) }
        }
        .then(if (tint != Color.Unspecified) Modifier.background(tint) else Modifier)
        .border(BorderStroke(edgeWidth.coerceAtLeast(1.dp), rim), shape)
}

/**
 * What floats over content (the demo guide). Neo-minimal: a plain solid surface. No blur, so
 * nothing behind it has to be recorded and re-processed on every frame.
 */
@Composable
fun Modifier.frosted(shape: Shape, edgeWidth: Dp = 0.8.dp): Modifier {
    val app = LocalAppColors.current
    return this
        .clip(shape)
        .background(app.glassTint)
        .then(if (app.glassEdge.alpha > 0f) Modifier.border(BorderStroke(edgeWidth, app.glassEdge), shape) else Modifier)
}

/** How much room the floating tab bar takes at the bottom, so lists can scroll under it. */
val LocalBottomInset = compositionLocalOf { 0.dp }


