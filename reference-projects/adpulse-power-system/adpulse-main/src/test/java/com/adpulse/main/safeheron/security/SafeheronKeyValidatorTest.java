package com.adpulse.main.safeheron.security;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import java.math.BigInteger;
import java.security.KeyFactory;
import java.security.KeyPair;
import java.security.KeyPairGenerator;
import java.security.interfaces.RSAPrivateCrtKey;
import java.security.spec.RSAPrivateCrtKeySpec;
import java.util.Base64;
import org.junit.jupiter.api.BeforeAll;
import org.junit.jupiter.api.Test;

/** 使用临时生成的密钥覆盖格式兼容与RSA签名自检，不使用真实凭证。 */
class SafeheronKeyValidatorTest {
    private static KeyPair pair;
    private static String body;

    @BeforeAll
    static void generateKey() throws Exception {
        var generator = KeyPairGenerator.getInstance("RSA");
        generator.initialize(2048);
        pair = generator.generateKeyPair();
        body = Base64.getEncoder().encodeToString(pair.getPrivate().getEncoded());
    }

    @Test
    void shouldAcceptRawPemAndEscapedNewlines() {
        assertThat(SafeheronKeyValidator.privateKey(body)).isEqualTo(body);
        for (String newline : new String[] {"\n", "\r\n", "\\n", "\\r\\n"}) {
            String pem =
                    "REDACTED_REFERENCE_SECRET";
            assertThat(SafeheronKeyValidator.privateKey(pem)).isEqualTo(body);
        }
    }

    @Test
    void shouldRejectMalformedAndUnsupportedKeys() {
        for (String invalid :
                new String[] {
                    null,
                    "",
                    "bad!",
                    body.substring(0, 80),
                    "REDACTED_REFERENCE_SECRET",
                    "REDACTED_REFERENCE_SECRET"
                }) {
            assertThatThrownBy(() -> SafeheronKeyValidator.privateKey(invalid))
                    .isInstanceOf(IllegalArgumentException.class)
                    .hasMessageContaining("私钥校验失败");
        }
    }

    @Test
    void shouldRejectParseableKeyWithCorruptedCrtParameters() throws Exception {
        var key = (RSAPrivateCrtKey) pair.getPrivate();
        var spec =
                new RSAPrivateCrtKeySpec(
                        key.getModulus(),
                        key.getPublicExponent(),
                        key.getPrivateExponent(),
                        key.getPrimeP(),
                        key.getPrimeQ(),
                        key.getPrimeExponentP().add(BigInteger.ONE),
                        key.getPrimeExponentQ(),
                        key.getCrtCoefficient());
        String corrupted =
                Base64.getEncoder()
                        .encodeToString(
                                KeyFactory.getInstance("RSA").generatePrivate(spec).getEncoded());
        assertThatThrownBy(() -> SafeheronKeyValidator.privateKey(corrupted))
                .isInstanceOf(IllegalArgumentException.class)
                .hasMessageContaining("私钥校验失败");
    }

    @Test
    void shouldValidatePlatformPublicKeyIndependently() {
        String publicBody = Base64.getEncoder().encodeToString(pair.getPublic().getEncoded());
        assertThat(
                        SafeheronKeyValidator.publicKey(
                                "-----BEGIN PUBLIC KEY-----\n"
                                        + publicBody
                                        + "\n-----END PUBLIC KEY-----"))
                .isEqualTo(publicBody);
        assertThatThrownBy(() -> SafeheronKeyValidator.publicKey(body))
                .isInstanceOf(IllegalArgumentException.class)
                .hasMessageContaining("公钥校验失败");
    }
}
