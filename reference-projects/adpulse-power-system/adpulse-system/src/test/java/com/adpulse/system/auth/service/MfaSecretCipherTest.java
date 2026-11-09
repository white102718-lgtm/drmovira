package com.adpulse.system.auth.service;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import com.adpulse.system.config.MfaProperties;
import java.time.Duration;
import org.junit.jupiter.api.Test;

/** MFA密钥AES-GCM保护测试。 */
class MfaSecretCipherTest {

    private static final String KEY = "MDEyMzQ1Njc4OWFiY2RlZjAxMjM0NTY3ODlhYmNkZWY=";

    @Test
    void shouldEncryptWithRandomIvAndDecrypt() {
        MfaSecretCipher cipher = cipher(KEY);
        String first = cipher.encrypt("JBSWY3DPEHPK3PXP");
        String second = cipher.encrypt("JBSWY3DPEHPK3PXP");

        assertThat(first).isNotEqualTo(second);
        assertThat(cipher.decrypt(first)).isEqualTo("JBSWY3DPEHPK3PXP");
        assertThat(cipher.decrypt(second)).isEqualTo("JBSWY3DPEHPK3PXP");
    }

    @Test
    void shouldRejectInvalidKeyLength() {
        assertThatThrownBy(() -> cipher("c2hvcnQ="))
                .isInstanceOf(IllegalStateException.class)
                .hasMessageContaining("32字节");
    }

    private MfaSecretCipher cipher(String key) {
        return new MfaSecretCipher(new MfaProperties(key, "AdPulse", Duration.ofMinutes(5), 5));
    }
}
