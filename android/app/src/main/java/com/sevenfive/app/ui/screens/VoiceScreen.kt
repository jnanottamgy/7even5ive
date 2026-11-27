package com.sevenfive.app.ui.screens

import android.Manifest
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.animation.core.RepeatMode
import androidx.compose.animation.core.animateFloat
import androidx.compose.animation.core.infiniteRepeatable
import androidx.compose.animation.core.rememberInfiniteTransition
import androidx.compose.animation.core.tween
import androidx.compose.foundation.background
import androidx.compose.ui.graphics.graphicsLayer
import androidx.compose.foundation.border
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.widthIn
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.lazy.rememberLazyListState
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.CallEnd
import androidx.compose.material.icons.filled.Mic
import com.sevenfive.app.ui.theme.pressable
import androidx.compose.material.icons.filled.Stop
import androidx.compose.material3.Icon
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.DisposableEffect
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.scale
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.dp
import android.app.Activity
import android.content.Context
import android.content.ContextWrapper
import androidx.compose.ui.platform.LocalContext
import androidx.lifecycle.Lifecycle
import androidx.lifecycle.LifecycleEventObserver
import androidx.lifecycle.compose.LocalLifecycleOwner
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import com.sevenfive.app.ui.AppViewModel
import com.sevenfive.app.ui.components.PrimaryPill
import com.sevenfive.app.ui.components.PushScaffold
import com.sevenfive.app.ui.theme.LocalAppColors
import com.sevenfive.app.ui.theme.glassSurface
import com.sevenfive.app.voice.VoiceAssistant

/**
 * Talk to 7even5ive. ElevenLabs listens and speaks; every fact comes from a tool the phone runs
 * through the gateway, so the voice can do exactly what a tap can and nothing more. The microphone
 * is asked for when the student starts, and the conversation ends when they leave the screen.
 */
@Composable
fun VoiceScreen(vm: AppViewModel, onBack: () -> Unit) {
    val state by vm.voice.collectAsStateWithLifecycle()
    val app = LocalAppColors.current
    val mic = rememberLauncherForActivityResult(ActivityResultContracts.RequestPermission()) { granted ->
        if (granted) vm.startVoice() else vm.say("The voice assistant needs the microphone")
    }
    // The conversation ends when the student leaves this screen or the app, but not when the
    // phone turns or the theme changes (the activity is only being rebuilt then).
    val context = LocalContext.current
    val lifecycleOwner = LocalLifecycleOwner.current
    DisposableEffect(lifecycleOwner) {
        val activity = context.findActivity()
        val observer = LifecycleEventObserver { _, event ->
            if (event == Lifecycle.Event.ON_STOP && activity?.isChangingConfigurations != true) vm.stopVoice()
        }
        lifecycleOwner.lifecycle.addObserver(observer)
        onDispose {
            lifecycleOwner.lifecycle.removeObserver(observer)
            if (activity?.isChangingConfigurations != true) {
                vm.stopVoice()
                vm.clearVoice()
            }
        }
    }
    val list = rememberLazyListState()
    LaunchedEffect(state.lines.size) {
        if (state.lines.isNotEmpty()) list.animateScrollToItem(state.lines.size - 1)
    }

    PushScaffold("Ask 7even5ive", onBack) { padding ->
        // One mic on this screen: the orb. Tap it to talk, tap it again to end.
        fun toggle() {
            if (state.active) {
                vm.stopVoice()
            } else {
                vm.clearVoice()
                if (vm.container.voice.hasMicPermission()) vm.startVoice()
                else mic.launch(Manifest.permission.RECORD_AUDIO)
            }
        }
        Column(Modifier.fillMaxSize().padding(padding)) {
            Orb(state.phase, active = state.active, onClick = ::toggle)
            Text(
                statusLine(state),
                style = MaterialTheme.typography.titleLarge,
                textAlign = TextAlign.Center,
                modifier = Modifier.fillMaxWidth().padding(top = 8.dp),
            )
            state.working?.let {
                Text(it, style = MaterialTheme.typography.bodySmall, color = app.secondaryLabel,
                    textAlign = TextAlign.Center, modifier = Modifier.fillMaxWidth())
            }
            Spacer(Modifier.height(12.dp))
            LazyColumn(
                state = list,
                modifier = Modifier.weight(1f).fillMaxWidth(),
                verticalArrangement = Arrangement.spacedBy(8.dp),
            ) {
                if (state.lines.isEmpty() && !state.active) {
                    item(key = "hints") { Hints() }
                }
                items(state.lines, key = { it.id }) { line -> Bubble(line) }
            }
            Text(
                "Nothing you say is stored by 7even5ive. Adding to your calendar still waits for your tap.",
                style = MaterialTheme.typography.labelSmall,
                color = app.tertiaryLabel,
                textAlign = TextAlign.Center,
                modifier = Modifier.fillMaxWidth().padding(top = 8.dp),
            )
        }
    }
}

