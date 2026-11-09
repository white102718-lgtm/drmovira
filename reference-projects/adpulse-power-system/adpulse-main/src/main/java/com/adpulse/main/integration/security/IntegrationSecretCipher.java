package com.adpulse.main.integration.security;

import com.adpulse.system.config.SecurityProperties;
import java.nio.ByteBuffer;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.security.SecureRandom;
import java.util.Base64;
import javax.crypto.Cipher;
import javax.crypto.spec.GCMParameterSpec;
import javax.crypto.spec.SecretKeySpec;
import org.springframework.stereotype.Component;

/** 使用AES-256-GCM加密第三方集成令牌与应用密钥。 */
@Component
public class IntegrationSecretCipher {
    private static final int IV_LENGTH = 12;
    private static final int TAG_BITS = 128;
    private final SecretKeySpec key;
    private final SecureRandom random = new SecureRandom();

    public IntegrationSecretCipher(SecurityProperties properties) {
        try {
            byte[] bytes =
                    MessageDigest.getInstance("SHA-256")
                            .digest(
                                    ("adpulse-integration:" + properties.jwtSecret())
                                            .getBytes(StandardCharsets.UTF_8));
            key = new SecretKeySpec(bytes, "AES");
        } catch (Exception exception) {
            throw new IllegalStateException("第三方密钥加密组件初始化失败", exception);
        }
    }

    /** 加密非空明文。 */
    public String encrypt(String plaintext) {
        try {
            byte[] iv = new byte[IV_LENGTH];
            random.nextBytes(iv);
            Cipher cipher = Cipher.getInstance("AES/GCM/NoPadding");
            cipher.init(Cipher.ENCRYPT_MODE, key, new GCMParameterSpec(TAG_BITS, iv));
            byte[] encrypted = cipher.doFinal(plaintext.getBytes(StandardCharsets.UTF_8));
            return Base64.getEncoder()
                    .encodeToString(
                            ByteBuffer.allocate(iv.length + encrypted.length)
                                    .put(iv)
                                    .put(encrypted)
                                    .array());
        } catch (Exception exception) {
            throw new IllegalStateException("第三方密钥加密失败", exception);
        }
    }

    /** 解密AES-GCM密文。 */
    public String decrypt(String encoded) {
        try {
            ByteBuffer buffer = ByteBuffer.wrap(Base64.getDecoder().decode(encoded));
            byte[] iv = new byte[IV_LENGTH];
            buffer.get(iv);
            byte[] encrypted = new byte[buffer.remaining()];
            buffer.get(encrypted);
            Cipher cipher = Cipher.getInstance("AES/GCM/NoPadding");
            cipher.init(Cipher.DECRYPT_MODE, key, new GCMParameterSpec(TAG_BITS, iv));
            return new String(cipher.doFinal(encrypted), StandardCharsets.UTF_8);
        } catch (Exception exception) {
            throw new IllegalStateException("第三方密钥解密失败", exception);
        }
    }
}
