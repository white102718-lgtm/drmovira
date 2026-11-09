package com.adpulse.main.google.security;

import com.adpulse.system.config.SecurityProperties;
import java.nio.charset.StandardCharsets;
import java.time.Instant;
import java.util.Base64;
import javax.crypto.Mac;
import javax.crypto.spec.SecretKeySpec;
import org.springframework.stereotype.Component;

/** 签发并验证十分钟有效的Google OAuth state，防止伪造回调。 */
@Component
public class GoogleOAuthState {
    private final SecretKeySpec key;

    public GoogleOAuthState(SecurityProperties properties) {
        key =
                new SecretKeySpec(
                        properties.jwtSecret().getBytes(StandardCharsets.UTF_8), "HmacSHA256");
    }

    /** 为当前用户签发OAuth state。 */
    public String issue(Long actorId) {
        String payload = actorId + ":" + Instant.now().getEpochSecond();
        return encode(payload) + "." + encode(sign(payload));
    }

    /** 验证OAuth state并返回发起用户ID。 */
    public Long verify(String state) {
        try {
            String[] parts = state.split("\\.");
            if (parts.length != 2) throw new IllegalArgumentException();
            String payload =
                    new String(Base64.getUrlDecoder().decode(parts[0]), StandardCharsets.UTF_8);
            if (!java.security.MessageDigest.isEqual(
                    sign(payload), Base64.getUrlDecoder().decode(parts[1])))
                throw new IllegalArgumentException();
            String[] values = payload.split(":");
            long issuedAt = Long.parseLong(values[1]);
            long ageSeconds = Instant.now().getEpochSecond() - issuedAt;
            if (ageSeconds > 600 || ageSeconds < -60) throw new IllegalArgumentException();
            return Long.parseLong(values[0]);
        } catch (Exception exception) {
            throw new IllegalArgumentException("Google授权状态已失效，请重新发起授权");
        }
    }

    private byte[] sign(String value) {
        try {
            Mac mac = Mac.getInstance("HmacSHA256");
            mac.init(key);
            return mac.doFinal(value.getBytes(StandardCharsets.UTF_8));
        } catch (Exception exception) {
            throw new IllegalStateException("OAuth state签名失败", exception);
        }
    }

    private String encode(String value) {
        return encode(value.getBytes(StandardCharsets.UTF_8));
    }

    private String encode(byte[] value) {
        return Base64.getUrlEncoder().withoutPadding().encodeToString(value);
    }
}
