package com.adpulse.main.safeheron.security;

import java.nio.charset.StandardCharsets;
import java.security.SecureRandom;
import java.util.Base64;
import javax.crypto.Cipher;
import javax.crypto.spec.GCMParameterSpec;
import javax.crypto.spec.SecretKeySpec;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Component;

/** 兼容旧系统格式的Safeheron数据库敏感字段AES-256-GCM保护组件。 */
@Component
public class SafeheronSecretCipher {
    private static final int IV_LENGTH = 12;
    private static final int TAG_BITS = 128;
    private final String masterKeyBase64;
    private final SecureRandom random = new SecureRandom();

    public SafeheronSecretCipher(@Value("${safeheron.master-key:}") String masterKeyBase64) {
        this.masterKeyBase64 = masterKeyBase64;
    }

    /** 加密非空明文，输出与旧系统一致的iv:data格式。 */
    public String encrypt(String plaintext) {
        try {
            byte[] iv = new byte[IV_LENGTH];
            random.nextBytes(iv);
            Cipher cipher = Cipher.getInstance("AES/GCM/NoPadding");
            cipher.init(Cipher.ENCRYPT_MODE, key(), new GCMParameterSpec(TAG_BITS, iv));
            byte[] encrypted = cipher.doFinal(plaintext.getBytes(StandardCharsets.UTF_8));
            return Base64.getEncoder().encodeToString(iv)
                    + ":"
                    + Base64.getEncoder().encodeToString(encrypted);
        } catch (SafeheronSecretException exception) {
            throw exception;
        } catch (Exception exception) {
            throw new SafeheronSecretException("Safeheron敏感字段加密失败", exception);
        }
    }

    /** 解密旧系统iv:data格式的密文。 */
    public String decrypt(String encoded) {
        try {
            String[] parts = encoded.split(":", 2);
            if (parts.length != 2) throw new IllegalArgumentException("密文格式错误");
            byte[] iv = Base64.getDecoder().decode(parts[0]);
            byte[] encrypted = Base64.getDecoder().decode(parts[1]);
            Cipher cipher = Cipher.getInstance("AES/GCM/NoPadding");
            cipher.init(Cipher.DECRYPT_MODE, key(), new GCMParameterSpec(TAG_BITS, iv));
            return new String(cipher.doFinal(encrypted), StandardCharsets.UTF_8);
        } catch (SafeheronSecretException exception) {
            throw exception;
        } catch (Exception exception) {
            throw new SafeheronSecretException("Safeheron敏感字段解密失败", exception);
        }
    }

    private SecretKeySpec key() {
        if (masterKeyBase64 == null || masterKeyBase64.isBlank()) {
            throw new SafeheronSecretException("SAFEHERON_MASTER_KEY未配置");
        }
        byte[] decoded;
        try {
            decoded = Base64.getDecoder().decode(masterKeyBase64.trim());
        } catch (IllegalArgumentException exception) {
            throw new SafeheronSecretException("SAFEHERON_MASTER_KEY不是有效Base64", exception);
        }
        if (decoded.length != 32) {
            throw new SafeheronSecretException("SAFEHERON_MASTER_KEY解码后必须为32字节");
        }
        return new SecretKeySpec(decoded, "AES");
    }

    /** 不包含密钥内容的Safeheron加解密异常。 */
    public static class SafeheronSecretException extends RuntimeException {
        public SafeheronSecretException(String message) {
            super(message);
        }

        public SafeheronSecretException(String message, Throwable cause) {
            super(message, cause);
        }
    }
}
