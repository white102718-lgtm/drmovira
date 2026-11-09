package com.ruoyi.system.orbit.config;

import static org.junit.jupiter.api.Assertions.*;

import java.util.Base64;
import java.util.Map;
import org.junit.jupiter.api.Test;

/** 使用生成的测试密钥验证机密性、认证绑定、轮换及安全失败；无真实凭据。 */
class SecretCipherTest {
    private final String oldKey = Base64.getEncoder().encodeToString(new byte[32]);
    private final String newKey =
            Base64.getEncoder()
                    .encodeToString(
                            "0123456789abcdef0123456789abcdef"
                                    .getBytes(java.nio.charset.StandardCharsets.UTF_8));

    private SecretCipher cipher() {
        return new SecretCipher("key1", Map.of("key1", oldKey));
    }

    @Test
    void encryptsWithRandomNonceAndRoundTripsUnicode() {
        SecretCipher cipher = cipher();
        String value = "fixture-only-token-中文";
        String first = cipher.encrypt(value, "tenant", "config", "apiKey");
        String second = cipher.encrypt(value, "tenant", "config", "apiKey");
        assertNotEquals(first, second);
        assertFalse(first.contains(value));
        assertEquals(value, cipher.decrypt(first, "tenant", "config", "apiKey"));
    }

    @Test
    void rejectsCrossTenantConfigAndSlotCopies() {
        SecretCipher cipher = cipher();
        String encrypted = cipher.encrypt("fixture", "tenant", "config", "token");
        assertThrows(
                IllegalStateException.class,
                () -> cipher.decrypt(encrypted, "other", "config", "token"));
        assertThrows(
                IllegalStateException.class,
                () -> cipher.decrypt(encrypted, "tenant", "other", "token"));
        assertThrows(
                IllegalStateException.class,
                () -> cipher.decrypt(encrypted, "tenant", "config", "other"));
    }

    @Test
    void rejectsCiphertextAndNonceTamperingWithoutLeakingInput() {
        SecretCipher cipher = cipher();
        String encrypted = cipher.encrypt("fixture-sensitive", "tenant", "config", "token");
        String[] parts = encrypted.split("\\.");
        byte[] ciphertext = Base64.getUrlDecoder().decode(parts[3]);
        ciphertext[0] ^= 1;
        String modified =
                parts[0]
                        + "."
                        + parts[1]
                        + "."
                        + parts[2]
                        + "."
                        + Base64.getUrlEncoder().withoutPadding().encodeToString(ciphertext);
        IllegalStateException error =
                assertThrows(
                        IllegalStateException.class,
                        () -> cipher.decrypt(modified, "tenant", "config", "token"));
        assertFalse(error.getMessage().contains("fixture-sensitive"));
        assertNull(error.getCause());
    }

    @Test
    void supportsRotationWhileOldKeyRemainsReadable() {
        String encrypted = cipher().encrypt("fixture", "tenant", "config", "token");
        SecretCipher rotated = new SecretCipher("key2", Map.of("key1", oldKey, "key2", newKey));
        assertEquals("fixture", rotated.decrypt(encrypted, "tenant", "config", "token"));
        String renewed = rotated.reencrypt(encrypted, "tenant", "config", "token");
        assertTrue(renewed.startsWith("v1.key2."));
        assertEquals(
                "fixture",
                new SecretCipher("key2", Map.of("key2", newKey))
                        .decrypt(renewed, "tenant", "config", "token"));
        assertThrows(
                IllegalStateException.class,
                () ->
                        new SecretCipher("key2", Map.of("key2", newKey))
                                .decrypt(encrypted, "tenant", "config", "token"));
    }

    @Test
    void missingMasterKeyFailsClosed() {
        SecretCipher missing = new SecretCipher(null, Map.of());
        assertFalse(missing.isReady());
        assertThrows(
                IllegalStateException.class,
                () -> missing.encrypt("fixture", "tenant", "config", "token"));
        assertThrows(
                IllegalStateException.class,
                () -> missing.decrypt("fixture", "tenant", "config", "token"));
    }

    @Test
    void invalidKeyCannotStartSecretService() {
        assertThrows(
                IllegalStateException.class,
                () -> new SecretCipher("key1", Map.of("key1", "invalid")));
        assertThrows(
                IllegalStateException.class,
                () -> new SecretCipher("unknown", Map.of("key1", oldKey)));
        assertThrows(
                IllegalStateException.class,
                () -> new SecretCipher("bad.id", Map.of("bad.id", oldKey)));
    }

    @Test
    void rejectsMalformedOrUnknownVersionEnvelopes() {
        for (String encrypted :
                new String[] {
                    "", "v1.unknown.a.b", "v2.key1.a.b", "v1.key1.a.b", "v1.key1.@@@.@@@"
                }) {
            assertThrows(
                    IllegalStateException.class,
                    () -> cipher().decrypt(encrypted, "tenant", "config", "token"));
        }
    }
}
