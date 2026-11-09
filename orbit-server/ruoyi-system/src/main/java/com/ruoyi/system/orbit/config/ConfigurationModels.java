package com.ruoyi.system.orbit.config;

import com.fasterxml.jackson.annotation.JsonIgnore;
import java.time.Instant;
import java.util.List;
import java.util.Map;

/** 系统配置输入、脱敏输出与持久化模型严格分开。 */
public final class ConfigurationModels {
    private ConfigurationModels() {}

    /** 密钥保持、替换、清除明确区分；toString不打印输入值。 */
    public record SecretChange(String operation, String value) {
        @Override
        public String toString() {
            return "SecretChange[REDACTED]";
        }
    }

    /** 公开settings只接受Catalog白名单，密钥单独一次性提交。 */
    public record WriteRequest(
            String section,
            String name,
            boolean enabled,
            Map<String, Object> settings,
            Map<String, SecretChange> secrets,
            String reason) {
        @Override
        public String toString() {
            return "WriteRequest[REDACTED]";
        }
    }

    /** 前端只知道是否已配置，不能拿到明文或密文。 */
    public record SecretState(boolean configured, String hint) {}

    public record View(
            String id,
            String section,
            String name,
            boolean enabled,
            long revision,
            Map<String, Object> settings,
            Map<String, SecretState> secrets,
            String verificationStatus,
            Instant verifiedAt,
            Instant updatedAt) {}

    /** 历史只包含操作元数据，不包含配置值、明文或密文。 */
    public record AuditView(
            String id,
            Long actorId,
            String action,
            long revision,
            Long beforeRevision,
            String beforeHash,
            String afterHash,
            String hashAlgorithm,
            List<String> changedFields,
            String reason,
            Instant createdAt) {}

    /** 审计写入仅接收元数据与状态摘要，不接收原始请求或配置快照。 */
    public record AuditWrite(
            String id,
            String tenantId,
            String configId,
            Long actorId,
            String action,
            long revision,
            long beforeRevision,
            String beforeHash,
            String afterHash,
            String hashAlgorithm,
            String changedFieldsJson,
            String reason) {}

    public record AuditPage(List<AuditView> items, Long nextBeforeRevision) {}

    public static final class AuditRow {
        public String id;
        public Long actorId;
        public String action;
        public long revision;
        public Long beforeRevision;
        public String beforeHash;
        public String afterHash;
        public String hashAlgorithm;
        public String changedFieldsJson;
        public String reason;
        public Instant createdAt;
    }

    /** 仅Mapper内部使用，禁止把此对象作为Controller返回值。 */
    public static final class Row {
        public String id;
        public String tenantId;
        public String section;
        public String name;
        public boolean enabled;
        public long revision;
        public String settingsJson;
        @JsonIgnore public String secretsJson;
        public String verificationStatus;
        public Instant verifiedAt;
        public Instant updatedAt;
    }

    /** 服务端按当前会话映射租户，不能使用请求中的tenant_id。 */
    public record Principal(String tenantId, String dataRole) {}

    /** 幂等记录只存请求hash与已脱敏响应，绝不存原密钥请求体。 */
    public static final class IdempotencyRow {
        public String payloadHash;
        public String responseJson;
    }
}
