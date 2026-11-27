package com.sevenfive.app.widget

import android.content.Context
import androidx.compose.runtime.Composable
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.glance.GlanceId
import androidx.glance.GlanceModifier
import androidx.glance.action.clickable
import androidx.glance.appwidget.GlanceAppWidget
import androidx.glance.appwidget.GlanceAppWidgetReceiver
import androidx.glance.action.actionStartActivity
import androidx.glance.appwidget.cornerRadius
import androidx.glance.appwidget.provideContent
import androidx.glance.appwidget.updateAll
import androidx.glance.background
import androidx.glance.layout.Alignment
import androidx.glance.layout.Column
import androidx.glance.layout.Row
import androidx.glance.layout.Spacer
import androidx.glance.layout.fillMaxSize
import androidx.glance.layout.fillMaxWidth
import androidx.glance.layout.height
import androidx.glance.layout.padding
import androidx.glance.layout.width
import androidx.glance.text.FontWeight
import androidx.glance.text.Text
import androidx.glance.text.TextStyle
import androidx.glance.unit.ColorProvider
import com.sevenfive.app.MainActivity
import com.sevenfive.app.SevenFiveApp
import com.sevenfive.app.data.Cards
import com.sevenfive.app.util.Time
import java.time.Duration
import java.time.Instant

private val Paper = Color(0xFFFBF8F3)
private val Ink = Color(0xFF111114)
private val Secondary = Color(0xFF6E6E73)
private val Orange = Color(0xFFF27A0C)
private val Red = Color(0xFFFF3B30)
private val Green = Color(0xFF34C759)
private val Amber = Color(0xFFFF9500)

/**
 * The home-screen widget: the next things due and the lowest attendance, from the last cards
 * the app saw (so it shows something with no network). Tapping it opens the app.
 */
class WeekWidget : GlanceAppWidget() {
    override suspend fun provideGlance(context: Context, id: GlanceId) {
        val cards = (context.applicationContext as SevenFiveApp).container.cards.cached()
        provideContent { Content(cards) }
    }

    @Composable
    private fun Content(cards: Cards?) {
        Column(
            GlanceModifier
                .fillMaxSize()
                .background(Paper)
                .cornerRadius(22.dp)
                .padding(14.dp)
                .clickable(actionStartActivity<MainActivity>()),
        ) {
            Row(GlanceModifier.fillMaxWidth(), verticalAlignment = Alignment.CenterVertically) {
                Text(
                    "This week",
                    style = TextStyle(color = ColorProvider(Ink), fontSize = 15.sp, fontWeight = FontWeight.Bold),
                    modifier = GlanceModifier.defaultWeight(),
                )
                Text(
                    "7even5ive",
                    style = TextStyle(color = ColorProvider(Orange), fontSize = 11.sp, fontWeight = FontWeight.Medium),
                )
            }
            Spacer(GlanceModifier.height(6.dp))
            if (cards == null) {
                Text(
                    "Open the app once to load your week.",
                    style = TextStyle(color = ColorProvider(Secondary), fontSize = 13.sp),
                )
                return@Column
            }
            val due = cards.dueThisWeek.take(3)
            if (due.isEmpty()) {
                Text("Nothing due in the next 7 days", style = TextStyle(color = ColorProvider(Secondary), fontSize = 13.sp))
            }
            due.forEach { item ->
                val at = Time.parse(item.dueAt)
                val urgent = at != null && at.toInstant().isBefore(Instant.now().plus(Duration.ofHours(24)))
                Row(GlanceModifier.fillMaxWidth().padding(vertical = 2.dp), verticalAlignment = Alignment.CenterVertically) {
                    Text(
                        item.title ?: "Untitled",
                        maxLines = 1,
                        style = TextStyle(color = ColorProvider(Ink), fontSize = 13.sp, fontWeight = FontWeight.Medium),
                        modifier = GlanceModifier.defaultWeight(),
                    )
                    Spacer(GlanceModifier.width(6.dp))
                    Text(
                        at?.let { Time.until(it) } ?: "",
                        style = TextStyle(
                            color = ColorProvider(if (urgent) Red else Orange),
                            fontSize = 12.sp,
                            fontWeight = FontWeight.Bold,
                        ),
                    )
                }
            }
            val worst = cards.attendance.subjects.minByOrNull { it.percent }
            if (worst != null) {
                Spacer(GlanceModifier.height(6.dp))
                val color = when (worst.status) {
                    "safe" -> Green
                    "at_risk" -> Amber
                    else -> Red
                }
                Row(verticalAlignment = Alignment.CenterVertically) {
                    Text(
                        "${worst.percent.toInt()}%",
                        style = TextStyle(color = ColorProvider(color), fontSize = 13.sp, fontWeight = FontWeight.Bold),
                    )
                    Spacer(GlanceModifier.width(6.dp))
                    Text(
                        worst.name,
                        maxLines = 1,
                        style = TextStyle(color = ColorProvider(Secondary), fontSize = 12.sp),
                    )
                }
            }
        }
    }

    companion object {
        /** Redraws every placed widget from the latest cards. */
        suspend fun refresh(context: Context) {
            runCatching { WeekWidget().updateAll(context) }
        }
    }
}

class WeekWidgetReceiver : GlanceAppWidgetReceiver() {
    override val glanceAppWidget: GlanceAppWidget = WeekWidget()
}
