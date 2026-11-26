package com.sevenfive.app.voice

import android.Manifest
import android.content.Context
import android.content.pm.PackageManager
import android.media.AudioAttributes
import android.media.AudioDeviceInfo
import android.media.AudioFormat
import android.media.AudioManager
import android.media.AudioRecord
import android.media.AudioTrack
import android.media.MediaRecorder
import android.media.audiofx.AcousticEchoCanceler
import android.media.audiofx.NoiseSuppressor
import android.os.Build
import android.util.Base64
import androidx.core.content.ContextCompat
import com.sevenfive.app.data.ApiException
import com.sevenfive.app.data.AppJson
import com.sevenfive.app.data.CardsRepository
import com.sevenfive.app.data.CoreApi
import com.sevenfive.app.data.VoiceSession
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.Job
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.channels.Channel
import kotlinx.coroutines.delay
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.update
import kotlinx.coroutines.isActive
import kotlinx.coroutines.launch
import kotlinx.serialization.json.JsonElement
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.buildJsonObject
import kotlinx.serialization.json.contentOrNull
import kotlinx.serialization.json.intOrNull
import kotlinx.serialization.json.jsonObject
import kotlinx.serialization.json.jsonPrimitive
import kotlinx.serialization.json.put
import okhttp3.OkHttpClient
import okhttp3.Request
import okhttp3.Response
import okhttp3.WebSocket
import okhttp3.WebSocketListener
import java.util.concurrent.TimeUnit
import java.util.concurrent.atomic.AtomicLong

/**
 * A spoken conversation with 7even5ive's assistant, ElevenLabs on the other end.
 *
 * The server hands out a signed address for one conversation (GET /api/voice/session); our
 * ElevenLabs key never reaches the phone. This class opens that WebSocket, streams the microphone
 * up as 16-bit PCM, plays the agent's voice as it arrives, stops it the moment the student talks
 * over it, and answers ElevenLabs' pings. When the agent wants a fact it sends a client tool call;
 * the phone runs it through /api/tools with its own token, the same gateway as any tap, and sends
 * the answer back. Only the tools the server listed may run. Nothing said is stored: the
 * transcript lives here while the screen is open.
 */
