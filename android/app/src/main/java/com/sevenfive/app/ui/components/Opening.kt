package com.sevenfive.app.ui.components

import androidx.compose.animation.core.Animatable
import androidx.compose.animation.core.FastOutSlowInEasing
import androidx.compose.animation.core.tween
import androidx.compose.foundation.Canvas
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
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
import androidx.compose.ui.graphics.StrokeCap
import androidx.compose.ui.graphics.drawscope.Stroke
import androidx.compose.ui.graphics.graphicsLayer
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.text.SpanStyle
import androidx.compose.ui.text.buildAnnotatedString
import androidx.compose.ui.text.withStyle
import androidx.compose.ui.unit.dp
import com.sevenfive.app.ui.theme.LocalAppColors
import com.sevenfive.app.ui.theme.NeoGround
import com.sevenfive.app.ui.theme.NeoInk
import com.sevenfive.app.ui.theme.Orange
import kotlinx.coroutines.launch

/**
 * The opening screen, neo-minimal: the brand's ring draws itself in orange, then the wordmark and
 * one line rise into place. It sits over the app while it starts and fades away on its own.
 */
@Composable
fun OpeningScreen(modifier: Modifier = Modifier) {
    val ring = remember { Animatable(0f) }
    val words = remember { Animatable(0f) }
    val line = remember { Animatable(0f) }
    LaunchedEffect(Unit) {
        launch { ring.animateTo(1f, tween(900, easing = FastOutSlowInEasing)) }
        launch { words.animateTo(1f, tween(520, delayMillis = 380, easing = FastOutSlowInEasing)) }
        launch { line.animateTo(1f, tween(520, delayMillis = 620, easing = FastOutSlowInEasing)) }
    }
    val app = LocalAppColors.current
    Box(
        modifier
            .fillMaxSize()
            .background(NeoGround)
            .semantics { contentDescription = "7even5ive is opening" },
    ) {
        Column(Modifier.align(Alignment.CenterStart).padding(horizontal = 32.dp)) {
            Canvas(Modifier.size(64.dp)) {
                val stroke = 7.dp.toPx()
                val inset = stroke / 2
                // The mark: an open ring, three quarters round, starting at the top.
                drawArc(
                    color = Orange,
                    startAngle = -90f,
                    sweepAngle = 270f * ring.value,
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
                        alpha = words.value
                        translationY = (1f - words.value) * 18.dp.toPx()
                    },
            )
            Text(
                "Your semester, sorted.",
                style = MaterialTheme.typography.titleLarge,
                color = app.secondaryLabel,
                modifier = Modifier
                    .padding(top = 6.dp)
                    .graphicsLayer {
                        alpha = line.value
                        translationY = (1f - line.value) * 14.dp.toPx()
                    },
            )
        }
        Text(
            "Deadlines · attendance · college mail",
            style = MaterialTheme.typography.labelSmall,
            color = app.secondaryLabel,
            modifier = Modifier
                .align(Alignment.BottomStart)
                .navigationBarsPadding()
                .padding(start = 32.dp, bottom = 28.dp)
                .graphicsLayer { alpha = line.value },
        )
    }
}
