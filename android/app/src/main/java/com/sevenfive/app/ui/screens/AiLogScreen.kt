package com.sevenfive.app.ui.screens

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.outlined.Block
import androidx.compose.material.icons.outlined.CheckCircle
import androidx.compose.material.icons.outlined.PanTool
import androidx.compose.material.icons.outlined.Shield
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.vector.ImageVector
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import com.sevenfive.app.data.AuditRow
import com.sevenfive.app.ui.AppViewModel
import com.sevenfive.app.ui.components.EmptyState
import com.sevenfive.app.ui.components.IconTile
import com.sevenfive.app.ui.components.PushScaffold
import com.sevenfive.app.ui.theme.LocalAppColors
import com.sevenfive.app.ui.theme.LocalStatusColors
import com.sevenfive.app.ui.theme.Motion
import com.sevenfive.app.ui.theme.glassSurface
import com.sevenfive.app.util.Time

/** Plain words for the gateway's tool names. */
fun toolLabel(tool: String): String = when (tool) {
    "due_this_week" -> "Read what's due this week"
    "attendance" -> "Read your attendance"
    "timetable" -> "Read your timetable"
    "marks" -> "Read your internal marks"
    "results" -> "Read your results"
    "materials" -> "Read your materials"
    "opportunities" -> "Read your inbox picks"
    "set_reminder" -> "Set a reminder"
    "list_reminders" -> "Read your reminders"
    "cancel_reminder" -> "Cancel a reminder"
    "add_to_calendar" -> "Add to Google Calendar"
    "approve" -> "Use an approval"
    "send_email" -> "Send an email"
    "submit_on_portal" -> "Submit on the portal"
    "*" -> "Unknown caller"
    else -> tool.replace('_', ' ').replaceFirstChar { it.uppercase() }
}

/** What the decision means, in the student's words. */
private fun reasonLabel(row: AuditRow): String = when {
    row.decision == "allow" && row.reason == "approved by student" -> "Ran after you tapped Approve"
    row.decision == "allow" -> "Allowed: only reads or touches your own data"
    row.decision == "ask" -> "Held until you tap Approve"
    row.reason == "policy" -> "Refused: this tool doesn't exist for AI here"
    row.reason == "unknown caller" -> "Refused: no valid token"
    else -> "Refused: ${row.reason ?: "against the rules"}"
}

/**
 * Every request an AI (or this app) made through the gateway, newest first: what it asked for,
 * and whether the gateway let it run, held it for a tap, or refused it. The rules live in the
 * gateway, so this is the proof that a prompt can't talk its way past them.
 */
@Composable
fun AiLogScreen(vm: AppViewModel, onBack: () -> Unit) {
    val state by vm.cards.collectAsStateWithLifecycle()
    val rows = state.cards?.audit.orEmpty()
    val status = LocalStatusColors.current
    val app = LocalAppColors.current

    PushScaffold("AI activity", onBack) { padding ->
        LazyColumn(contentPadding = padding, verticalArrangement = Arrangement.spacedBy(10.dp)) {
            item(key = "intro") {
                Text(
                    "Every request made through the gateway, by your AI over MCP or by this app. " +
                        "Rules live in the gateway, not in a prompt.",
                    style = MaterialTheme.typography.bodyLarge,
                    color = app.secondaryLabel,
                    modifier = Modifier.padding(horizontal = 4.dp, vertical = 2.dp),
                )
            }
            item(key = "counts") {
                Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(10.dp)) {
                    Count("${rows.count { it.decision == "allow" }}", "Allowed", status.safe, Modifier.weight(1f))
                    Count("${rows.count { it.decision == "ask" }}", "Held for you", status.atRisk, Modifier.weight(1f))
                    Count("${rows.count { it.decision == "deny" }}", "Refused", status.short, Modifier.weight(1f))
                }
            }
            if (rows.isEmpty()) {
                item(key = "empty") {
                    EmptyState(Icons.Outlined.Shield, "No requests yet",
                        "Ask something, or let your AI ask over MCP: each request shows up here.")
                }
            }
            items(rows, key = { it.id }) { row -> LogRow(row, Modifier.animateItem(placementSpec = Motion.item)) }
        }
    }
}

@Composable
private fun Count(value: String, label: String, color: Color, modifier: Modifier = Modifier) {
    Column(modifier.glassSurface(shape = MaterialTheme.shapes.medium).padding(12.dp)) {
        Text(value, style = MaterialTheme.typography.headlineSmall, fontWeight = FontWeight.Bold, color = color)
        Text(label, style = MaterialTheme.typography.labelMedium, color = LocalAppColors.current.secondaryLabel)
    }
}

@Composable
private fun LogRow(row: AuditRow, modifier: Modifier = Modifier) {
    val status = LocalStatusColors.current
    val (icon: ImageVector, color: Color) = when (row.decision) {
        "allow" -> Icons.Outlined.CheckCircle to status.safe
        "ask" -> Icons.Outlined.PanTool to status.atRisk
        else -> Icons.Outlined.Block to status.short
    }
    Row(
        modifier.fillMaxWidth().glassSurface(shape = MaterialTheme.shapes.medium).padding(12.dp),
        verticalAlignment = Alignment.CenterVertically,
    ) {
        IconTile(icon, color, size = 34.dp)
        Spacer(Modifier.width(12.dp))
        Column(Modifier.weight(1f)) {
            Text(toolLabel(row.tool), style = MaterialTheme.typography.bodyLarge, fontWeight = FontWeight.Medium)
            Text(reasonLabel(row), style = MaterialTheme.typography.bodySmall, color = LocalAppColors.current.secondaryLabel)
        }
        Time.parse(row.at)?.let {
            Text(Time.ago(it.toInstant()), style = MaterialTheme.typography.labelSmall,
                color = LocalAppColors.current.tertiaryLabel)
        }
    }
}