class VoiceAssistant(
    private val context: Context,
    private val core: CoreApi,
    private val cards: CardsRepository,
    baseClient: OkHttpClient,
) {
    enum class Phase { IDLE, CONNECTING, LISTENING, SPEAKING, ENDED, UNAVAILABLE, ERROR }

    data class Line(val id: Long, val fromAgent: Boolean, val text: String)

    data class State(
        val phase: Phase = Phase.IDLE,
        val lines: List<Line> = emptyList(),
        /** What the assistant is looking up right now ("Checking what's due…"). */
        val working: String? = null,
        val message: String? = null,
    ) {
        val active: Boolean get() = phase == Phase.CONNECTING || phase == Phase.LISTENING || phase == Phase.SPEAKING
    }

    private val client = baseClient.newBuilder().readTimeout(0, TimeUnit.SECONDS).build()
    private val scope = CoroutineScope(SupervisorJob() + Dispatchers.Default)
    private val _state = MutableStateFlow(State())
    val state: StateFlow<State> = _state.asStateFlow()
    private val lineIds = AtomicLong()

    /** The live conversation's socket; null once it ends (by us or by ElevenLabs). */
    @Volatile private var socket: WebSocket? = null
    private var recorder: AudioRecord? = null
    private var track: AudioTrack? = null
    private val jobs = java.util.concurrent.CopyOnWriteArrayList<Job>()
    private var playback = Channel<ByteArray>(Channel.UNLIMITED)
    private var allowed: Set<String> = emptySet()
    @Volatile private var interruptedThrough = -1
    @Volatile private var lastAudioAt = 0L
    private var savedMode: Int? = null

    fun hasMicPermission(): Boolean =
        ContextCompat.checkSelfPermission(context, Manifest.permission.RECORD_AUDIO) == PackageManager.PERMISSION_GRANTED

    fun start() {
        if (_state.value.active) return
        _state.value = State(Phase.CONNECTING)
        scope.launch {
            val session = try {
                core.voiceSession()
            } catch (e: ApiException) {
                _state.value = State(Phase.ERROR, message = e.detail)
                return@launch
            }
            val url = session.signedUrl
            if (!session.available || url == null) {
                _state.value = State(Phase.UNAVAILABLE, message = session.reason ?: "The voice assistant isn't available.")
                return@launch
            }
            allowed = session.tools.toSet()
            interruptedThrough = -1
            playback = Channel(Channel.UNLIMITED)
            jobs.clear()
            socket = client.newWebSocket(Request.Builder().url(url).build(), Listener(session))
            // The agent ends the call itself at its limit; this is the phone's own backstop.
            jobs += scope.launch {
                delay((session.maxSeconds + 15) * 1000L)
                stop("That's the time limit for one conversation.")
            }
        }
    }

    fun stop(message: String? = null) {
        val wasActive = _state.value.active
        val open = socket
        socket = null  // first, so the close that follows is known to be ours
        open?.close(1000, "done")
        jobs.forEach { it.cancel() }
        jobs.clear()
        stopAudio()
        if (wasActive || message != null) {
            _state.update { it.copy(phase = Phase.ENDED, working = null, message = message) }
        }
    }

    fun clear() {
        if (!_state.value.active) _state.value = State()
    }

    private fun send(json: JsonObject) {
        socket?.send(json.toString())
    }

    private inner class Listener(private val session: VoiceSession) : WebSocketListener() {
        override fun onOpen(webSocket: WebSocket, response: Response) {
            // Sent on the socket handed to us: it may open before newWebSocket has even returned.
            webSocket.send(buildJsonObject {
                put("type", "conversation_initiation_client_data")
                put("dynamic_variables", buildJsonObject {
                    session.dynamicVariables.forEach { (k, v) -> put(k, v) }
                })
            }.toString())
        }

        override fun onMessage(webSocket: WebSocket, text: String) {
            if (socket !== webSocket) return  // a conversation that already ended
            val message = runCatching { AppJson.parseToJsonElement(text).jsonObject }.getOrNull() ?: return
            handle(message)
        }

        override fun onFailure(webSocket: WebSocket, t: Throwable, response: Response?) {
            ended(webSocket, Phase.ERROR, "The conversation dropped. Try again.")
        }

        override fun onClosed(webSocket: WebSocket, code: Int, reason: String) {
            ended(webSocket, Phase.ENDED, null)
        }

        private fun ended(webSocket: WebSocket, phase: Phase, message: String?) {
            if (socket !== webSocket) return  // we closed it ourselves, or it is an older one
            socket = null
            stopAudio()
            jobs.forEach { it.cancel() }
            jobs.clear()
            _state.update { it.copy(phase = phase, working = null, message = message) }
        }
    }

    private fun handle(message: JsonObject) {
        when (message.str("type")) {
            "conversation_initiation_metadata" -> {
                val event = message.obj("conversation_initiation_metadata_event")
                val output = rate(event?.str("agent_output_audio_format"))
                val input = rate(event?.str("user_input_audio_format"))
                if (output == null || input == null) {
                    stop("This voice uses an audio format the app can't play.")
                    return
                }
                if (!startAudio(input, output)) return
                _state.update { it.copy(phase = Phase.LISTENING) }
            }
            "audio" -> {
                val event = message.obj("audio_event") ?: return
                val id = event.int("event_id") ?: 0
                if (id <= interruptedThrough) return  // it was talked over: never play it
                val audio = event.str("audio_base_64") ?: return
                playback.trySend(Base64.decode(audio, Base64.DEFAULT))
                lastAudioAt = System.currentTimeMillis()
                _state.update { if (it.phase == Phase.LISTENING) it.copy(phase = Phase.SPEAKING) else it }
            }
            "interruption" -> {
                interruptedThrough = message.obj("interruption_event")?.int("event_id") ?: interruptedThrough
                drainPlayback()
                _state.update { it.copy(phase = Phase.LISTENING) }
            }
            "agent_response" ->
                message.obj("agent_response_event")?.str("agent_response")?.let { add(fromAgent = true, it) }
            "agent_response_correction" -> {
                val corrected = message.obj("agent_response_correction_event")?.str("corrected_agent_response") ?: return
                _state.update { s ->
                    val last = s.lines.indexOfLast { it.fromAgent }
                    if (last < 0) s else s.copy(lines = s.lines.toMutableList().also { it[last] = it[last].copy(text = corrected) })
                }
            }
            "user_transcript" ->
                message.obj("user_transcription_event")?.str("user_transcript")?.takeIf { it.isNotBlank() }
                    ?.let { add(fromAgent = false, it) }
            "ping" -> {
                val id = message.obj("ping_event")?.int("event_id") ?: return
                send(buildJsonObject {
                    put("type", "pong")
                    put("event_id", id)
                })
            }
            "client_tool_call" -> message.obj("client_tool_call")?.let { runTool(it) }
        }
    }

    private fun add(fromAgent: Boolean, text: String) {
        _state.update { it.copy(lines = it.lines + Line(lineIds.incrementAndGet(), fromAgent, text)) }
    }

    /** One tool the agent asked for, run through the gateway with the student's token. */
    private fun runTool(call: JsonObject) {
        val name = call.str("tool_name") ?: return
        val id = call.str("tool_call_id") ?: return
        val args = (call["parameters"] as? JsonObject) ?: JsonObject(emptyMap())
        _state.update { it.copy(working = workingLabel(name)) }
        scope.launch {
            val (result, isError) = if (name !in allowed) {
                "That isn't something 7even5ive can do from here." to true
            } else {
                try {
                    core.toolText(name, args).take(MAX_RESULT_CHARS) to false
                } catch (e: ApiException) {
                    // The gateway's own reason ("calls are off", "approval needed"), said as it is.
                    e.detail to true
                }
            }
            send(buildJsonObject {
                put("type", "client_tool_result")
                put("tool_call_id", id)
                put("result", result)
                put("is_error", isError)
            })
            _state.update { it.copy(working = null) }
            if (!isError && name in CHANGES_CARDS) cards.refresh()
        }
    }

    // --- audio ------------------------------------------------------------------------------------
    private fun startAudio(inputRate: Int, outputRate: Int): Boolean {
        if (!hasMicPermission()) {
            stop("7even5ive needs the microphone to hear you.")
            return false
        }
        val audio = context.getSystemService(AudioManager::class.java)
        if (audio != null) {
            // A call-style session: the phone's echo canceller hears what the speaker plays.
            savedMode = audio.mode
            audio.mode = AudioManager.MODE_IN_COMMUNICATION
            routeToSpeaker(audio)
        }
        val outMin = AudioTrack.getMinBufferSize(outputRate, AudioFormat.CHANNEL_OUT_MONO, AudioFormat.ENCODING_PCM_16BIT)
        val out = AudioTrack.Builder()
            .setAudioAttributes(
                AudioAttributes.Builder()
                    .setUsage(AudioAttributes.USAGE_VOICE_COMMUNICATION)
                    .setContentType(AudioAttributes.CONTENT_TYPE_SPEECH)
                    .build(),
            )
            .setAudioFormat(
                AudioFormat.Builder()
                    .setEncoding(AudioFormat.ENCODING_PCM_16BIT)
                    .setSampleRate(outputRate)
                    .setChannelMask(AudioFormat.CHANNEL_OUT_MONO)
                    .build(),
            )
            .setBufferSizeInBytes(maxOf(outMin, outputRate))  // about half a second
            .setTransferMode(AudioTrack.MODE_STREAM)
            .build()
        out.play()
        track = out

        val chunkBytes = inputRate / 10 * 2  // 100 ms of 16-bit mono
        val inMin = AudioRecord.getMinBufferSize(inputRate, AudioFormat.CHANNEL_IN_MONO, AudioFormat.ENCODING_PCM_16BIT)
        val mic = try {
            AudioRecord(
                MediaRecorder.AudioSource.VOICE_COMMUNICATION, inputRate, AudioFormat.CHANNEL_IN_MONO,
                AudioFormat.ENCODING_PCM_16BIT, maxOf(inMin, chunkBytes * 4),
            )
        } catch (e: SecurityException) {
            stop("7even5ive needs the microphone to hear you.")
            return false
        }
        if (mic.state != AudioRecord.STATE_INITIALIZED) {
            mic.release()
            stop("The microphone is busy in another app.")
            return false
        }
        if (AcousticEchoCanceler.isAvailable()) AcousticEchoCanceler.create(mic.audioSessionId)?.enabled = true
        if (NoiseSuppressor.isAvailable()) NoiseSuppressor.create(mic.audioSessionId)?.enabled = true
        mic.startRecording()
        recorder = mic

        jobs += listOf(
            scope.launch(Dispatchers.IO) {
                val buffer = ByteArray(chunkBytes)
                while (isActive && recorder === mic) {
                    val read = mic.read(buffer, 0, buffer.size)
                    if (read > 0) {
                        send(buildJsonObject { put("user_audio_chunk", Base64.encodeToString(buffer, 0, read, Base64.NO_WRAP)) })
                    }
                }
            },
            scope.launch(Dispatchers.IO) {
                for (pcm in playback) {
                    val player = track ?: break
                    player.write(pcm, 0, pcm.size)
                }
            },
            scope.launch {
                // No new audio for a moment: the agent has finished speaking.
                while (isActive) {
                    delay(250)
                    if (_state.value.phase == Phase.SPEAKING && System.currentTimeMillis() - lastAudioAt > 700) {
                        _state.update { if (it.phase == Phase.SPEAKING) it.copy(phase = Phase.LISTENING) else it }
                    }
                }
            },
        )
        return true
    }

    private fun drainPlayback() {
        while (playback.tryReceive().isSuccess) Unit
        track?.let {
            runCatching {
                it.pause()
                it.flush()
                it.play()
            }
        }
    }

    private fun stopAudio() {
        recorder?.let {
            runCatching { it.stop() }
            it.release()
        }
        recorder = null
        playback.close()
        track?.let {
            runCatching { it.stop() }
            it.release()
        }
        track = null
        val audio = context.getSystemService(AudioManager::class.java)
        if (audio != null && savedMode != null) {
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.S) audio.clearCommunicationDevice() else legacySpeaker(audio, false)
            savedMode?.let { audio.mode = it }
        }
        savedMode = null
    }

    private fun routeToSpeaker(audio: AudioManager) {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.S) {
            audio.availableCommunicationDevices.firstOrNull { it.type == AudioDeviceInfo.TYPE_BUILTIN_SPEAKER }
                ?.let { audio.setCommunicationDevice(it) }
        } else {
            legacySpeaker(audio, true)
        }
    }

    /** Before Android 12 the speaker is chosen with the old switch. */
    @Suppress("DEPRECATION")
    private fun legacySpeaker(audio: AudioManager, on: Boolean) {
        audio.isSpeakerphoneOn = on
    }

    companion object {
        private const val MAX_RESULT_CHARS = 8_000
        private val CHANGES_CARDS = setOf("set_reminder", "cancel_reminder", "mark_done", "reopen", "add_to_calendar")

        /** "pcm_16000" -> 16000. Anything else (μ-law is for phone lines) the app can't play. */
        fun rate(format: String?): Int? =
            format?.takeIf { it.startsWith("pcm_") }?.removePrefix("pcm_")?.toIntOrNull()?.takeIf { it in 8_000..48_000 }

        fun workingLabel(tool: String): String = when (tool) {
            "due_this_week" -> "Checking what's due…"
            "timetable_today" -> "Looking at today's classes…"
            "attendance" -> "Checking attendance…"
            "briefing" -> "Putting today together…"
            "materials" -> "Looking through your materials…"
            "opportunities" -> "Checking college mail…"
            "list_reminders", "set_reminder", "cancel_reminder" -> "Updating reminders…"
            "mark_done", "reopen" -> "Updating your list…"
            "add_to_calendar" -> "Asking you to approve…"
            else -> "Working on it…"
        }
    }
}

private fun JsonObject.obj(key: String): JsonObject? = this[key] as? JsonObject
private fun JsonObject.str(key: String): String? = (this[key] as? JsonElement)?.let { runCatching { it.jsonPrimitive.contentOrNull }.getOrNull() }
private fun JsonObject.int(key: String): Int? = (this[key] as? JsonElement)?.let { runCatching { it.jsonPrimitive.intOrNull }.getOrNull() }
