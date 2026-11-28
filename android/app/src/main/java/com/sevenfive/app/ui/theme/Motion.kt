package com.sevenfive.app.ui.theme

import androidx.compose.animation.core.FastOutSlowInEasing
import androidx.compose.animation.core.LinearOutSlowInEasing
import androidx.compose.animation.core.Spring
import androidx.compose.animation.core.spring
import androidx.compose.animation.core.tween
import androidx.compose.foundation.clickable
import androidx.compose.runtime.Composable
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.drawscope.scale
import androidx.compose.ui.hapticfeedback.HapticFeedbackType
import androidx.compose.ui.platform.LocalHapticFeedback
import androidx.compose.ui.semantics.Role
import androidx.compose.ui.unit.Dp
import androidx.compose.ui.unit.IntOffset
import kotlinx.coroutines.launch

/** Springs, not durations: motion that settles like iOS, interruptible at any point. */
object Motion {
    /** A press: quick dip, slightly bouncy return. */
    val press = spring<Float>(dampingRatio = 0.6f, stiffness = Spring.StiffnessMedium)

    /** Things gliding into place (the tab bar's selection). */
    val glide = spring<Dp>(dampingRatio = 0.82f, stiffness = Spring.StiffnessMediumLow)

    /** Screens and content: no overshoot, unhurried. */
    val screen = spring<IntOffset>(dampingRatio = Spring.DampingRatioNoBouncy, stiffness = Spring.StiffnessMediumLow)
    val fade = spring<Float>(dampingRatio = Spring.DampingRatioNoBouncy, stiffness = Spring.StiffnessMediumLow)
    val item = spring<IntOffset>(dampingRatio = 0.86f, stiffness = Spring.StiffnessMediumLow)

    // Between screens, "fade through": the one being left is gone before the one arriving comes
    // in, so no screen ever shows through another; the one backdrop under both stays still.
    private const val LEAVE_MS = 90
    private const val ARRIVE_MS = 210

    /** The screen being left: most of it gone on the first frames after the tap, so the tap
     * answers at once, and all of it by 90 ms. */
    val leave = tween<Float>(LEAVE_MS, easing = LinearOutSlowInEasing)

    /** The screen arriving: only once the last has gone, settling as it comes. */
    val arrive = tween<Float>(ARRIVE_MS, delayMillis = LEAVE_MS, easing = LinearOutSlowInEasing)

    /** The little way a screen travels while it fades (where the motion has a direction). */
    val travel = tween<IntOffset>(LEAVE_MS + ARRIVE_MS, easing = FastOutSlowInEasing)

    /** About 30 dp on a phone: a hint of direction rather than a slide. */
    fun nudge(width: Int) = width / 12
}

/**
 * Tappable the iOS way: no ripple; the element dips a little while pressed and springs back,
 * with an optional light haptic tick.
 *
 * The dip is drawn, never composed: a press costs no work on the screen around it, and nothing
 * is made for it until the first touch. A quick tap still shows it: inside a scrolling list
 * Android only reports the press as the finger lifts, so the dip is held for a moment.
 */
@Composable
fun Modifier.pressable(
    enabled: Boolean = true,
    scaleTo: Float = 0.97f,
    haptic: Boolean = false,
    role: Role = Role.Button,
    onClick: () -> Unit,
): Modifier {
    val haptics = LocalHapticFeedback.current
    return this.clickable(interactionSource = null, indication = Dip(scaleTo), enabled = enabled, role = role) {
        if (haptic) haptics.performHapticFeedback(HapticFeedbackType.TextHandleMove)
        onClick()
    }
}

/** The shortest dip a tap shows, however quick the tap. */
private const val MIN_DIP_MILLIS = 90L

private class Dip(private val to: Float) : androidx.compose.foundation.IndicationNodeFactory {
    override fun create(interactionSource: androidx.compose.foundation.interaction.InteractionSource):
        androidx.compose.ui.node.DelegatableNode = DipNode(interactionSource, to)

    override fun equals(other: Any?) = other is Dip && other.to == to
    override fun hashCode() = to.hashCode()
}

private class DipNode(
    private val source: androidx.compose.foundation.interaction.InteractionSource,
    private val to: Float,
) : Modifier.Node(), androidx.compose.ui.node.DrawModifierNode {
    private val scale = androidx.compose.animation.core.Animatable(1f)

    override fun onAttach() {
        coroutineScope.launch {
            var pressedAt = 0L
            var release: kotlinx.coroutines.Job? = null
            source.interactions.collect { interaction ->
                when (interaction) {
                    is androidx.compose.foundation.interaction.PressInteraction.Press -> {
                        release?.cancel()
                        pressedAt = System.nanoTime()
                        launch { scale.animateTo(to, Motion.press) }
                    }
                    is androidx.compose.foundation.interaction.PressInteraction.Release,
                    is androidx.compose.foundation.interaction.PressInteraction.Cancel -> {
                        val held = (System.nanoTime() - pressedAt) / 1_000_000
                        release = launch {
                            if (held < MIN_DIP_MILLIS) kotlinx.coroutines.delay(MIN_DIP_MILLIS - held)
                            scale.animateTo(1f, Motion.press)
                        }
                    }
                }
            }
        }
    }

    // Read while drawing: each step of the dip redraws this element only.
    override fun androidx.compose.ui.graphics.drawscope.ContentDrawScope.draw() {
        val s = scale.value
        if (s == 1f) drawContent()
        else scale(s) { this@draw.drawContent() }
    }
}
