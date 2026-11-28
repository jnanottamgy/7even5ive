package com.sevenfive.app.ui.components

import androidx.compose.animation.AnimatedVisibility
import androidx.compose.animation.expandVertically
import androidx.compose.animation.fadeIn
import androidx.compose.animation.fadeOut
import androidx.compose.animation.shrinkVertically
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.outlined.Assignment
import androidx.compose.material.icons.outlined.Campaign
import androidx.compose.material.icons.outlined.CloudOff
import androidx.compose.material.icons.outlined.Description
import androidx.compose.material.icons.outlined.Event
import androidx.compose.material.icons.outlined.Quiz
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.Icon
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.alpha
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.vector.ImageVector
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.Dp
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.sevenfive.app.ui.theme.LocalAppColors
import com.sevenfive.app.ui.theme.glassSurface
import com.sevenfive.app.ui.theme.pressable
import com.sevenfive.app.util.Time
import java.time.Instant

data class KindStyle(val label: String, val icon: ImageVector)

/**
 * Keys for a lazy list that never repeat (a repeated key closes the app): each item's [key], and
 * for a second item with the same one "CS301#2", "CS301#3"... Unlike the plain index, a key stays
 * with its item when the list is re-sorted, so items still animate to their new place.
 */
fun <T> uniqueKeys(items: List<T>, key: (T) -> String): List<String> {
    val seen = HashMap<String, Int>()
    return items.map { item ->
        val k = key(item)
        val n = (seen[k] ?: 0) + 1
        seen[k] = n
        if (n == 1) k else "$k#$n"
    }
}

fun kindStyle(kind: String): KindStyle = when (kind) {
    "deadline" -> KindStyle("Deadline", Icons.AutoMirrored.Outlined.Assignment)
    "exam" -> KindStyle("Exam", Icons.Outlined.Quiz)
    "material" -> KindStyle("Material", Icons.Outlined.Description)
    "event" -> KindStyle("Event", Icons.Outlined.Event)
    "notice" -> KindStyle("Notice", Icons.Outlined.Campaign)
    else -> KindStyle(kind.replaceFirstChar { it.uppercase() }.ifBlank { "Item" }, Icons.Outlined.Description)
}

/** One colour per kind of card, iOS system colours. */
@Composable
fun kindColor(kind: String): Color {
    val app = LocalAppColors.current
    return when (kind) {
        "deadline" -> app.deadline
        "exam" -> app.exam
        "material" -> app.material
        "event" -> app.event
        "notice" -> app.notice
        else -> MaterialTheme.colorScheme.primary
    }
}

/** A rounded colour tile with a white glyph, like iOS Settings icons. */
@Composable
fun IconTile(icon: ImageVector, color: Color, modifier: Modifier = Modifier, size: Dp = 40.dp) {
    Box(
        modifier
            .size(size)
            .clip(CircleShape)
            .background(color.copy(alpha = 0.10f)),
        contentAlignment = Alignment.Center,
    ) {
        // Neo-minimal: a quiet round tile, the glyph in the kind's own ink.
        Icon(icon, contentDescription = null, tint = color, modifier = Modifier.size(size * 0.48f))
    }
}

@Composable
fun KindChip(kind: String, modifier: Modifier = Modifier) {
    val style = kindStyle(kind)
    val tint = kindColor(kind)
    Text(
        style.label,
        modifier = modifier
            .clip(CircleShape)
            .background(tint.copy(alpha = 0.14f))
            .padding(horizontal = 8.dp, vertical = 2.dp),
        style = MaterialTheme.typography.labelSmall,
        color = tint,
    )
}

/** What decided the card (bot, classroom, jev, jev+llm, llm). Quiet: judges like seeing it. */
@Composable
fun RouteBadge(route: String?, modifier: Modifier = Modifier) {
    if (route.isNullOrBlank()) return
    Text(
        "via $route",
        modifier = modifier,
        style = MaterialTheme.typography.labelSmall,
        fontWeight = FontWeight.Medium,
        color = LocalAppColors.current.tertiaryLabel,
    )
}

/** An iOS grouped-list header: small, uppercase, secondary. */
@Composable
fun SectionHeader(text: String, modifier: Modifier = Modifier, trailing: @Composable (() -> Unit)? = null) {
    Row(
        modifier.fillMaxWidth().padding(top = 26.dp, bottom = 4.dp),
        verticalAlignment = Alignment.CenterVertically,
    ) {
        Text(
            text.uppercase(),
            style = MaterialTheme.typography.labelSmall,
            letterSpacing = 1.5.sp,
            color = LocalAppColors.current.secondaryLabel,
            modifier = Modifier.weight(1f),
        )
        trailing?.invoke()
    }
}

/** A glass card. [muted] is for things that are done or need no action. */
@Composable
fun AppCard(modifier: Modifier = Modifier, muted: Boolean = false, content: @Composable () -> Unit) {
    Box(
        modifier
            .fillMaxWidth()
            .glassSurface()
            .padding(18.dp)
            .then(if (muted) Modifier.alpha(0.72f) else Modifier),
    ) { content() }
}