private fun statusLine(state: VoiceAssistant.State): String = when (state.phase) {
    VoiceAssistant.Phase.IDLE -> if (state.lines.isEmpty()) "Tap the mic to talk" else "Tap the mic to talk again"
    VoiceAssistant.Phase.CONNECTING -> "Connecting…"
    VoiceAssistant.Phase.LISTENING -> "Listening… tap to end"
    VoiceAssistant.Phase.SPEAKING -> "Speaking… tap to end"
    VoiceAssistant.Phase.ENDED -> state.message ?: "Conversation ended"
    VoiceAssistant.Phase.UNAVAILABLE -> state.message ?: "The voice assistant isn't set up yet"
    VoiceAssistant.Phase.ERROR -> state.message ?: "Something went wrong"
}

/**
 * The orb, neo-minimal: one solid orange circle with the mic. While the conversation is live a
 * single ring breathes out from it and fades; faster while the assistant speaks.
 */
@Composable
private fun Orb(phase: VoiceAssistant.Phase, active: Boolean, onClick: () -> Unit) {
    val orange = com.sevenfive.app.ui.theme.Orange
    val live = phase == VoiceAssistant.Phase.LISTENING || phase == VoiceAssistant.Phase.SPEAKING
    val speaking = phase == VoiceAssistant.Phase.SPEAKING
    val pulse = rememberInfiniteTransition(label = "orb")
    val wave by pulse.animateFloat(
        initialValue = 0f,
        targetValue = 1f,
        animationSpec = infiniteRepeatable(tween(if (speaking) 900 else 1600), RepeatMode.Restart),
        label = "orb wave",
    )
    Box(Modifier.fillMaxWidth().height(176.dp), contentAlignment = Alignment.Center) {
        if (live) {
            Box(
                Modifier
                    .size(120.dp)
                    .scale(1f + wave * 0.6f)
                    .graphicsLayer { alpha = (1f - wave) * 0.55f }
                    .border(2.dp, orange, CircleShape),
            )
        }
        Box(
            Modifier
                .size(120.dp)
                .pressable(scaleTo = 0.93f, haptic = true, onClick = onClick)
                .background(orange, CircleShape),
            contentAlignment = Alignment.Center,
        ) {
            Icon(
                if (active) Icons.Filled.Stop else Icons.Filled.Mic,
                contentDescription = if (active) "End the conversation" else "Start talking",
                tint = com.sevenfive.app.ui.theme.NeoInk,
                modifier = Modifier.size(40.dp),
            )
        }
    }
}

@Composable
private fun Hints() {
    val app = LocalAppColors.current
    Column(Modifier.fillMaxWidth().padding(vertical = 8.dp)) {
        Text("TRY", style = MaterialTheme.typography.labelSmall, color = app.secondaryLabel,
            modifier = Modifier.padding(bottom = 6.dp))
        listOf(
            "“What's due this week?”",
            "“Can I skip Database Management Systems tomorrow?”",
            "“What's my first class today?”",
            "“Remind me an hour before the quiz.”",
            "“Any placements in my mail?”",
        ).forEach {
            Text(it, style = MaterialTheme.typography.titleMedium,
                modifier = Modifier.padding(vertical = 6.dp))
        }
    }
}

@Composable
private fun Bubble(line: VoiceAssistant.Line) {
    if (line.fromAgent) {
        // The answer: plain, readable text, no bubble.
        Text(
            line.text,
            style = MaterialTheme.typography.titleMedium,
            color = MaterialTheme.colorScheme.onSurface,
            modifier = Modifier.fillMaxWidth().padding(vertical = 4.dp),
        )
    } else {
        // What you said: a small ink pill on the right.
        Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.End) {
            Text(
                line.text,
                style = MaterialTheme.typography.bodyMedium,
                color = com.sevenfive.app.ui.theme.NeoGround,
                modifier = Modifier
                    .widthIn(max = 280.dp)
                    .background(com.sevenfive.app.ui.theme.NeoInk, RoundedCornerShape(18.dp))
                    .padding(horizontal = 14.dp, vertical = 10.dp),
            )
        }
    }
}

private tailrec fun Context.findActivity(): Activity? = when (this) {
    is Activity -> this
    is ContextWrapper -> baseContext.findActivity()
    else -> null
}
