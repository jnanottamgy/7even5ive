package com.sevenfive.app.ui

import android.content.Context
import android.media.AudioAttributes
import android.media.MediaPlayer
import android.speech.tts.TextToSpeech
import android.speech.tts.UtteranceProgressListener
import com.sevenfive.app.data.ApiException
import com.sevenfive.app.data.Briefing
import com.sevenfive.app.data.CoreApi
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.update
import kotlinx.coroutines.withContext
import java.io.File
import java.util.Locale

/**
 * Reads today's briefing aloud. ElevenLabs' voice when the server has it (made on the first tap,
 * cached there per day); otherwise the phone's own text-to-speech reads the same text, which the
 * plan accepts as the stand-in. The briefing is never a notification (decision 41).
 *
 * One briefing plays at a time: a second Play while one is loading is ignored, and while one is
 * playing it starts over. Everything that touches the players runs on the main thread.
 */
class BriefingPlayer(private val context: Context, private val core: CoreApi) {
    enum class Phase { IDLE, LOADING, PLAYING }

    data class State(
        val phase: Phase = Phase.IDLE,
        /** "ElevenLabs" or "Phone voice": said on screen, so the demo shows which ran. */
        val voice: String? = null,
        /** Why the phone's voice was used instead, when ElevenLabs was expected. */
        val note: String? = null,
    )

    private val _state = MutableStateFlow(State())
    val state: StateFlow<State> = _state.asStateFlow()
    private var player: MediaPlayer? = null
    private var tts: TextToSpeech? = null
    private var ttsReady = false
    /** What to read once the phone's voice has started up. */
    private var pending: Pair<String, String?>? = null
    /** Each play's number: a slow fetch or a late callback from an earlier play does nothing. */
    private var playId = 0

    /** Fetches today's briefing with [load] and reads it. Call from the main thread. */
    suspend fun play(load: suspend () -> Briefing): Briefing? {
        if (_state.value.phase == Phase.LOADING) return null
        stop()
        val id = ++playId
        _state.value = State(Phase.LOADING)
        val briefing = try {
            load()
        } catch (e: ApiException) {
            if (id == playId) _state.value = State(note = e.detail)
            return null
        }
        var note: String? = null
        if (briefing.audio.available) {
            try {
                val bytes = core.briefingAudio()
                // A new file for every play: an earlier player may still hold the last one.
                val file = withContext(Dispatchers.IO) {
                    context.cacheDir.listFiles { f -> f.name.startsWith("briefing-") }?.forEach { it.delete() }
                    File(context.cacheDir, "briefing-${briefing.day}-$id.mp3").apply { writeBytes(bytes) }
                }
                if (id == playId) playFile(file, id)
                return briefing
            } catch (e: ApiException) {
                note = e.detail
            }
        }
        if (id == playId) speak(briefing.text, note)
        return briefing
    }

    private fun playFile(file: File, id: Int) {
        releasePlayer()
        val media = MediaPlayer()
        player = media
        media.setAudioAttributes(
            AudioAttributes.Builder()
                .setUsage(AudioAttributes.USAGE_MEDIA)
                .setContentType(AudioAttributes.CONTENT_TYPE_SPEECH)
                .build(),
        )
        media.setDataSource(file.path)
        media.setOnPreparedListener {
            if (id == playId && player === it) {
                it.start()
                _state.value = State(Phase.PLAYING, voice = "ElevenLabs")
            }
        }
        media.setOnCompletionListener { if (player === it) stop() }
        media.setOnErrorListener { mp, _, _ ->
            if (player === mp) stop()
            true
        }
        media.prepareAsync()
    }

    private fun speak(text: String, note: String?) {
        val engine = tts
        if (engine != null && ttsReady) {
            say(engine, text, note)
            return
        }
        pending = text to note
        if (engine != null) return  // still starting up: it reads `pending` when ready
        tts = TextToSpeech(context) { status ->
            val ready = tts
            if (status == TextToSpeech.SUCCESS && ready != null) {
                ttsReady = true
                ready.language = Locale.forLanguageTag("en-IN")
                pending?.let { (t, n) -> say(ready, t, n) }
            } else {
                // Gone, so the next Play tries again from scratch instead of waiting forever.
                ready?.shutdown()
                tts = null
                ttsReady = false
                _state.value = State(note = "This phone has no text-to-speech voice.")
            }
            pending = null
        }
    }

    private fun say(engine: TextToSpeech, text: String, note: String?) {
        engine.setOnUtteranceProgressListener(object : UtteranceProgressListener() {
            override fun onStart(utteranceId: String?) = Unit
            override fun onDone(utteranceId: String?) {
                _state.update { if (it.phase == Phase.PLAYING && it.voice == PHONE) State(note = it.note) else it }
            }

            @Deprecated("Deprecated in Java")
            override fun onError(utteranceId: String?) {
                _state.value = State(note = "The phone's voice couldn't read it.")
            }
        })
        _state.value = State(Phase.PLAYING, voice = PHONE, note = note)
        engine.speak(text, TextToSpeech.QUEUE_FLUSH, null, "briefing")
    }

    private fun releasePlayer() {
        player?.let {
            runCatching { it.stop() }
            it.release()
        }
        player = null
    }

    /** Stops whatever is playing (main thread). */
    fun stop() {
        playId++
        releasePlayer()
        tts?.stop()
        pending = null
        _state.update { State(note = it.note) }
    }

    private companion object {
        const val PHONE = "Phone voice"
    }
}
