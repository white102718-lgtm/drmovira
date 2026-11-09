package com.ruoyi.system.orbit.config;

import java.nio.ByteBuffer;
import java.nio.charset.StandardCharsets;
import java.security.GeneralSecurityException;
import java.security.SecureRandom;
import java.util.Base64;
import java.util.HashMap;
import java.util.Map;
import javax.crypto.Cipher;
import javax.crypto.spec.GCMParameterSpec;
import javax.crypto.spec.SecretKeySpec;

/** 独立主密钥的凭据认证加密；密文绑定租户、配置和字段，禁止跨对象复制使用。 */
public final class SecretCipher {
    private static final int NONCE_BYTES = 12;
    private final String activeKeyId;
    private final Map<String, SecretKeySpec> keys;
    private final SecureRandom random = new SecureRandom();

    /** 主密钥必须为独立随机生成的32字节Base64值，不得从JWT密钥或密码派生。 */
    public SecretCipher(String activeKeyId, Map<String, String> encodedKeys) {
        this.activeKeyId = activeKeyId;
        Map<String, SecretKeySpec> parsed = new HashMap<>();
        try {
            for (Map.Entry<String, String> entry : encodedKeys.entrySet()) {
                if (!entry.getKey().matches("[A-Za-z0-9_-]{1,40}")) {
                    throw new IllegalArgumentException();
                }
                byte[] key = Base64.getDecoder().decode(entry.getValue());
                if (key.length != 32) {
                    throw new IllegalArgumentException();
                }
                parsed.put(entry.getKey(), new SecretKeySpec(key, "AES"));
                java.util.Arrays.fill(key, (byte) 0);
            }
            if (!parsed.isEmpty() && !parsed.containsKey(activeKeyId)) {
                throw new IllegalArgumentException();
            }
        } catch (IllegalArgumentException | NullPointerException exception) {
            // 不带原异常或输入值，防止配置错误时将密钥写入日志。
            throw new IllegalStateException("凭据主密钥配置无效，请检查独立32字节密钥与key_id");
        }
        keys = Map.copyOf(parsed);
    }

    /** 无主密钥时允许系统启动及查看脱敏配置，但禁止凭据加密或解密。 */
    public boolean isReady() {
        return activeKeyId != null && keys.containsKey(activeKeyId);
    }

    /** 加密同一明文也使用不同nonce；完整性标签同时保护对象身份。 */
    public String encrypt(String plaintext, String tenantId, String configId, String slot) {
        requireReady();
        byte[] bytes = plaintext.getBytes(StandardCharsets.UTF_8);
        try {
            byte[] nonce = new byte[NONCE_BYTES];
            random.nextBytes(nonce);
            Cipher cipher = Cipher.getInstance("AES/GCM/NoPadding");
            cipher.init(
                    Cipher.ENCRYPT_MODE, keys.get(activeKeyId), new GCMParameterSpec(128, nonce));
            cipher.updateAAD(aad(tenantId, configId, slot));
            return "v1." + activeKeyId + "." + encode(nonce) + "." + encode(cipher.doFinal(bytes));
        } catch (GeneralSecurityException exception) {
            throw new IllegalStateException("凭据加密失败");
        } finally {
            java.util.Arrays.fill(bytes, (byte) 0);
        }
    }

    /** 解密只供服务端Adapter内部使用；禁止在响应、日志或审计中返回明文。 */
    public String decrypt(String encrypted, String tenantId, String configId, String slot) {
        requireReady();
        byte[] plaintext = null;
        try {
            String[] parts = encrypted.split("\\.", -1);
            if (parts.length != 4 || !"v1".equals(parts[0]) || !keys.containsKey(parts[1])) {
                throw new IllegalArgumentException();
            }
            byte[] nonce = Base64.getUrlDecoder().decode(parts[2]);
            if (nonce.length != NONCE_BYTES) {
                throw new IllegalArgumentException();
            }
            Cipher cipher = Cipher.getInstance("AES/GCM/NoPadding");
            cipher.init(Cipher.DECRYPT_MODE, keys.get(parts[1]), new GCMParameterSpec(128, nonce));
            cipher.updateAAD(aad(tenantId, configId, slot));
            plaintext = cipher.doFinal(Base64.getUrlDecoder().decode(parts[3]));
            return new String(plaintext, StandardCharsets.UTF_8);
        } catch (GeneralSecurityException
                | IllegalArgumentException
                | NullPointerException exception) {
            throw new IllegalStateException("凭据无法解密或完整性校验失败，请检查密钥版本与对象归属");
        } finally {
            if (plaintext != null) {
                java.util.Arrays.fill(plaintext, (byte) 0);
            }
        }
    }

    /** 旧key保留读取能力，使用当前key重新加密；持久化与审计由事务服务负责。 */
    public String reencrypt(String encrypted, String tenantId, String configId, String slot) {
        return encrypt(decrypt(encrypted, tenantId, configId, slot), tenantId, configId, slot);
    }

    private void requireReady() {
        if (!isReady()) {
            throw new IllegalStateException("服务端尚未配置凭据主密钥，密钥操作已禁用");
        }
    }

    private static String encode(byte[] value) {
        return Base64.getUrlEncoder().withoutPadding().encodeToString(value);
    }

    private static byte[] aad(String tenantId, String configId, String slot) {
        byte[][] values = {
            tenantId.getBytes(StandardCharsets.UTF_8),
            configId.getBytes(StandardCharsets.UTF_8),
            slot.getBytes(StandardCharsets.UTF_8)
        };
        int size = 0;
        for (byte[] value : values) {
            size += Integer.BYTES + value.length;
        }
        ByteBuffer buffer = ByteBuffer.allocate(size);
        for (byte[] value : values) {
            buffer.putInt(value.length).put(value);
        }
        return buffer.array();
    }
}
