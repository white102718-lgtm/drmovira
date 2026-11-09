package com.adpulse.main.safeheron.security;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import java.util.Base64;
import org.junit.jupiter.api.Test;

/** Safeheron旧库密文格式兼容测试。 */
class SafeheronSecretCipherTest {
    @Test
    void shouldRoundTripUsingLegacyIvAndCiphertextFormat() {
        String masterKey = Base64.getEncoder().encodeToString(new byte[32]);
        SafeheronSecretCipher cipher = new SafeheronSecretCipher(masterKey);

        String encrypted = cipher.encrypt("private-key");

        assertThat(encrypted).contains(":").doesNotContain("private-key");
        assertThat(cipher.decrypt(encrypted)).isEqualTo("private-key");
    }

    @Test
    void shouldRejectMissingMasterKeyWithoutExposingSecretInput() {
        SafeheronSecretCipher cipher = new SafeheronSecretCipher("");

        assertThatThrownBy(() -> cipher.encrypt("private-key"))
                .isInstanceOf(SafeheronSecretCipher.SafeheronSecretException.class)
                .hasMessageContaining("SAFEHERON_MASTER_KEY");
    }
}
