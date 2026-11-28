package com.sevenfive.app.widget

import android.content.Context
import android.os.SystemClock
import android.widget.RemoteViews
import androidx.glance.appwidget.AndroidRemoteViews
import androidx.glance.layout.Box
import androidx.glance.layout.size
import com.sevenfive.app.R
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

// The app's neo-minimal palette: off-white, ink, one grey, orange only where it matters.
private val Ground = Color(0xFFF3F3F0)
private val Ink = Color(0xFF111111)
private val Grey = Color(0xFF66665F)
private val Orange = Color(0xFFFF8A1F)
private val DeepOrange = Color(0xFFC2410C)

/**
 * The home-screen widget, neo-minimal: the next thing due as a live countdown (Android's own
 * Chronometer, so it ticks every second without the app), then attendance in one line. From
 * the last cards the app saw, so it shows something with no network. Tapping opens the app.
 */
class WeekWidget : GlanceAppWidget() {
    override suspend fun provideGlance(context: Context, id: GlanceId) {
        val cards = (context.applicationContext as SevenFiveApp).container.cards.cached()
        provideContent { Content(context, cards) }
    }

    @Composable
    private fun Content(context: Context, cards: Cards?) {
        Column(
            GlanceModifier
                .fillMaxSize()
                .background(Ground)
                .cornerRadius(24.dp)
                .padding(horizontal = 16.dp, vertical = 14.dp)
                .clickable(actionStartActivity<MainActivity>()),
        ) {
            Row(GlanceModifier.fillMaxWidth(), verticalAlignment = Alignment.CenterVertically) {
                Box(GlanceModifier.size(6.dp).cornerRadius(3.dp).background(Orange)) {}
                Spacer(GlanceModifier.width(6.dp))
                Text(
                    "NEXT",
                    style = TextStyle(color = ColorProvider(Grey), fontSize = 10.sp, fontWeight = FontWeight.Medium),
                    modifier = GlanceModifier.defaultWeight(),
                )
                Text(
                    "7even5ive",
                    style = TextStyle(color = ColorProvider(Ink), fontSize = 11.sp, fontWeight = FontWeight.Medium),
                )
            }
            if (cards == null) {
                Spacer(GlanceModifier.height(8.dp))
                Text("Open the app once to load your week.", style = TextStyle(color = ColorProvider(Grey), fontSize = 13.sp))
                return@Column
            }
            val now = Instant.now()
            val next = cards.dueThisWeek
                .mapNotNull { item -> Time.parse(item.dueAt)?.let { item to it } }
                .filter { it.second.toInstant().isAfter(now) }
                .minByOrNull { it.second }
            if (next == null) {
                Spacer(GlanceModifier.height(4.dp))
                Text("A clear week", style = TextStyle(color = ColorProvider(Ink), fontSize = 26.sp, fontWeight = FontWeight.Medium))
            } else {
                val (item, at) = next
                val left = Duration.between(now, at.toInstant()).toMillis()
                val clock = RemoteViews(context.packageName, R.layout.widget_countdown).apply {
                    setChronometer(R.id.widget_countdown, SystemClock.elapsedRealtime() + left, null, true)
                    setChronometerCountDown(R.id.widget_countdown, true)
                }
                AndroidRemoteViews(clock)
                Text(
                    item.title ?: "Untitled",
                    maxLines = 1,
                    style = TextStyle(color = ColorProvider(Ink), fontSize = 14.sp, fontWeight = FontWeight.Medium),
                )
                Text(
                    "Due " + Time.dayAndTime(at),
                    maxLines = 1,
                    style = TextStyle(color = ColorProvider(Grey), fontSize = 11.sp),
                )
            }
            val subjects = cards.attendance.subjects
            if (subjects.isNotEmpty()) {
                Spacer(GlanceModifier.defaultWeight())
                val above = subjects.count { it.percent >= it.minimumPercent }
                val worst = subjects.minByOrNull { it.percent }
                Row(GlanceModifier.fillMaxWidth(), verticalAlignment = Alignment.CenterVertically) {
                    Text(
                        "$above/${subjects.size}",
                        style = TextStyle(color = ColorProvider(Ink), fontSize = 16.sp, fontWeight = FontWeight.Bold),
                    )
                    Spacer(GlanceModifier.width(6.dp))
                    Text(
                        "above ${subjects.first().minimumPercent.toInt()}%",
                        style = TextStyle(color = ColorProvider(Grey), fontSize = 11.sp),
                        modifier = GlanceModifier.defaultWeight(),
                    )
                    if (worst != null && worst.percent < worst.minimumPercent) {
                        Text(
                            "${worst.code} ${worst.percent.toInt()}%",
                            style = TextStyle(color = ColorProvider(DeepOrange), fontSize = 11.sp, fontWeight = FontWeight.Bold),
                        )
                    }
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
