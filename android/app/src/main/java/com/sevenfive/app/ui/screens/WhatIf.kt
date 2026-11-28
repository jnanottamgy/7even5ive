package com.sevenfive.app.ui.screens

import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableIntStateOf
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import com.sevenfive.app.data.Cards
import com.sevenfive.app.ui.components.AppCard
import com.sevenfive.app.ui.theme.LocalAppColors
import com.sevenfive.app.ui.theme.LocalStatusColors
import com.sevenfive.app.ui.theme.NeoInk
import com.sevenfive.app.ui.theme.Orange
import java.util.Locale
import kotlin.math.ceil
import kotlin.math.max

/*
 * Grade "what-if": for each subject, the final-exam score needed for each grade, from the
 * internal marks so far. The scheme is stated on screen, not hidden: 50 internal marks (the CIE
 * tests and quizzes so far, scaled to 50) plus the final exam out of 100, halved; ten-point grade
 * bands; at least 35 of 100 in the final exam to pass. Colleges differ, so the note says so.
 */

internal data class GradeBand(val grade: String, val from: Int)

internal val GRADE_BANDS = listOf(
    GradeBand("O", 90), GradeBand("A+", 80), GradeBand("A", 70), GradeBand("B+", 60),
    GradeBand("B", 55), GradeBand("C", 50), GradeBand("P", 40),
)

internal const val FINAL_PASS_MIN = 35

/** Internal marks so far, scaled to 50. */
internal fun internalOutOf50(scored: Double, maximum: Double): Double =
    if (maximum > 0) scored / maximum * 50.0 else 0.0

/** The final-exam mark (out of 100) needed for a total of [from]; null when it's out of reach. */
internal fun finalNeeded(internal50: Double, from: Int): Int? {
    val need = max(FINAL_PASS_MIN, ceil((from - internal50) * 2.0 - 1e-9).toInt())
    return if (need > 100) null else need
}

@Composable
internal fun WhatIfCalculator(cards: Cards) {
    val app = LocalAppColors.current
    val bySubject = cards.marks.data.groupBy { it.code }
    if (bySubject.isEmpty()) {
        Text("No internal marks yet: the calculator needs them from the portal.",
            style = MaterialTheme.typography.bodyMedium, color = app.secondaryLabel)
        return
    }
    val codes = bySubject.keys.toList()
    var pick by rememberSaveable { mutableIntStateOf(0) }
    val code = codes[pick.coerceIn(0, codes.lastIndex)]
    val rows = bySubject.getValue(code)
    val scored = rows.sumOf { it.scored }
    val maximum = rows.sumOf { it.maximum }
    val internal = internalOutOf50(scored, maximum)

    Column(verticalArrangement = Arrangement.spacedBy(14.dp)) {
        NeoSegments(codes.map { Segment(it) }, pick) { pick = it }

        // The subject and its internal marks, scaled.
        Column {
            NeoLabel(cards.subjectName(code))
            Row(verticalAlignment = Alignment.Bottom, modifier = Modifier.padding(top = 6.dp)) {
                Text(String.format(Locale.ENGLISH, "%.1f", internal), style = MaterialTheme.typography.displayMedium)
                Text(" / 50 internal", style = MaterialTheme.typography.titleMedium, color = app.secondaryLabel,
                    modifier = Modifier.padding(bottom = 10.dp))
            }
            Text("${pct(scored)} of ${pct(maximum)} so far: " + rows.joinToString(", ") { "${it.component} ${pct(it.scored)}/${pct(it.maximum)}" },
                style = MaterialTheme.typography.bodySmall, color = app.secondaryLabel)
        }

        // What the final exam needs to be, grade by grade.
        AppCard {
            Column(verticalArrangement = Arrangement.spacedBy(2.dp)) {
                Row(Modifier.fillMaxWidth().padding(bottom = 6.dp)) {
                    Text("GRADE", style = MaterialTheme.typography.labelSmall, color = app.secondaryLabel, modifier = Modifier.weight(1f))
                    Text("FINAL EXAM NEEDS", style = MaterialTheme.typography.labelSmall, color = app.secondaryLabel)
                }
                GRADE_BANDS.forEach { band ->
                    val need = finalNeeded(internal, band.from)
                    val easy = need != null && need <= FINAL_PASS_MIN
                    Row(
                        Modifier
                            .fillMaxWidth()
                            .clip(MaterialTheme.shapes.small)
                            .padding(vertical = 8.dp),
                        verticalAlignment = Alignment.CenterVertically,
                    ) {
                        Text(band.grade, style = MaterialTheme.typography.titleLarge, modifier = Modifier.weight(1f))
                        Text(
                            when {
                                need == null -> "out of reach"
                                easy -> "$FINAL_PASS_MIN / 100 (the pass mark)"
                                else -> "$need / 100"
                            },
                            style = MaterialTheme.typography.titleMedium.copy(fontFeatureSettings = "tnum"),
                            fontWeight = FontWeight.Medium,
                            color = when {
                                need == null -> app.secondaryLabel
                                need >= 85 -> LocalStatusColors.current.short
                                else -> NeoInk
                            },
                        )
                    }
                }
            }
        }
        Row(verticalAlignment = Alignment.Top) {
            androidx.compose.foundation.layout.Box(
                Modifier.padding(top = 6.dp).clip(androidx.compose.foundation.shape.CircleShape).background(Orange)
                    .padding(3.dp),
            )
            Text(
                "  Assumes 50 internal marks (tests and quizzes so far, scaled) plus the final exam out of 100, " +
                    "halved; grade bands O 90, A+ 80, A 70, B+ 60, B 55, C 50, P 40; and at least " +
                    "$FINAL_PASS_MIN in the final exam to pass. Check your college's scheme.",
                style = MaterialTheme.typography.bodySmall,
                color = app.secondaryLabel,
            )
        }
    }
}
