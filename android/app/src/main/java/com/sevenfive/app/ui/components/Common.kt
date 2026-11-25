package com.sevenfive.app.ui.components

import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.outlined.Assignment
import androidx.compose.material.icons.outlined.Campaign
import androidx.compose.material.icons.outlined.CloudOff
import androidx.compose.material.icons.outlined.Description
import androidx.compose.material.icons.outlined.Event
import androidx.compose.material.icons.outlined.Quiz
import androidx.compose.material3.Card
import androidx.compose.material3.CardDefaults
import androidx.compose.material3.Icon
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.vector.ImageVector
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.dp
import com.sevenfive.app.util.Time
import java.time.Instant

data class KindStyle(val label: String, val icon: ImageVector)

fun kindStyle(kind: String): KindStyle = when (kind) {
    "deadline" -> KindStyle("Deadline", Icons.AutoMirrored.Outlined.Assignment)
    "exam" -> KindStyle("Exam", Icons.Outlined.Quiz)
    "material" -> KindStyle("Material", Icons.Outlined.Description)
    "event" -> KindStyle("Event", Icons.Outlined.Event)
    "notice" -> KindStyle("Notice", Icons.Outlined.Campaign)
    else -> KindStyle(kind.replaceFirstChar { it.uppercase() }.ifBlank { "Item" }, Icons.Outlined.Description)
}

@Composable
fun KindChip(kind: String, modifier: Modifier = Modifier) {
    val style = kindStyle(kind)
    val tint = when (kind) {
        "exam" -> MaterialTheme.colorScheme.error
        "deadline" -> MaterialTheme.colorScheme.primary
        else -> MaterialTheme.colorScheme.tertiary
    }
    Row(
        modifier
            .background(tint.copy(alpha = 0.12f), RoundedCornerShape(50))
            .padding(horizontal = 8.dp, vertical = 3.dp),
        verticalAlignment = Alignment.CenterVertically,
    ) {
        Icon(style.icon, contentDescription = null, tint = tint, modifier = Modifier.size(14.dp))
        Spacer(Modifier.width(4.dp))
        Text(style.label, style = MaterialTheme.typography.labelMedium, color = tint)
    }
}

/** What decided the card (bot, classroom, jev, jev+llm, llm). Small: judges like seeing it. */
@Composable
fun RouteBadge(route: String?, modifier: Modifier = Modifier) {
    if (route.isNullOrBlank()) return
    Text(
        "via $route",
        modifier = modifier
            .background(MaterialTheme.colorScheme.surfaceVariant, RoundedCornerShape(4.dp))
            .padding(horizontal = 5.dp, vertical = 1.dp),
        style = MaterialTheme.typography.labelSmall,
        fontFamily = FontFamily.Monospace,
        color = MaterialTheme.colorScheme.onSurfaceVariant,
    )
}

@Composable
fun SectionHeader(text: String, modifier: Modifier = Modifier, trailing: @Composable (() -> Unit)? = null) {
    Row(
        modifier.fillMaxWidth().padding(top = 8.dp, bottom = 4.dp),
        verticalAlignment = Alignment.CenterVertically,
    ) {
        Text(
            text.uppercase(),
            style = MaterialTheme.typography.labelLarge,
            fontWeight = FontWeight.SemiBold,
            color = MaterialTheme.colorScheme.onSurfaceVariant,
            modifier = Modifier.weight(1f),
        )
        trailing?.invoke()
    }
}

@Composable
fun AppCard(modifier: Modifier = Modifier, muted: Boolean = false, content: @Composable () -> Unit) {
    Card(
        modifier = modifier.fillMaxWidth(),
        shape = RoundedCornerShape(16.dp),
        colors = CardDefaults.cardColors(
            containerColor = if (muted) MaterialTheme.colorScheme.surfaceContainer
            else MaterialTheme.colorScheme.surfaceContainerLowest,
        ),
        border = androidx.compose.foundation.BorderStroke(1.dp, MaterialTheme.colorScheme.outlineVariant),
    ) {
        Box(Modifier.padding(16.dp)) { content() }
    }
}

@Composable
fun EmptyState(icon: ImageVector, title: String, body: String? = null, modifier: Modifier = Modifier) {
    Column(
        modifier.fillMaxWidth().padding(vertical = 48.dp, horizontal = 24.dp),
        horizontalAlignment = Alignment.CenterHorizontally,
        verticalArrangement = Arrangement.spacedBy(8.dp),
    ) {
        Icon(icon, contentDescription = null, modifier = Modifier.size(40.dp), tint = MaterialTheme.colorScheme.outline)
        Text(title, style = MaterialTheme.typography.titleMedium, textAlign = TextAlign.Center)
        if (body != null) {
            Text(
                body,
                style = MaterialTheme.typography.bodyMedium,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
                textAlign = TextAlign.Center,
            )
        }
    }
}

/** The last good cards stay on screen; this says the server is out of reach and since when. */
@Composable
fun OfflineBanner(error: String?, updatedAt: Instant?, onSettings: () -> Unit, searching: Boolean = false) {
    if (error == null) return
    Surface(
        color = MaterialTheme.colorScheme.errorContainer,
        contentColor = MaterialTheme.colorScheme.onErrorContainer,
        modifier = Modifier.fillMaxWidth(),
    ) {
        Row(Modifier.padding(start = 16.dp, end = 4.dp, top = 4.dp, bottom = 4.dp), verticalAlignment = Alignment.CenterVertically) {
            Icon(Icons.Outlined.CloudOff, contentDescription = null, modifier = Modifier.size(18.dp))
            Spacer(Modifier.width(8.dp))
            Column(Modifier.weight(1f)) {
                Text(
                    if (searching) "Looking for the laptop on this network…" else error,
                    style = MaterialTheme.typography.bodySmall,
                    fontWeight = FontWeight.Medium,
                )
                if (updatedAt != null) {
                    Text("Showing data from ${Time.ago(updatedAt)}", style = MaterialTheme.typography.labelSmall)
                }
            }
            TextButton(onClick = onSettings) { Text("Server") }
        }
    }
}

val ScreenPadding = PaddingValues(start = 16.dp, end = 16.dp, top = 8.dp, bottom = 24.dp)

@Composable
fun Dot(color: Color, modifier: Modifier = Modifier) {
    Box(modifier.size(8.dp).background(color, RoundedCornerShape(50)))
}
