package com.ruoyi.system.orbit.config;

import static org.junit.jupiter.api.Assertions.*;

import com.ruoyi.system.orbit.config.ConfigurationModels.Row;
import java.time.Instant;
import org.junit.jupiter.api.Test;

/** 摘要的规范化、归属绑定与敏感值保护；不代替数据库事务验收。 */
class ConfigurationFingerprintTest {
    private Row fixture() {
        Row row = new Row();
        row.id = "config-a";
        row.tenantId = "tenant-a";
        row.section = "AI_GPT";
        row.name = "模型配置";
        row.revision = 1;
        row.settingsJson = "{\"model\":\"fixture\",\"timeout\":15}";
        row.secretsJson = "{\"apiKey\":\"v1.fixture.random-nonce.ciphertext\"}";
        row.verificationStatus = "UNTESTED";
        return row;
    }

    @Test
    void jsonOrderAndWhitespaceDoNotChangeDigest() {
        Row row = fixture();
        String digest = ConfigurationFingerprint.of(row);
        row.settingsJson = "{ \"timeout\": 15, \"model\": \"fixture\" }";
        assertEquals(digest, ConfigurationFingerprint.of(row));
        assertTrue(digest.matches("[a-f0-9]{64}"));
        row.updatedAt = Instant.now();
        row.verifiedAt = Instant.now();
        assertEquals(digest, ConfigurationFingerprint.of(row));
    }

    @Test
    void bindsIdentityRevisionAndEveryBusinessComponent() {
        String original = ConfigurationFingerprint.of(fixture());
        java.util.List<java.util.function.Consumer<Row>> changes =
                java.util.List.of(
                        row -> row.id = "config-b",
                        row -> row.tenantId = "tenant-b",
                        row -> row.section = "AI_CLAUDE",
                        row -> row.name = "另一个名称",
                        row -> row.enabled = true,
                        row -> row.revision = 2,
                        row -> row.verificationStatus = "READ_VERIFIED",
                        row -> row.settingsJson = "{\"model\":\"another\"}",
                        row -> row.secretsJson = "{}");
        for (var change : changes) {
            Row row = fixture();
            change.accept(row);
            assertNotEquals(original, ConfigurationFingerprint.of(row));
        }
    }

    @Test
    void malformedStoredDataFailsWithoutEchoingIt() {
        Row row = fixture();
        row.settingsJson = "fixture-private-input";
        ConfigurationException error =
                assertThrows(ConfigurationException.class, () -> ConfigurationFingerprint.of(row));
        assertFalse(error.getMessage().contains("fixture-private-input"));
        assertNull(error.getCause());
    }

    @Test
    void credentialEnvelopeRotationChangesDigestWithoutDecryption() {
        Row row = fixture();
        String original = ConfigurationFingerprint.of(row);
        row.secretsJson = "{\"apiKey\":\"v1.fixture.another-nonce.another-ciphertext\"}";
        assertNotEquals(original, ConfigurationFingerprint.of(row));
    }
}
