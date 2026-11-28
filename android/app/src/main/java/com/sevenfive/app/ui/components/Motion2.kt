package com.sevenfive.app.ui.components

import androidx.compose.animation.AnimatedContent
import androidx.compose.animation.core.Animatable
import androidx.compose.animation.core.FastOutSlowInEasing
import androidx.compose.animation.core.tween
import androidx.compose.animation.fadeIn
import androidx.compose.animation.fadeOut
import androidx.compose.animation.slideInVertically
import androidx.compose.animation.slideOutVertically
import androidx.compose.animation.togetherWith
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableIntStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.graphicsLayer
import androidx.compose.ui.text.TextStyle
import kotlinx.coroutines.launch

/**
 * Switching segments: the new content slides in from the side it lies on (right for a segment
 * further along, left for one before) and fades up. The switcher itself stays put.
 */
@Composable
fun Modifier.segmentSlide(segment: Int): Modifier {
    var last by remember { mutableIntStateOf(segment) }
    val x = remember { Animatable(0f) }
    val alpha = remember { Animatable(1f) }
    LaunchedEffect(segment) {
        if (segment == last) return@LaunchedEffect
        val direction = if (segment > last) 1f else -1f
        last = segment
        x.snapTo(direction * 56f)
        alpha.snapTo(0f)
        launch { x.animateTo(0f, tween(280, easing = FastOutSlowInEasing)) }
        alpha.animateTo(1f, tween(220))
    }
    return this.graphicsLayer {
        translationX = x.value * density
        this.alpha = alpha.value
    }
}

/**
 * Text whose characters roll when they change, like a mechanical counter: the old digit slides
 * down and out, the new one drops in. Used for the live countdown; line breaks are kept.
 */
@Composable
fun RollingText(text: String, style: TextStyle, modifier: Modifier = Modifier) {
    Column(modifier) {
        text.split('\n').forEachIndexed { line, part ->
            Row {
                part.forEachIndexed { i, ch ->
                    // Keyed by position from the right, so the seconds keep their slot as the
                    // string shortens (hours running out).
                    androidx.compose.runtime.key(line, part.length - i) {
                        AnimatedContent(
                            targetState = ch,
                            transitionSpec = {
                                (slideInVertically(tween(260)) { -it / 2 } + fadeIn(tween(200))) togetherWith
                                    (slideOutVertically(tween(260)) { it / 2 } + fadeOut(tween(160)))
                            },
                            label = "roll",
                        ) { c -> Text(c.toString(), style = style) }
                    }
                }
            }
        }
    }
}
