package com.sevenfive.app.ui.components

import androidx.compose.animation.core.Animatable
import androidx.compose.animation.core.FastOutSlowInEasing
import androidx.compose.animation.core.LinearEasing
import androidx.compose.animation.core.LinearOutSlowInEasing
import androidx.compose.animation.core.animateFloat
import androidx.compose.animation.core.tween
import androidx.compose.foundation.Canvas
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.navigationBarsPadding
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.remember
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.StrokeCap
import androidx.compose.ui.graphics.drawscope.Stroke
import androidx.compose.ui.graphics.graphicsLayer
import androidx.compose.ui.platform.LocalConfiguration
import androidx.compose.ui.semantics.clearAndSetSemantics
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.text.SpanStyle
import androidx.compose.ui.text.buildAnnotatedString
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.withStyle
import androidx.compose.ui.unit.dp
import com.sevenfive.app.ui.theme.LocalAppColors
import com.sevenfive.app.ui.theme.NeoGround
import com.sevenfive.app.ui.theme.NeoInk
import com.sevenfive.app.ui.theme.Orange

/** The whole opening sequence, start to finish; the app opens right after it. */
const val OPENING_SEQUENCE_MILLIS = 3_000

private const val RING_MS = 900f
private const val WORDS_AT = 380f
private const val WORDS_MS = 520f
private const val LETTERS_AT = 1_000f
private const val LETTER_STEP = 80f
private const val LETTER_MS = 240f
private const val SENTENCE = "Your semester, sorted."
private const val ORANGE_FROM = 15 // "sorted." is the orange part
/** "sorted." swipes in from the right edge once the letters before it are in. */
private const val SORTED_AT = 2_200f
private const val SORTED_MS = 650f

/** 0 before [start], 1 after [start] + [length], eased in between. */
private fun phase(t: Float, start: Float, length: Float): Float =
    FastOutSlowInEasing.transform(((t - start) / length).coerceIn(0f, 1f))

/**
 * The opening screen, neo-minimal: the brand's ring draws itself in orange, the wordmark slides in
 * from the left, "Your semester," arrives left to right one letter at a time, and "sorted.", in
 * orange, swipes in from the right edge of the screen. The whole
 * sequence takes [OPENING_SEQUENCE_MILLIS]; [onFinished] is called the moment it ends.
 */
@Composable
fun OpeningScreen(modifier: Modifier = Modifier, onFinished: () -> Unit = {}) {
    val clock = remember { Animatable(0f) }
    LaunchedEffect(Unit) {
        clock.animateTo(OPENING_SEQUENCE_MILLIS.toFloat(), tween(OPENING_SEQUENCE_MILLIS, easing = LinearEasing))
        onFinished()
    }
    // The clock is read only inside drawing and layer blocks, never while composing: the 3 s
    // sequence redraws, it never rebuilds the screen frame by frame.
    val app = LocalAppColors.current
    Box(
        modifier
            .fillMaxSize()
            .background(NeoGround),
    ) {
        Column(Modifier.align(Alignment.CenterStart).padding(horizontal = 32.dp)) {
            Canvas(Modifier.size(64.dp)) {
                val stroke = 7.dp.toPx()
                val inset = stroke / 2
                // The mark: an open ring, three quarters round, starting at the top.
                drawArc(
                    color = Orange,
                    startAngle = -90f,
                    sweepAngle = 270f * phase(clock.value, 0f, RING_MS),
                    useCenter = false,
                    topLeft = androidx.compose.ui.geometry.Offset(inset, inset),
                    size = androidx.compose.ui.geometry.Size(size.width - stroke, size.height - stroke),
                    style = Stroke(width = stroke, cap = StrokeCap.Round),
                )
            }
            Text(
                buildAnnotatedString {
                    append("7even")
                    withStyle(SpanStyle(color = Orange)) { append("5") }
                    append("ive")
                },
                style = MaterialTheme.typography.displaySmall,
                color = NeoInk,
                modifier = Modifier
                    .padding(top = 28.dp)
                    .graphicsLayer {
                        val words = phase(clock.value, WORDS_AT, WORDS_MS)
                        alpha = words
                        translationX = -(1f - words) * 28.dp.toPx()
                    },
            )
            // Left to right, one letter at a time; then "sorted." swipes in from the right edge
            // of the screen. Read out once, as the whole sentence.
            val screenWidth = LocalConfiguration.current.screenWidthDp.dp
            Row(
                Modifier
                    .padding(top = 8.dp)
                    .clearAndSetSemantics { contentDescription = SENTENCE },
            ) {
                SENTENCE.substring(0, ORANGE_FROM).forEachIndexed { i, ch ->
                    Text(
                        ch.toString(),
                        style = MaterialTheme.typography.titleLarge,
                        color = app.secondaryLabel,
                        modifier = Modifier.graphicsLayer {
                            val a = phase(clock.value, LETTERS_AT + i * LETTER_STEP, LETTER_MS)
                            alpha = a
                            translationX = -(1f - a) * 12.dp.toPx()
                        },
                    )
                }
                Text(
                    SENTENCE.substring(ORANGE_FROM),
                    style = MaterialTheme.typography.titleLarge,
                    fontWeight = FontWeight.SemiBold,
                    // A deeper orange than the ring, so the word stays readable on the light ground.
                    color = Color(0xFFE0670A),
                    modifier = Modifier.graphicsLayer {
                        val t = clock.value
                        val swipe = LinearOutSlowInEasing.transform(((t - SORTED_AT) / SORTED_MS).coerceIn(0f, 1f))
                        alpha = if (t < SORTED_AT) 0f else 1f
                        translationX = (1f - swipe) * screenWidth.toPx()
                    },
                )
            }
        }
        Text(
            "Deadlines · attendance · college mail",
            style = MaterialTheme.typography.labelSmall,
            color = app.secondaryLabel,
            modifier = Modifier
                .align(Alignment.BottomStart)
                .navigationBarsPadding()
                .padding(start = 32.dp, bottom = 28.dp)
                .graphicsLayer { alpha = phase(clock.value, WORDS_AT, WORDS_MS) },
        )
    }
}

/** The brand's open orange ring. [spinning] turns it slowly: the app's one loading mark. */
@Composable
fun BrandRing(modifier: Modifier = Modifier, size: androidx.compose.ui.unit.Dp = 36.dp, spinning: Boolean = false) {
    val angle: androidx.compose.runtime.State<Float>? = if (spinning) {
        val turn = androidx.compose.animation.core.rememberInfiniteTransition(label = "ring")
        turn.animateFloat(
            initialValue = 0f,
            targetValue = 360f,
            animationSpec = androidx.compose.animation.core.infiniteRepeatable(tween(1100, easing = LinearEasing)),
            label = "ring turn",
        )
    } else null
    Canvas(
        modifier
            .size(size)
            .graphicsLayer { rotationZ = angle?.value ?: 0f }
            .semantics { if (spinning) contentDescription = "Loading" },
    ) {
        val stroke = this.size.minDimension * 0.11f
        val inset = stroke / 2
        drawArc(
            color = Orange,
            startAngle = -90f,
            sweepAngle = 270f,
            useCenter = false,
            topLeft = androidx.compose.ui.geometry.Offset(inset, inset),
            size = androidx.compose.ui.geometry.Size(this.size.width - stroke, this.size.height - stroke),
            style = Stroke(width = stroke, cap = StrokeCap.Round),
        )
    }
}
