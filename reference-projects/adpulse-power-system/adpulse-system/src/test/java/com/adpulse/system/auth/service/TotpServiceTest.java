package com.adpulse.system.auth.service;

import static org.assertj.core.api.Assertions.assertThat;

import com.adpulse.system.config.MfaProperties;
import java.time.Duration;
import org.junit.jupiter.api.Test;

/** TOTP标准向量和密钥格式测试。 */
class TotpServiceTest {

    private final TotpService service =
            new TotpService(new MfaProperties("unused", "AdPulse", Duration.ofMinutes(5), 5));

    @Test
    void shouldMatchRfc6238Sha1VectorAsSixDigits() {
        String secret = "REDACTED_REFERENCE_SECRET";

        assertThat(service.generateCode(secret, 1)).isEqualTo("287082");
    }

    @Test
    void shouldGenerateAuthenticatorCompatibleSecretAndUri() {
        String secret = service.generateSecret();

        assertThat(secret).hasSize(32).matches("[A-Z2-7]+");
        assertThat(service.buildOtpAuthUri("admin@example.com", secret))
                .startsWith("otpauth://totp/AdPulse:admin%40example.com")
                .contains("secret=" + secret)
                .contains("issuer=AdPulse");
    }
}
