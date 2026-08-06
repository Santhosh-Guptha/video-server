package com.example.godownvision.security

import java.security.MessageDigest
import javax.crypto.Cipher
import javax.crypto.SecretKey
import javax.crypto.SecretKeyFactory
import javax.crypto.spec.GCMParameterSpec
import javax.crypto.spec.PBEKeySpec
import javax.crypto.spec.SecretKeySpec

object VaultCryptoEngine {
    private const val TRANSFORMATION = "AES/GCM/NoPadding"
    private const val GCM_TAG_LENGTH = 128
    private const val IV_LENGTH = 12
    private const val MASTER_SEED = "AEGIS_PERSISTENT_UNINSTALL_SAFE_VAULT_KEY_2026"
    private val MASTER_SALT = byteArrayOf(
        0x41.toByte(), 0x65.toByte(), 0x67.toByte(), 0x69.toByte(),
        0x73.toByte(), 0x53.toByte(), 0x65.toByte(), 0x63.toByte(),
        0x75.toByte(), 0x72.toByte(), 0x65.toByte(), 0x56.toByte(),
        0x61.toByte(), 0x75.toByte(), 0x6c.toByte(), 0x74.toByte()
    )

    private fun getSecretKey(): SecretKey {
        val factory = SecretKeyFactory.getInstance("PBKDF2WithHmacSHA256")
        val spec = PBEKeySpec(MASTER_SEED.toCharArray(), MASTER_SALT, 1000, 256)
        val tmp = factory.generateSecret(spec)
        return SecretKeySpec(tmp.encoded, "AES")
    }

    fun encrypt(plainText: String): ByteArray {
        val cipher = Cipher.getInstance(TRANSFORMATION)
        cipher.init(Cipher.ENCRYPT_MODE, getSecretKey())
        val iv = cipher.iv
        val cipherText = cipher.doFinal(plainText.toByteArray(Charsets.UTF_8))
        return iv + cipherText
    }

    fun decrypt(encryptedBytes: ByteArray): String {
        if (encryptedBytes.isEmpty()) return ""

        // Check if raw plaintext JSON
        val rawStr = String(encryptedBytes, Charsets.UTF_8)
        if (rawStr.trim().startsWith("{") && rawStr.trim().endsWith("}")) {
            return rawStr
        }

        if (encryptedBytes.size <= IV_LENGTH) return ""

        return try {
            val iv = encryptedBytes.copyOfRange(0, IV_LENGTH)
            val cipherText = encryptedBytes.copyOfRange(IV_LENGTH, encryptedBytes.size)

            val cipher = Cipher.getInstance(TRANSFORMATION)
            val gcmSpec = GCMParameterSpec(GCM_TAG_LENGTH, iv)
            cipher.init(Cipher.DECRYPT_MODE, getSecretKey(), gcmSpec)
            val plainBytes = cipher.doFinal(cipherText)
            String(plainBytes, Charsets.UTF_8)
        } catch (e: Exception) {
            ""
        }
    }

    fun hashPassword(password: String): String {
        val digest = MessageDigest.getInstance("SHA-256")
        val hash = digest.digest(password.toByteArray(Charsets.UTF_8))
        return hash.joinToString("") { "%02x".format(it) }
    }
}
