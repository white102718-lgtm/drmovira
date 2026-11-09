package com.ruoyi.system.orbit.config;

import com.fasterxml.jackson.core.type.TypeReference;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.SerializationFeature;
import com.ruoyi.system.orbit.config.ConfigurationModels.Row;
import java.security.MessageDigest;
import java.util.HexFormat;
import java.util.Map;
import java.util.TreeMap;

/** 审计状态摘要：凭据只摘要随机化密文信封，不解密、不生成可离线猜测的明文摘要。 */
public final class ConfigurationFingerprint {
    public static final String ALGORITHM = "SHA256_STATE_V1";
    private static final ObjectMapper JSON =
            new ObjectMapper().enable(SerializationFeature.ORDER_MAP_ENTRIES_BY_KEYS);

    private ConfigurationFingerprint() {}

    /** 固定版本的规范JSON涵盖对象归属、业务值、密文信封、版本与验证状态；排除数据库时间。 */
    public static String of(Row row) {
        byte[] bytes = null;
        try {
            Map<String, Object> snapshot = new TreeMap<>();
            snapshot.put("algorithm", ALGORITHM);
            snapshot.put("tenantId", row.tenantId);
            snapshot.put("id", row.id);
            snapshot.put("section", row.section);
            snapshot.put("name", row.name);
            snapshot.put("enabled", row.enabled);
            snapshot.put("revision", row.revision);
            snapshot.put("verificationStatus", row.verificationStatus);
            snapshot.put(
                    "settings",
                    JSON.readValue(row.settingsJson, new TypeReference<Map<String, Object>>() {}));
            snapshot.put(
                    "encryptedSecrets",
                    JSON.readValue(row.secretsJson, new TypeReference<Map<String, String>>() {}));
            bytes = JSON.writeValueAsBytes(snapshot);
            return HexFormat.of().formatHex(MessageDigest.getInstance("SHA-256").digest(bytes));
        } catch (Exception exception) {
            throw new ConfigurationException(500, "AUDIT_DIGEST_FAILED", "配置状态无法生成审计摘要，请联系管理员核查");
        } finally {
            if (bytes != null) java.util.Arrays.fill(bytes, (byte) 0);
        }
    }
}
