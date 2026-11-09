package com.adpulse.system.feishuorg.security;

import static org.assertj.core.api.Assertions.assertThat;

import com.adpulse.system.config.SecurityProperties;
import java.time.Duration;
import org.junit.jupiter.api.Test;

/** 飞书应用密钥兼容加解密测试。 */
class FeishuSecretCipherTest {

    @Test
    void shouldEncryptWithoutExposingPlaintextAndDecryptBack() {
        FeishuSecretCipher cipher =
                new FeishuSecretCipher(
                        new SecurityProperties("jwt-secret", "issuer", Duration.ofHours(8)));

        String encrypted = cipher.encrypt("app-secret");

        assertThat(encrypted).doesNotContain("app-secret");
        assertThat(cipher.decrypt(encrypted)).isEqualTo("app-secret");
    }
}
