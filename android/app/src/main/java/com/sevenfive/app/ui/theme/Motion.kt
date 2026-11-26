package com.sevenfive.app.ui.theme

import androidx.compose.animation.core.Spring
import androidx.compose.animation.core.animateFloatAsState
import androidx.compose.animation.core.spring
import androidx.compose.foundation.clickable
import androidx.compose.foundation.interaction.MutableInteractionSource
import androidx.compose.foundation.interaction.collectIsPressedAsState
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.remember
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.graphicsLayer
import androidx.compose.ui.hapticfeedback.HapticFeedbackType
import androidx.compose.ui.platform.LocalHapticFeedback
import androidx.compose.ui.semantics.Role
import androidx.compose.ui.unit.Dp
import androidx.compose.ui.unit.IntOffset

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
}

/**
 * Tappable the iOS way: no ripple; the element dips a little while pressed and springs back,
 * with an optional light haptic tick.
 */
@Composable
fun Modifier.pressable(
    enabled: Boolean = true,
    scaleTo: Float = 0.97f,
    haptic: Boolean = false,
    role: Role = Role.Button,
    onClick: () -> Unit,
): Modifier {
    val source = remember { MutableInteractionSource() }
    val pressed by source.collectIsPressedAsState()
    val scale by animateFloatAsState(if (pressed && enabled) scaleTo else 1f, Motion.press, label = "press")
    val haptics = LocalHapticFeedback.current
    return this
        .graphicsLayer {
            scaleX = scale
            scaleY = scale
        }
        .clickable(interactionSource = source, indication = null, enabled = enabled, role = role) {
            if (haptic) haptics.performHapticFeedback(HapticFeedbackType.TextHandleMove)
            onClick()
        }
}
