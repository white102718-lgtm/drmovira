package com.adpulse.system.feishuorg.security;

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

/** 加解密飞书应用配置密文，与主服务的集成密钥算法保持兼容。 */
@Component
public class FeishuSecretCipher {
    private static final int IV_LENGTH = 12;
    private static final int TAG_BITS = 128;
    private final SecureRandom secureRandom = new SecureRandom();
    private final SecretKeySpec key;

    public FeishuSecretCipher(SecurityProperties properties) {
        try {
            byte[] bytes =
                    MessageDigest.getInstance("SHA-256")
                            .digest(
                                    ("adpulse-integration:" + properties.jwtSecret())
                                            .getBytes(StandardCharsets.UTF_8));
            key = new SecretKeySpec(bytes, "AES");
        } catch (Exception exception) {
            throw new IllegalStateException("飞书应用密钥解密组件初始化失败", exception);
        }
    }

    /** 解密 feishu_app_config 中保存的 AES-GCM 密文。 */
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
            throw new IllegalStateException("飞书应用密钥解密失败", exception);
        }
    }

    /** 使用与主服务相同的AES-GCM格式加密飞书应用密钥。 */
    public String encrypt(String plaintext) {
        try {
            byte[] iv = new byte[IV_LENGTH];
            secureRandom.nextBytes(iv);
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
            throw new IllegalStateException("飞书应用密钥加密失败", exception);
        }
    }
}