/** The main action: a filled capsule in the brand gradient. */
@Composable
fun PrimaryPill(
    text: String,
    onClick: () -> Unit,
    modifier: Modifier = Modifier,
    enabled: Boolean = true,
    busy: Boolean = false,
    icon: ImageVector? = null,
) {
    // The one accent: a flat orange capsule with ink text.
    val accent = com.sevenfive.app.ui.theme.Orange
    val ink = com.sevenfive.app.ui.theme.NeoInk
    Row(
        modifier
            .pressable(enabled = enabled && !busy, haptic = true, onClick = onClick)
            .clip(CircleShape)
            .background(accent.copy(alpha = if (enabled) 1f else 0.4f))
            .padding(horizontal = 20.dp, vertical = 12.dp),
        verticalAlignment = Alignment.CenterVertically,
        horizontalArrangement = Arrangement.Center,
    ) {
        if (busy) {
            CircularProgressIndicator(Modifier.size(16.dp), strokeWidth = 2.dp, color = ink)
        } else {
            if (icon != null) {
                Icon(icon, contentDescription = null, tint = ink, modifier = Modifier.size(18.dp))
                Spacer(Modifier.width(6.dp))
            }
            Text(text, style = MaterialTheme.typography.labelLarge, color = ink)
        }
    }
}

/** A quieter action: a glass capsule with tinted text. */
@Composable
fun GlassPill(
    text: String,
    onClick: () -> Unit,
    modifier: Modifier = Modifier,
    enabled: Boolean = true,
    busy: Boolean = false,
    icon: ImageVector? = null,
    tint: Color = MaterialTheme.colorScheme.primary,
) {
    Row(
        modifier
            .pressable(enabled = enabled && !busy, onClick = onClick)
            .glassSurface(shape = CircleShape, strong = true)
            .padding(horizontal = 16.dp, vertical = 10.dp)
            .alpha(if (enabled) 1f else 0.45f),
        verticalAlignment = Alignment.CenterVertically,
        horizontalArrangement = Arrangement.Center,
    ) {
        if (busy) {
            CircularProgressIndicator(Modifier.size(14.dp), strokeWidth = 2.dp, color = tint)
        } else {
            if (icon != null) {
                Icon(icon, contentDescription = null, tint = tint, modifier = Modifier.size(16.dp))
                Spacer(Modifier.width(5.dp))
            }
            Text(text, style = MaterialTheme.typography.labelMedium, fontWeight = FontWeight.SemiBold, color = tint)
        }
    }
}

@Composable
fun EmptyState(icon: ImageVector, title: String, body: String? = null, modifier: Modifier = Modifier) {
    val app = LocalAppColors.current
    Column(
        modifier.fillMaxWidth().padding(vertical = 48.dp, horizontal = 28.dp),
        horizontalAlignment = Alignment.CenterHorizontally,
        verticalArrangement = Arrangement.spacedBy(10.dp),
    ) {
        Box(Modifier.size(72.dp).glassSurface(shape = CircleShape), contentAlignment = Alignment.Center) {
            Icon(icon, contentDescription = null, modifier = Modifier.size(32.dp), tint = app.secondaryLabel)
        }
        Text(title, style = MaterialTheme.typography.titleMedium, textAlign = TextAlign.Center)
        if (body != null) {
            Text(body, style = MaterialTheme.typography.bodyMedium, color = app.secondaryLabel, textAlign = TextAlign.Center)
        }
    }
}

/** The last good cards stay on screen; this says the server is out of reach and since when. */
@Composable
fun OfflineBanner(error: String?, updatedAt: Instant?, onSettings: () -> Unit, searching: Boolean = false) {
    AnimatedVisibility(
        visible = error != null,
        enter = fadeIn() + expandVertically(),
        exit = fadeOut() + shrinkVertically(),
    ) {
        val red = MaterialTheme.colorScheme.error
        Row(
            Modifier
                .fillMaxWidth()
                .padding(horizontal = 16.dp, vertical = 6.dp)
                .glassSurface(shape = RoundedCornerShape(16.dp), strong = true, tint = red.copy(alpha = 0.10f))
                .padding(start = 12.dp, end = 4.dp, top = 6.dp, bottom = 6.dp),
            verticalAlignment = Alignment.CenterVertically,
        ) {
            Icon(Icons.Outlined.CloudOff, contentDescription = null, tint = red, modifier = Modifier.size(18.dp))
            Spacer(Modifier.width(10.dp))
            Column(Modifier.weight(1f)) {
                Text(
                    if (searching) "Looking for the laptop on this network…" else error.orEmpty(),
                    style = MaterialTheme.typography.labelMedium,
                    color = MaterialTheme.colorScheme.onSurface,
                )
                if (updatedAt != null) {
                    Text(
                        "Showing data from ${Time.ago(updatedAt)}",
                        style = MaterialTheme.typography.labelSmall,
                        color = LocalAppColors.current.secondaryLabel,
                    )
                }
            }
            Text(
                "Server",
                style = MaterialTheme.typography.labelMedium,
                fontWeight = FontWeight.SemiBold,
                color = MaterialTheme.colorScheme.primary,
                modifier = Modifier.pressable(onClick = onSettings).padding(horizontal = 10.dp, vertical = 6.dp),
            )
        }
    }
}

@Composable
fun Dot(color: Color, modifier: Modifier = Modifier) {
    Box(modifier.size(8.dp).clip(CircleShape).background(color))
}

/** A thin rounded progress bar on a faint track. */
@Composable
fun SlimBar(fraction: Float, color: Color, modifier: Modifier = Modifier) {
    Box(
        modifier
            .fillMaxWidth()
            .height(4.dp)
            .clip(CircleShape)
            .background(LocalAppColors.current.hairline),
    ) {
        Box(
            Modifier
                .fillMaxWidth(fraction.coerceIn(0f, 1f))
                .height(4.dp)
                .clip(CircleShape)
                .background(color),
        )
    }
}
