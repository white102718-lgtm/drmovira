package com.adpulse.system.auth.service;

import com.adpulse.system.config.MfaProperties;
import java.net.URLEncoder;
import java.nio.ByteBuffer;
import java.nio.charset.StandardCharsets;
import java.security.GeneralSecurityException;
import java.security.MessageDigest;
import java.security.SecureRandom;
import java.time.Instant;
import java.util.Locale;
import java.util.OptionalLong;
import javax.crypto.Mac;
import javax.crypto.spec.SecretKeySpec;
import org.springframework.stereotype.Component;

/** RFC 6238兼容的六位TOTP密钥和动态码服务。 */
@Component
public class TotpService {

    private static final String BASE32_ALPHABET = "ABCDEFGHIJKLMNOPQRSTUVWXYZ234567";
    private static final long STEP_SECONDS = 30;
    private static final int SECRET_BYTES = 20;

    private final SecureRandom secureRandom = new SecureRandom();
    private final MfaProperties properties;

    public TotpService(MfaProperties properties) {
        this.properties = properties;
    }

    /** 生成160位随机Base32密钥。 */
    public String generateSecret() {
        byte[] bytes = new byte[SECRET_BYTES];
        secureRandom.nextBytes(bytes);
        return encodeBase32(bytes);
    }

    /** 创建验证器应用可识别的otpauth URI。 */
    public String buildOtpAuthUri(String account, String secret) {
        String issuer = urlEncode(properties.issuer());
        String label = issuer + ":" + urlEncode(account);
        return "otpauth://totp/"
                + label
                + "?secret="
                + secret
                + "&issuer="
                + issuer
                + "&algorithm=SHA1&digits=6&period=30";
    }

    /** 验证当前时间前后一个窗口，并返回命中的时间计数器用于防重放。 */
    public OptionalLong verify(String secret, String code) {
        long currentCounter = Instant.now().getEpochSecond() / STEP_SECONDS;
        for (long counter = currentCounter - 1; counter <= currentCounter + 1; counter++) {
            String expected = generateCode(secret, counter);
            if (MessageDigest.isEqual(
                    expected.getBytes(StandardCharsets.US_ASCII),
                    code.getBytes(StandardCharsets.US_ASCII))) {
                return OptionalLong.of(counter);
            }
        }
        return OptionalLong.empty();
    }

    String generateCode(String secret, long counter) {
        try {
            Mac mac = Mac.getInstance("HmacSHA1");
            mac.init(new SecretKeySpec(decodeBase32(secret), "HmacSHA1"));
            byte[] hash = mac.doFinal(ByteBuffer.allocate(Long.BYTES).putLong(counter).array());
            int offset = hash[hash.length - 1] & 0x0f;
            int binary =
                    ((hash[offset] & 0x7f) << 24)
                            | ((hash[offset + 1] & 0xff) << 16)
                            | ((hash[offset + 2] & 0xff) << 8)
                            | (hash[offset + 3] & 0xff);
            return String.format(Locale.ROOT, "%06d", binary % 1_000_000);
        } catch (GeneralSecurityException exception) {
            throw new IllegalStateException("无法计算TOTP动态码", exception);
        }
    }

    private String encodeBase32(byte[] source) {
        StringBuilder result = new StringBuilder((source.length * 8 + 4) / 5);
        int buffer = 0;
        int bitsLeft = 0;
        for (byte value : source) {
            buffer = (buffer << 8) | (value & 0xff);
            bitsLeft += 8;
            while (bitsLeft >= 5) {
                result.append(BASE32_ALPHABET.charAt((buffer >> (bitsLeft - 5)) & 0x1f));
                bitsLeft -= 5;
            }
        }
        if (bitsLeft > 0) {
            result.append(BASE32_ALPHABET.charAt((buffer << (5 - bitsLeft)) & 0x1f));
        }
        return result.toString();
    }

    private byte[] decodeBase32(String value) {
        String normalized = value.replace("=", "").toUpperCase(Locale.ROOT);
        byte[] result = new byte[normalized.length() * 5 / 8];
        int buffer = 0;
        int bitsLeft = 0;
        int index = 0;
        for (char character : normalized.toCharArray()) {
            int digit = BASE32_ALPHABET.indexOf(character);
            if (digit < 0) {
                throw new IllegalArgumentException("非法MFA Base32密钥");
            }
            buffer = (buffer << 5) | digit;
            bitsLeft += 5;
            if (bitsLeft >= 8) {
                result[index++] = (byte) ((buffer >> (bitsLeft - 8)) & 0xff);
                bitsLeft -= 8;
            }
        }
        return result;
    }

    private String urlEncode(String value) {
        return URLEncoder.encode(value, StandardCharsets.UTF_8).replace("+", "%20");
    }
}
