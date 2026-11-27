package com.sevenfive.app.ui.components

import androidx.compose.animation.core.LinearEasing
import androidx.compose.animation.core.RepeatMode
import androidx.compose.animation.core.animateFloat
import androidx.compose.animation.core.infiniteRepeatable
import androidx.compose.animation.core.rememberInfiniteTransition
import androidx.compose.animation.core.tween
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.MaterialTheme
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.draw.drawWithContent
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.Shape
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.unit.Dp
import androidx.compose.ui.unit.dp
import com.sevenfive.app.ui.theme.LocalAppColors

/**
 * Skeleton loading: grey shapes where the content will be, with a soft light passing over them.
 * Used instead of a spinner while the first cards arrive, so the screen already has its shape.
 */
@Composable
fun Modifier.shimmer(shape: Shape = RoundedCornerShape(10.dp)): Modifier {
    val base = LocalAppColors.current.glassFill
    val transition = rememberInfiniteTransition(label = "skeleton")
    val x by transition.animateFloat(
        initialValue = -1f,
        targetValue = 2f,
        animationSpec = infiniteRepeatable(tween(1300, easing = LinearEasing), RepeatMode.Restart),
        label = "skeleton light",
    )
    return this
        .clip(shape)
        .background(base)
        .drawWithContent {
            drawContent()
            val w = size.width
            val band = w * 0.6f
            val start = x * w - band
            drawRect(
                Brush.linearGradient(
                    listOf(Color.Transparent, Color.White.copy(alpha = 0.55f), Color.Transparent),
                    start = Offset(start, 0f),
                    end = Offset(start + band, size.height),
                ),
            )
        }
}

@Composable
private fun Bone(width: Dp? = null, height: Dp, modifier: Modifier = Modifier, shape: Shape = RoundedCornerShape(8.dp)) {
    Box(
        (if (width != null) modifier.width(width) else modifier.fillMaxWidth())
            .height(height)
            .shimmer(shape),
    )
}

/** The shape of a tab while it loads: a hero, a line, then a few rows. */
@Composable
fun SkeletonScreen(padding: PaddingValues, modifier: Modifier = Modifier) {
    Column(
        modifier
            .fillMaxWidth()
            .padding(padding)
            .padding(horizontal = 4.dp)
            .semantics { contentDescription = "Loading" },
    ) {
        Spacer(Modifier.height(14.dp))
        Bone(width = 64.dp, height = 10.dp)
        Spacer(Modifier.height(16.dp))
        Bone(width = 220.dp, height = 52.dp, shape = RoundedCornerShape(12.dp))
        Spacer(Modifier.height(8.dp))
        Bone(width = 150.dp, height = 52.dp, shape = RoundedCornerShape(12.dp))
        Spacer(Modifier.height(20.dp))
        Bone(width = 240.dp, height = 18.dp)
        Spacer(Modifier.height(8.dp))
        Bone(width = 170.dp, height = 14.dp)
        Spacer(Modifier.height(30.dp))
        Bone(height = 52.dp, shape = CircleShape)
        Spacer(Modifier.height(26.dp))
        Column(verticalArrangement = Arrangement.spacedBy(12.dp)) {
            repeat(4) { SkeletonRow() }
        }
    }
}

@Composable
private fun SkeletonRow() {
    Row(
        Modifier
            .fillMaxWidth()
            .clip(MaterialTheme.shapes.large)
            .background(LocalAppColors.current.glassFill.copy(alpha = 0.45f))
            .padding(18.dp),
        verticalAlignment = Alignment.CenterVertically,
    ) {
        Box(Modifier.size(40.dp).shimmer(CircleShape))
        Spacer(Modifier.width(14.dp))
        Column(Modifier.weight(1f)) {
            Bone(height = 14.dp)
            Spacer(Modifier.height(8.dp))
            Bone(width = 120.dp, height = 12.dp)
        }
    }
}
