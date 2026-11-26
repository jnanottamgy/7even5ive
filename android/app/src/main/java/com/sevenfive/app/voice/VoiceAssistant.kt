package com.sevenfive.app.voice

import android.Manifest
import android.annotation.SuppressLint
import android.content.Context
import android.content.pm.PackageManager
import android.media.AudioAttributes
import android.media.AudioDeviceInfo
import android.media.AudioFocusRequest
import android.media.AudioFormat
import android.media.AudioManager
import android.media.AudioRecord
import android.media.AudioTrack
import android.media.MediaRecorder
import android.media.audiofx.AcousticEchoCanceler
import android.media.audiofx.NoiseSuppressor
import android.os.Build
import android.os.Handler
import android.os.Looper
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
import kotlinx.coroutines.withTimeoutOrNull
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
import java.util.concurrent.CopyOnWriteArrayList
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
 *
 * Every conversation has a generation number. Ending one (End, leaving the screen, the server
 * closing, a dropped connection) moves the generation on, under one lock, so a session that
 * arrives late, a socket that opens late or a callback from an old socket finds itself stale and
 * does nothing: the microphone can only ever be on for the conversation on screen.
 *
 * The conversation holds the phone's audio for itself while it lasts (other apps pause; a phone
 * call ends it) and talks through what the student is wearing: a Bluetooth or wired headset or
 * earphones, and the loudspeaker only when there is none.
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

    private val lock = Any()
    /** The conversation everything below belongs to; moves on whenever one ends. */
    @Volatile private var generation = 0L
    private var connectJob: Job? = null
    @Volatile private var socket: WebSocket? = null
    private var recorder: AudioRecord? = null
    private var echo: AcousticEchoCanceler? = null
    private var noise: NoiseSuppressor? = null
    private var track: AudioTrack? = null
    private var playbackJob: Job? = null
    private var playback = Channel<ByteArray>(Channel.UNLIMITED)
    /** The timer, the microphone loop and the speaking watcher of the current conversation. */
    private val jobs = CopyOnWriteArrayList<Job>()
    private var allowed: Set<String> = emptySet()
    @Volatile private var interruptedThrough = -1
    @Volatile private var lastAudioAt = 0L
    private var savedMode: Int? = null
    private var focus: AudioFocusRequest? = null
    /** Before Android 12: a Bluetooth headset's call channel was opened for this conversation. */
    private var legacySco = false

    fun hasMicPermission(): Boolean =
        ContextCompat.checkSelfPermission(context, Manifest.permission.RECORD_AUDIO) == PackageManager.PERMISSION_GRANTED

    fun start() {
        val gen = synchronized(lock) {
            if (_state.value.active) return
            _state.value = State(Phase.CONNECTING)
            ++generation
        }
        connectJob = scope.launch { connect(gen) }
    }

    private suspend fun connect(gen: Long) {
        val session = try {
            core.voiceSession()
        } catch (e: ApiException) {
            synchronized(lock) { if (gen == generation) _state.value = State(Phase.ERROR, message = e.detail) }
            return
        }
        synchronized(lock) {
            if (gen != generation) return  // ended or restarted while the server answered
            val url = session.signedUrl
            if (!session.available || url == null) {
                _state.value = State(Phase.UNAVAILABLE, message = session.reason ?: "The voice assistant isn't available.")
                return
            }
            allowed = session.tools.toSet()
            interruptedThrough = -1
            playback = Channel(Channel.UNLIMITED)
            socket = client.newWebSocket(Request.Builder().url(url).build(), Listener(session, gen))
            // The agent ends the call itself at its limit; this is the phone's own backstop.
            jobs += scope.launch {
                delay((session.maxSeconds + 15) * 1000L)
                if (gen == generation) stop("That's the time limit for one conversation.")
            }
        }
    }

    /** End now: the student tapped End or left the screen. Safe to call at any moment. */
    fun stop(message: String? = null) {
        synchronized(lock) {
            val wasActive = _state.value.active
            generation++
            connectJob?.cancel()
            connectJob = null
            val open = socket
            socket = null
            open?.close(1000, "done")
            cancelJobs()
            stopMic()
            releaseOutput()
            if (wasActive || message != null) {
                _state.update { it.copy(phase = Phase.ENDED, working = null, message = message) }
            }
        }
    }

    fun clear() {
        if (!_state.value.active) _state.value = State()
    }

    private fun send(json: JsonObject) {
        socket?.send(json.toString())
    }

    private inner class Listener(private val session: VoiceSession, private val gen: Long) : WebSocketListener() {
        override fun onOpen(webSocket: WebSocket, response: Response) {
            if (gen != generation) {
                webSocket.close(1000, "done")
                return
            }
            // Sent on the socket handed to us: it may open before newWebSocket has even returned.
            webSocket.send(buildJsonObject {
                put("type", "conversation_initiation_client_data")
                put("dynamic_variables", buildJsonObject {
                    session.dynamicVariables.forEach { (k, v) -> put(k, v) }
                })
            }.toString())
        }

        override fun onMessage(webSocket: WebSocket, text: String) {
            if (gen != generation) return
            val message = runCatching { AppJson.parseToJsonElement(text).jsonObject }.getOrNull() ?: return
            handle(message, gen)
        }

        /** ElevenLabs ended it (the agent said goodbye, or its time limit): answer and wind down. */
        override fun onClosing(webSocket: WebSocket, code: Int, reason: String) {
            webSocket.close(1000, null)
            finishFromServer(gen)
        }

        override fun onFailure(webSocket: WebSocket, t: Throwable, response: Response?) {
            synchronized(lock) {
                if (gen != generation) return  // ours, already ended
                generation++
                socket = null
                cancelJobs()
                stopMic()
                releaseOutput()
                _state.update { it.copy(phase = Phase.ERROR, working = null, message = "The conversation dropped. Try again.") }
            }
        }
    }

    /** The microphone stops at once; what the agent already said (its goodbye) plays out. */
    private fun finishFromServer(gen: Long) {
        val consumer: Job?
        synchronized(lock) {
            if (gen != generation) return
            socket = null
            cancelJobs()
            stopMic()
            playback.close()  // queued audio still plays, then the player finishes
            consumer = playbackJob
            _state.update { it.copy(phase = Phase.SPEAKING, working = null) }
        }
        scope.launch {
            withTimeoutOrNull(DRAIN_MILLIS) { consumer?.join() }
            delay(TAIL_MILLIS)  // the last half second still in the player's own buffer
            synchronized(lock) {
                if (gen != generation) return@launch  // End was tapped meanwhile: already clean
                generation++
                releaseOutput()
                _state.update { it.copy(phase = Phase.ENDED, working = null) }
            }
        }
    }

    private fun handle(message: JsonObject, gen: Long) {
        when (message.str("type")) {
            "conversation_initiation_metadata" -> {
                val event = message.obj("conversation_initiation_metadata_event")
                val output = rate(event?.str("agent_output_audio_format"))
                val input = rate(event?.str("user_input_audio_format"))
                if (output == null || input == null) {
                    stop("This voice uses an audio format the app can't play.")
                    return
                }
                if (startAudio(gen, input, output)) {
                    _state.update { if (it.phase == Phase.CONNECTING) it.copy(phase = Phase.LISTENING) else it }
                }
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
                _state.update { if (it.phase == Phase.SPEAKING) it.copy(phase = Phase.LISTENING) else it }
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
            "client_tool_call" -> message.obj("client_tool_call")?.let { runTool(it, gen) }
        }
    }

    private fun add(fromAgent: Boolean, text: String) {
        _state.update { it.copy(lines = it.lines + Line(lineIds.incrementAndGet(), fromAgent, text)) }
    }

    /** One tool the agent asked for, run through the gateway with the student's token. */
    private fun runTool(call: JsonObject, gen: Long) {
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
            if (gen != generation) return@launch  // the conversation ended while the tool ran
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
    /** Opens the speaker and the microphone for this conversation, unless it already ended. */
    private fun startAudio(gen: Long, inputRate: Int, outputRate: Int): Boolean = synchronized(lock) {
        if (gen != generation || track != null) return false
        if (!hasMicPermission()) {
            stop("7even5ive needs the microphone to hear you.")
            return false
        }
        val audio = context.getSystemService(AudioManager::class.java)
        if (audio != null) {
            if (!takeFocus(audio, gen)) {
                stop("Your phone is busy with other audio (a call?). Try again when it's done.")
                return false
            }
            // A call-style session: the phone's echo canceller hears what the speaker plays.
            if (savedMode == null) savedMode = audio.mode
            audio.mode = AudioManager.MODE_IN_COMMUNICATION
            routeOutput(audio)
        }
        val outMin = AudioTrack.getMinBufferSize(outputRate, AudioFormat.CHANNEL_OUT_MONO, AudioFormat.ENCODING_PCM_16BIT)
        val out = AudioTrack.Builder()
            .setAudioAttributes(VOICE)
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
        val queue = playback
        playbackJob = scope.launch(Dispatchers.IO) {
            for (pcm in queue) out.write(pcm, 0, pcm.size)  // this conversation's own player
        }

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
        // Held in fields: an audio effect nobody holds is released by the garbage collector.
        echo = if (AcousticEchoCanceler.isAvailable()) AcousticEchoCanceler.create(mic.audioSessionId)?.also { it.enabled = true } else null
        noise = if (NoiseSuppressor.isAvailable()) NoiseSuppressor.create(mic.audioSessionId)?.also { it.enabled = true } else null
        mic.startRecording()
        recorder = mic

        jobs += scope.launch(Dispatchers.IO) {
            val buffer = ByteArray(chunkBytes)
            while (isActive && gen == generation) {
                val read = mic.read(buffer, 0, buffer.size)
                if (read > 0 && gen == generation) {
                    send(buildJsonObject { put("user_audio_chunk", Base64.encodeToString(buffer, 0, read, Base64.NO_WRAP)) })
                } else if (read < 0) {
                    break  // released under us: the conversation ended
                }
            }
        }
        jobs += scope.launch {
            // No new audio for a moment: the agent has finished speaking.
            while (isActive) {
                delay(250)
                if (_state.value.phase == Phase.SPEAKING && System.currentTimeMillis() - lastAudioAt > 700) {
                    _state.update { if (it.phase == Phase.SPEAKING) it.copy(phase = Phase.LISTENING) else it }
                }
            }
        }
        true
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

    private fun cancelJobs() {
        jobs.forEach { it.cancel() }
        jobs.clear()
    }

    /** Called with the lock held. */
    private fun stopMic() {
        recorder?.let {
            runCatching { it.stop() }
            it.release()
        }
        recorder = null
        echo?.release()
        echo = null
        noise?.release()
        noise = null
    }

    /** Called with the lock held. The speaker, the player, the phone's audio mode and focus. */
    private fun releaseOutput() {
        playback.close()
        playbackJob?.cancel()
        playbackJob = null
        track?.let {
            runCatching { it.stop() }
            it.release()
        }
        track = null
        val audio = context.getSystemService(AudioManager::class.java)
        val mode = savedMode
        if (audio != null && mode != null) {
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.S) audio.clearCommunicationDevice() else legacyRelease(audio)
            audio.mode = mode
        }
        savedMode = null
        focus?.let { audio?.abandonAudioFocusRequest(it) }
        focus = null
    }

    /**
     * The phone's audio for this conversation alone: music and the briefing pause, notification
     * sounds wait. Losing it to a phone call (or an alarm, another assistant) ends the
     * conversation: the microphone must not keep listening under it. False when another app holds
     * it and won't let go (a call in progress).
     */
    private fun takeFocus(audio: AudioManager, gen: Long): Boolean {
        val request = AudioFocusRequest.Builder(AudioManager.AUDIOFOCUS_GAIN_TRANSIENT_EXCLUSIVE)
            .setAudioAttributes(VOICE)
            .setOnAudioFocusChangeListener({ change ->
                if (change == AudioManager.AUDIOFOCUS_LOSS || change == AudioManager.AUDIOFOCUS_LOSS_TRANSIENT) {
                    if (gen == generation) stop("The conversation stopped: your phone needed its audio for something else.")
                }
            }, Handler(Looper.getMainLooper()))
            .build()
        if (audio.requestAudioFocus(request) != AudioManager.AUDIOFOCUS_REQUEST_GRANTED) return false
        focus = request
        return true
    }

    /** Through what the student is wearing ([preferredOutput]); the loudspeaker when nothing is. */
    private fun routeOutput(audio: AudioManager) {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.S) {
            val devices = audio.availableCommunicationDevices
            preferredOutput(devices.map { it.type })?.let { audio.setCommunicationDevice(devices[it]) }
        } else {
            legacyRoute(audio)
        }
    }

    /** Before Android 12: the loudspeaker is the old switch, and a Bluetooth headset's call
     * channel (SCO) is opened by hand. A wired headset takes a call-style session by itself. */
    @Suppress("DEPRECATION")
    private fun legacyRoute(audio: AudioManager) {
        val outputs = audio.getDevices(AudioManager.GET_DEVICES_OUTPUTS).map { it.type }
        when (preferredOutput(outputs)?.let { outputs[it] }) {
            AudioDeviceInfo.TYPE_BLUETOOTH_SCO -> {
                audio.isSpeakerphoneOn = false
                audio.startBluetoothSco()
                audio.isBluetoothScoOn = true
                legacySco = true
            }
            AudioDeviceInfo.TYPE_BUILTIN_SPEAKER, null -> audio.isSpeakerphoneOn = true
            else -> audio.isSpeakerphoneOn = false
        }
    }

    @Suppress("DEPRECATION")
    private fun legacyRelease(audio: AudioManager) {
        if (legacySco) {
            audio.isBluetoothScoOn = false
            audio.stopBluetoothSco()
            legacySco = false
        }
        audio.isSpeakerphoneOn = false
    }

    companion object {
        private val VOICE: AudioAttributes by lazy {
            AudioAttributes.Builder()
                .setUsage(AudioAttributes.USAGE_VOICE_COMMUNICATION)
                .setContentType(AudioAttributes.CONTENT_TYPE_SPEECH)
                .build()
        }

        /** What a conversation talks through, best first: what the student is wearing, then the
         * loudspeaker (the phone is held in front of them, the transcript on screen). The earpiece
         * never: it would sound like the conversation went silent. */
        @SuppressLint("InlinedApi") // plain numbers: on older Android they simply never match
        private val PREFERRED_OUTPUTS = listOf(
            AudioDeviceInfo.TYPE_BLUETOOTH_SCO,
            AudioDeviceInfo.TYPE_BLE_HEADSET,
            AudioDeviceInfo.TYPE_WIRED_HEADSET,
            AudioDeviceInfo.TYPE_USB_HEADSET,
            AudioDeviceInfo.TYPE_WIRED_HEADPHONES,
            AudioDeviceInfo.TYPE_HEARING_AID,
            AudioDeviceInfo.TYPE_BUILTIN_SPEAKER,
        )

        /** The index in [types] (the phone's devices, by AudioDeviceInfo type) to talk through. */
        fun preferredOutput(types: List<Int>): Int? =
            PREFERRED_OUTPUTS.firstNotNullOfOrNull { wanted -> types.indexOf(wanted).takeIf { it >= 0 } }

        private const val MAX_RESULT_CHARS = 8_000
        private const val DRAIN_MILLIS = 4_000L
        private const val TAIL_MILLIS = 600L
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
