package com.adpulse.system.auth.service;

import com.adpulse.system.config.MfaProperties;
import java.nio.ByteBuffer;
import java.nio.charset.StandardCharsets;
import java.security.GeneralSecurityException;
import java.security.SecureRandom;
import java.util.Base64;
import javax.crypto.Cipher;
import javax.crypto.spec.GCMParameterSpec;
import javax.crypto.spec.SecretKeySpec;
import org.springframework.stereotype.Component;

/** 使用AES-256-GCM加密数据库和Redis中的MFA密钥。 */
@Component
public class MfaSecretCipher {

    private static final int IV_LENGTH = 12;
    private static final int TAG_LENGTH_BITS = 128;

    private final SecretKeySpec key;
    private final SecureRandom secureRandom = new SecureRandom();

    public MfaSecretCipher(MfaProperties properties) {
        byte[] keyBytes;
        try {
            keyBytes = Base64.getDecoder().decode(properties.encryptionKey());
        } catch (IllegalArgumentException exception) {
            throw new IllegalStateException("MFA_ENCRYPTION_KEY必须是Base64编码的32字节密钥", exception);
        }
        if (keyBytes.length != 32) {
            throw new IllegalStateException("MFA_ENCRYPTION_KEY解码后必须为32字节");
        }
        this.key = new SecretKeySpec(keyBytes, "AES");
    }

    /** 加密MFA明文密钥，每次使用独立随机IV。 */
    public String encrypt(String plaintext) {
        byte[] iv = new byte[IV_LENGTH];
        secureRandom.nextBytes(iv);
        try {
            Cipher cipher = Cipher.getInstance("AES/GCM/NoPadding");
            cipher.init(Cipher.ENCRYPT_MODE, key, new GCMParameterSpec(TAG_LENGTH_BITS, iv));
            byte[] ciphertext = cipher.doFinal(plaintext.getBytes(StandardCharsets.UTF_8));
            return Base64.getEncoder()
                    .encodeToString(
                            ByteBuffer.allocate(iv.length + ciphertext.length)
                                    .put(iv)
                                    .put(ciphertext)
                                    .array());
        } catch (GeneralSecurityException exception) {
            throw new IllegalStateException("无法加密MFA密钥", exception);
        }
    }

    /** 解密MFA密钥；密钥配置不匹配或密文损坏时拒绝继续认证。 */
    public String decrypt(String encoded) {
        try {
            byte[] payload = Base64.getDecoder().decode(encoded);
            if (payload.length <= IV_LENGTH) {
                throw new IllegalArgumentException("MFA密文长度非法");
            }
            ByteBuffer buffer = ByteBuffer.wrap(payload);
            byte[] iv = new byte[IV_LENGTH];
            buffer.get(iv);
            byte[] ciphertext = new byte[buffer.remaining()];
            buffer.get(ciphertext);
            Cipher cipher = Cipher.getInstance("AES/GCM/NoPadding");
            cipher.init(Cipher.DECRYPT_MODE, key, new GCMParameterSpec(TAG_LENGTH_BITS, iv));
            return new String(cipher.doFinal(ciphertext), StandardCharsets.UTF_8);
        } catch (GeneralSecurityException | IllegalArgumentException exception) {
            throw new IllegalStateException("无法解密MFA密钥", exception);
        }
    }
}
