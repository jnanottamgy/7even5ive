package com.sevenfive.app.ui.components

import androidx.compose.runtime.Composable
import androidx.compose.runtime.State
import androidx.compose.runtime.produceState
import kotlinx.coroutines.delay
import java.time.Instant

/**
 * The time now, kept live: it ticks on the boundary of every [periodMillis] (every second for a
 * countdown, every half minute for "in 3 h"), so what the screen says is always true.
 */
@Composable
fun rememberNow(periodMillis: Long = 1_000L): State<Instant> = produceState(Instant.now(), periodMillis) {
    while (true) {
        val ms = System.currentTimeMillis()
        delay(periodMillis - ms % periodMillis + 5)
        value = Instant.now()
    }
}
