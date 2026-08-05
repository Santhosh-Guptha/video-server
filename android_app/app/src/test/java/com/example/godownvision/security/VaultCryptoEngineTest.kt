package com.example.godownvision.security

import org.junit.Assert.assertEquals
import org.junit.Assert.assertNotEquals
import org.junit.Assert.assertTrue
import org.junit.Test

class VaultCryptoEngineTest {

    @Test
    fun testPasswordHashingConsistency() {
        val rawPassword = "Admin@123"
        val hash1 = VaultCryptoEngine.hashPassword(rawPassword)
        val hash2 = VaultCryptoEngine.hashPassword(rawPassword)

        assertEquals(hash1, hash2)
        assertNotEquals(rawPassword, hash1)
        assertEquals(64, hash1.length) // SHA-256 hex string length is 64 chars
    }

    @Test
    fun testDifferentPasswordsProduceDifferentHashes() {
        val hash1 = VaultCryptoEngine.hashPassword("Admin@123")
        val hash2 = VaultCryptoEngine.hashPassword("Operator@123")

        assertNotEquals(hash1, hash2)
    }

    @Test
    fun testSecurityAnswerNormalizationAndHashing() {
        val answerInput1 = "  Fluffy  "
        val answerInput2 = "fluffy"

        val hash1 = VaultCryptoEngine.hashPassword(answerInput1.trim().lowercase())
        val hash2 = VaultCryptoEngine.hashPassword(answerInput2.trim().lowercase())

        assertEquals(hash1, hash2)
    }
}
