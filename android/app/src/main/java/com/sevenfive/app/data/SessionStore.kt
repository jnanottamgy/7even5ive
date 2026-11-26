package com.sevenfive.app.data

import android.content.Context
import android.security.keystore.KeyGenParameterSpec
import android.security.keystore.KeyProperties
import android.util.Base64
import kotlinx.serialization.Serializable
import kotlinx.serialization.decodeFromString
import kotlinx.serialization.encodeToString
import java.security.KeyStore
import javax.crypto.Cipher
import javax.crypto.KeyGenerator
import javax.crypto.SecretKey
import javax.crypto.spec.GCMParameterSpec

/** Seals bytes so that only this phone can open them again. */
interface Sealer {
    fun seal(plain: ByteArray): ByteArray
    fun open(sealed: ByteArray): ByteArray
}

/**
 * AES-256-GCM with a key that lives in the Android Keystore and never leaves it: a copy of the
 * app's files (a backup, a rooted phone's file dump) holds only ciphertext. The 12-byte IV is
 * kept in front of each sealed value.
 */
class KeystoreSealer(private val alias: String = "sevenfive-session") : Sealer {
    /** Synchronized: two first saves at once must not make two keys (the first one's blob would
     * never open again). */
    @Synchronized
    private fun key(): SecretKey {
        val store = KeyStore.getInstance("AndroidKeyStore").apply { load(null) }
        (store.getKey(alias, null) as? SecretKey)?.let { return it }
        val generator = KeyGenerator.getInstance(KeyProperties.KEY_ALGORITHM_AES, "AndroidKeyStore")
        generator.init(
            KeyGenParameterSpec.Builder(alias, KeyProperties.PURPOSE_ENCRYPT or KeyProperties.PURPOSE_DECRYPT)
                .setBlockModes(KeyProperties.BLOCK_MODE_GCM)
                .setEncryptionPaddings(KeyProperties.ENCRYPTION_PADDING_NONE)
                .setKeySize(256)
                .build(),
        )
        return generator.generateKey()
    }

    override fun seal(plain: ByteArray): ByteArray {
        val cipher = Cipher.getInstance("AES/GCM/NoPadding")
        cipher.init(Cipher.ENCRYPT_MODE, key())
        return cipher.iv + cipher.doFinal(plain)
    }

    override fun open(sealed: ByteArray): ByteArray {
        val cipher = Cipher.getInstance("AES/GCM/NoPadding")
        cipher.init(Cipher.DECRYPT_MODE, key(), GCMParameterSpec(128, sealed, 0, IV_BYTES))
        return cipher.doFinal(sealed, IV_BYTES, sealed.size - IV_BYTES)
    }

    private companion object {
        const val IV_BYTES = 12
    }
}

/** Who is using the app on this phone. */
sealed interface Saved {
    data object Nobody : Saved

    /** "Try the demo": the shared demo student, by its public token. */
    data object Demo : Saved

    /** A real account: its session, and its profile as last seen (null until asked). */
    data class Account(val session: Session, val me: Me? = null) : Saved
}

/** Where [Saved] is kept. The app's is [SessionStore]; tests keep it in memory. */
interface SavedAccount {
    fun load(): Saved
    fun save(saved: Saved)
}

@Serializable
private data class SealedAccount(val session: Session, val me: Me? = null)

/**
 * The phone's memory of who is signed in: the session and profile sealed by the Keystore
 * ([KeystoreSealer]), in the app's private preferences. Anything unreadable (a backup restored
 * on another phone, whose Keystore has no key for it) counts as signed out.
 */
class SessionStore(context: Context, private val sealer: Sealer = KeystoreSealer()) : SavedAccount {
    private val prefs = context.getSharedPreferences("account", Context.MODE_PRIVATE)

    @Synchronized
    override fun load(): Saved = try {
        when (prefs.getString(MODE, null)) {
            DEMO -> Saved.Demo
            ACCOUNT -> {
                val sealed = Base64.decode(prefs.getString(SEALED, null) ?: return Saved.Nobody, Base64.NO_WRAP)
                val account = AppJson.decodeFromString<SealedAccount>(String(sealer.open(sealed), Charsets.UTF_8))
                Saved.Account(account.session, account.me)
            }
            else -> Saved.Nobody
        }
    } catch (e: Exception) {
        // A key gone for good (a restore on another phone, the Keystore reset) or a damaged
        // file: sign in again. Anything else (the Keystore busy after an update) leaves the
        // saved session alone, to be read at the next start.
        if (gone(e)) prefs.edit().clear().apply()
        Saved.Nobody
    }

    private fun gone(e: Exception): Boolean =
        e is javax.crypto.AEADBadTagException || e is java.security.UnrecoverableKeyException ||
            e is android.security.keystore.KeyPermanentlyInvalidatedException ||
            e is IllegalArgumentException || e is kotlinx.serialization.SerializationException

    @Synchronized
    override fun save(saved: Saved) {
        val edit = prefs.edit().clear()
        when (saved) {
            Saved.Nobody -> Unit
            Saved.Demo -> edit.putString(MODE, DEMO)
            is Saved.Account -> {
                val sealed = try {
                    val plain = AppJson.encodeToString(SealedAccount(saved.session, saved.me)).toByteArray(Charsets.UTF_8)
                    Base64.encodeToString(sealer.seal(plain), Base64.NO_WRAP)
                } catch (e: Exception) {
                    // The Keystore failed (it can, on some phones after an update): the session
                    // stays in memory for this run and is never written unsealed.
                    null
                }
                if (sealed != null) edit.putString(MODE, ACCOUNT).putString(SEALED, sealed)
            }
        }
        // commit, not apply: a session must be on disk before the next request can rotate it.
        edit.commit()
    }

    private companion object {
        const val MODE = "mode"
        const val SEALED = "sealed"
        const val DEMO = "demo"
        const val ACCOUNT = "account"
    }
}
