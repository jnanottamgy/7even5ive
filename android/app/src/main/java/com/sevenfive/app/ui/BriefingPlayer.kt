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

    suspend fun play(briefing: Briefing) {
        stop()
        _state.value = State(Phase.LOADING)
        var note: String? = null
        if (briefing.audio.available) {
            try {
                val bytes = core.briefingAudio()
                val file = File(context.cacheDir, "briefing-${briefing.day}.mp3")
                withContext(Dispatchers.IO) { file.writeBytes(bytes) }
                withContext(Dispatchers.Main) { playFile(file) }
                return
            } catch (e: ApiException) {
                note = e.detail
            }
        }
        withContext(Dispatchers.Main) { speak(briefing.text, note) }
    }

    private fun playFile(file: File) {
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
            it.start()
            _state.value = State(Phase.PLAYING, voice = "ElevenLabs")
        }
        media.setOnCompletionListener { stop() }
        media.setOnErrorListener { _, _, _ ->
            stop()
            true
        }
        media.prepareAsync()
    }

    private fun speak(text: String, note: String?) {
        val engine = tts
        if (engine != null) {
            say(engine, text, note)
            return
        }
        tts = TextToSpeech(context) { status ->
            val ready = tts
            if (status == TextToSpeech.SUCCESS && ready != null) {
                ready.language = Locale("en", "IN")
                say(ready, text, note)
            } else {
                _state.value = State(note = "This phone has no text-to-speech voice.")
            }
        }
    }

    private fun say(engine: TextToSpeech, text: String, note: String?) {
        engine.setOnUtteranceProgressListener(object : UtteranceProgressListener() {
            override fun onStart(utteranceId: String?) = Unit
            override fun onDone(utteranceId: String?) {
                _state.update { if (it.phase == Phase.PLAYING) State(note = it.note) else it }
            }

            @Deprecated("Deprecated in Java")
            override fun onError(utteranceId: String?) {
                _state.value = State(note = "The phone's voice couldn't read it.")
            }
        })
        _state.value = State(Phase.PLAYING, voice = "Phone voice", note = note)
        engine.speak(text, TextToSpeech.QUEUE_FLUSH, null, "briefing")
    }

    fun stop() {
        player?.let {
            runCatching { it.stop() }
            it.release()
        }
        player = null
        tts?.stop()
        _state.update { State(note = it.note) }
    }
}
