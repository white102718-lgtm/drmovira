package com.ruoyi.system.orbit.config;

import com.fasterxml.jackson.core.type.TypeReference;
import com.fasterxml.jackson.databind.DeserializationFeature;
import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.MapperFeature;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.ruoyi.common.utils.SecurityUtils;
import com.ruoyi.system.orbit.config.ConfigurationModels.*;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Set;
import java.util.UUID;
import org.springframework.stereotype.Service;
import org.springframework.transaction.PlatformTransactionManager;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.transaction.support.TransactionTemplate;

/** 租户隔离的系统配置服务，版本CAS、密钥加密和脱敏审计同事务提交。 */
@Service
public class ConfigurationService {
    private final ConfigurationMapper repository;
    private final SecretCipher cipher;
    private final ObjectMapper json;
    private final ConnectionProbe probe;
    private final TransactionTemplate transactions;

    public ConfigurationService(
            ConfigurationMapper repository,
            SecretCipher cipher,
            ObjectMapper json,
            ConnectionProbe probe,
            PlatformTransactionManager manager) {
        this.repository = repository;
        this.cipher = cipher;
        this.json =
                json.copy()
                        .enable(DeserializationFeature.FAIL_ON_UNKNOWN_PROPERTIES)
                        .enable(
                                com.fasterxml.jackson.databind.SerializationFeature
                                        .ORDER_MAP_ENTRIES_BY_KEYS)
                        .disable(MapperFeature.ALLOW_COERCION_OF_SCALARS);
        this.probe = probe;
        this.transactions = new TransactionTemplate(manager);
    }

    /** 校验当前活跃会话的服务端租户/角色映射，若依admin通配权限也不能绕过此检查。 */
    public Principal principal() {
        Principal principal = repository.findPrincipal(SecurityUtils.getUserId());
        if (principal == null || !"SUPER_ADMIN".equals(principal.dataRole())) {
            throw new ConfigurationException(
                    403, "CONFIGURATION_FORBIDDEN", "仅目标租户授权的超级管理员可维护系统配置");
        }
        return principal;
    }

    public Map<String, Object> metadata() {
        principal();
        return Map.of(
                "sections", ConfigurationCatalog.sections(), "encryptionReady", cipher.isReady());
    }

    public List<View> list() {
        return repository.list(principal().tenantId()).stream().map(this::view).toList();
    }

    public View get(String id) {
        return view(load(principal().tenantId(), id));
    }

    /** 先检查配置可见性，再查询本租户历史；不接受客户端指定租户。 */
    public AuditPage history(String id, Long beforeRevision, int pageSize) {
        Principal actor = principal();
        load(actor.tenantId(), id);
        if (pageSize < 1 || pageSize > 100 || (beforeRevision != null && beforeRevision < 1)) {
            throw new ConfigurationException(400, "INVALID_HISTORY_PAGE", "历史每页须为1至100条，版本游标须为正整数");
        }
        List<AuditRow> rows =
                repository.history(
                        actor.tenantId(),
                        id,
                        beforeRevision == null ? Long.MAX_VALUE : beforeRevision,
                        pageSize + 1);
        boolean more = rows.size() > pageSize;
        List<AuditView> items =
                rows.stream()
                        .limit(pageSize)
                        .map(
                                row -> {
                                    try {
                                        List<String> fields =
                                                json.readValue(
                                                        row.changedFieldsJson,
                                                        new TypeReference<List<String>>() {});
                                        return new AuditView(
                                                row.id,
                                                row.actorId,
                                                row.action,
                                                row.revision,
                                                row.beforeRevision,
                                                row.beforeHash,
                                                row.afterHash,
                                                row.hashAlgorithm,
                                                fields,
                                                row.reason,
                                                row.createdAt);
                                    } catch (Exception exception) {
                                        throw new ConfigurationException(
                                                500, "HISTORY_INVALID", "变更历史无法读取，请联系管理员核查");
                                    }
                                })
                        .toList();
        return new AuditPage(items, more ? items.get(items.size() - 1).revision() : null);
    }

    /** 只使用专用严格解析器，结构错误不交给可能打印rejectedValue的默认验证日志。 */
    public WriteRequest parse(JsonNode payload) {
        try {
            if (!payload.isObject() || !payload.path("enabled").isBoolean()) {
                throw new IllegalArgumentException();
            }
            return json.treeToValue(payload, WriteRequest.class);
        } catch (Exception exception) {
            throw new ConfigurationException(400, "INVALID_STRUCTURE", "系统配置结构无效、包含未知字段或字段类型错误");
        }
    }

    /** 只读测试也会写入版本和审计；只接受明确的人工原因，不容许额外凭据字段。 */
    public String parseTestReason(JsonNode payload) {
        if (!payload.isObject() || payload.size() != 1 || !payload.path("reason").isTextual()) {
            throw new ConfigurationException(400, "INVALID_STRUCTURE", "连接测试仅接受字符串类型的测试原因");
        }
        return payload.path("reason").asText();
    }

    /** 创建/更新时只保存加密凭据；清除和替换均使原验证状态失效。 */
    // 幂等请求可能等待另一事务提交；READ_COMMITTED保证重放时读取到刚提交的配置。
    // 若使用默认REPEATABLE_READ，前面的权限查询会固定旧快照，导致重放错误返回404。
    @Transactional(isolation = org.springframework.transaction.annotation.Isolation.READ_COMMITTED)
    public View save(String id, long expectedRevision, String requestKey, WriteRequest request) {
        Principal actor = principal();
        if (requestKey == null || !requestKey.matches("[A-Za-z0-9:_-]{8,128}")) {
            throw new ConfigurationException(
                    400, "IDEMPOTENCY_REQUIRED", "Idempotency-Key必须为8至128位安全随机标识");
        }
        String payloadHash = payloadHash(id, expectedRevision, request);
        repository.reserveRequest(
                actor.tenantId(), SecurityUtils.getUserId(), requestKey, payloadHash);
        IdempotencyRow recorded =
                repository.requestForUpdate(
                        actor.tenantId(), SecurityUtils.getUserId(), requestKey);
        if (!payloadHash.equals(recorded.payloadHash)) {
            throw new ConfigurationException(409, "IDEMPOTENCY_CONFLICT", "相同幂等键不能用于不同配置请求");
        }
        if (recorded.responseJson != null) {
            try {
                View replay = json.readValue(recorded.responseJson, View.class);
                load(actor.tenantId(), replay.id());
                return replay;
            } catch (com.fasterxml.jackson.core.JsonProcessingException exception) {
                throw new ConfigurationException(500, "REPLAY_UNAVAILABLE", "幂等结果暂时不可读取");
            }
        }
        boolean creating = id == null;
        Row row = creating ? new Row() : load(actor.tenantId(), id);
        if (!creating && row.revision != expectedRevision) {
            throw conflict();
        }
        if (creating) {
            row.id = UUID.randomUUID().toString();
            row.tenantId = actor.tenantId();
            row.section = ConfigurationCatalog.section(request.section()).key();
            row.revision = 0;
        } else if (!row.section.equals(request.section())) {
            throw new ConfigurationException(422, "SECTION_IMMUTABLE", "已有配置不能更换类型，请新建对应配置");
        }
        if (row.section.equals("RISK")) {
            Set<String> permissions = SecurityUtils.getLoginUser().getPermissions();
            if (!permissions.contains("system.release.manage") && !permissions.contains("*:*:*")) {
                throw new ConfigurationException(403, "POLICY_FORBIDDEN", "修改执行风控还需要发布管理权限");
            }
        }
        String beforeHash = creating ? null : ConfigurationFingerprint.of(row);
        String previousName = row.name;
        boolean previousEnabled = row.enabled;
        Map<String, Object> previousSettings =
                creating ? Map.of() : decodeSettings(row.settingsJson);
        row.name = ConfigurationCatalog.normalizeText(request.name(), 100, "配置名称");
        String reason = ConfigurationCatalog.normalizeText(request.reason(), 500, "变更原因");
        Map<String, Object> settings =
                ConfigurationCatalog.validate(row.section, request.settings(), request.enabled());
        Map<String, String> encrypted =
                creating ? new LinkedHashMap<>() : decodeSecrets(row.secretsJson);
        Map<String, SecretChange> changes =
                request.secrets() == null ? Map.of() : request.secrets();
        Map<String, ConfigurationCatalog.Field> secretFields = new LinkedHashMap<>();
        ConfigurationCatalog.section(row.section).fields().stream()
                .filter(field -> field.type().equals("secret"))
                .forEach(field -> secretFields.put(field.key(), field));
        if (!secretFields.keySet().containsAll(changes.keySet())) {
            throw new ConfigurationException(400, "UNKNOWN_SECRET", "包含此配置不支持的密钥字段");
        }
        List<String> changedFields = new ArrayList<>();
        if (creating || !java.util.Objects.equals(previousName, row.name))
            changedFields.add("name");
        if (creating || previousEnabled != request.enabled()) changedFields.add("enabled");
        Set<String> settingKeys = new java.util.TreeSet<>(previousSettings.keySet());
        settingKeys.addAll(settings.keySet());
        for (String key : settingKeys) {
            if (!java.util.Objects.equals(previousSettings.get(key), settings.get(key))) {
                changedFields.add(key);
            }
        }
        for (Map.Entry<String, SecretChange> entry : changes.entrySet()) {
            SecretChange change = entry.getValue();
            if (change == null || change.operation() == null) {
                throw new ConfigurationException(400, "INVALID_SECRET_ACTION", "密钥操作结构无效");
            }
            switch (change.operation()) {
                case "KEEP" -> {
                    if (change.value() != null && !change.value().isEmpty()) {
                        throw invalidSecret();
                    }
                }
                case "CLEAR" -> {
                    if (change.value() != null && !change.value().isEmpty()) {
                        throw invalidSecret();
                    }
                    encrypted.remove(entry.getKey());
                    changedFields.add("secret:" + entry.getKey() + ":cleared");
                }
                case "REPLACE" -> {
                    String value = change.value();
                    if (value == null
                            || value.isBlank()
                            || value.length() > 8192
                            || value.contains("*")
                            || value.codePoints().anyMatch(Character::isISOControl)) {
                        throw invalidSecret();
                    }
                    encrypted.put(
                            entry.getKey(),
                            cipher.encrypt(value, row.tenantId, row.id, entry.getKey()));
                    changedFields.add("secret:" + entry.getKey() + ":replaced");
                }
                default -> throw invalidSecret();
            }
        }
        if (request.enabled()
                && secretFields.values().stream()
                        .anyMatch(
                                field -> field.required() && !encrypted.containsKey(field.key()))) {
            throw new ConfigurationException(422, "SECRET_REQUIRED", "启用前必须配置所需凭据");
        }
        if (request.enabled() && row.section.equals("AI_SUGGESTIONS")) {
            Row provider = load(actor.tenantId(), settings.get("providerConfigId").toString());
            if (!provider.enabled || !Set.of("AI_GPT", "AI_CLAUDE").contains(provider.section)) {
                throw new ConfigurationException(
                        422, "AI_PROVIDER_UNAVAILABLE", "默认AI配置须为本租户已启用的GPT或Claude配置");
            }
        }
        row.enabled = request.enabled();
        row.settingsJson = encode(settings);
        row.secretsJson = encode(encrypted);
        row.revision++;
        if (creating) {
            repository.insert(row);
        } else if (repository.update(row, expectedRevision) != 1) {
            throw conflict();
        }
        Row stored = load(actor.tenantId(), row.id);
        repository.audit(
                new AuditWrite(
                        UUID.randomUUID().toString(),
                        actor.tenantId(),
                        row.id,
                        SecurityUtils.getUserId(),
                        creating ? "CREATE" : "UPDATE",
                        stored.revision,
                        expectedRevision,
                        beforeHash,
                        ConfigurationFingerprint.of(stored),
                        ConfigurationFingerprint.ALGORITHM,
                        encode(changedFields),
                        reason));
        View response = view(stored);
        repository.finishRequest(
                actor.tenantId(), SecurityUtils.getUserId(), requestKey, encode(response));
        return response;
    }

    /** 网络请求不占用数据库事务；测试期间配置变更时CAS拒绝保存过时结果。 */
    public Map<String, Object> test(String id, long expectedRevision, String reason) {
        Principal actor = principal();
        Row row = load(actor.tenantId(), id);
        if (row.revision != expectedRevision) {
            throw conflict();
        }
        if (reason != null && reason.codePoints().anyMatch(Character::isISOControl)) {
            throw new ConfigurationException(422, "FIELD_INVALID", "测试原因不能包含控制字符");
        }
        String normalizedReason = ConfigurationCatalog.normalizeText(reason, 500, "测试原因");
        String beforeHash = ConfigurationFingerprint.of(row);
        Map<String, Object> settings = decodeSettings(row.settingsJson);
        ConfigurationCatalog.validate(row.section, settings, true);
        Map<String, String> plaintext = new LinkedHashMap<>();
        try {
            for (Map.Entry<String, String> entry : decodeSecrets(row.secretsJson).entrySet()) {
                plaintext.put(
                        entry.getKey(),
                        cipher.decrypt(entry.getValue(), actor.tenantId(), id, entry.getKey()));
            }
            ConnectionProbe.Result result = probe.check(row.section, settings, plaintext);
            transactions.executeWithoutResult(
                    status -> {
                        Principal current = principal();
                        if (!current.tenantId().equals(actor.tenantId())) {
                            throw new ConfigurationException(
                                    403, "CONFIGURATION_SCOPE_CHANGED", "当前租户授权已变化，请刷新后重试");
                        }
                        if (repository.recordVerification(
                                        actor.tenantId(), id, expectedRevision, result.status())
                                != 1) {
                            throw conflict();
                        }
                        Row stored = load(actor.tenantId(), id);
                        repository.audit(
                                new AuditWrite(
                                        UUID.randomUUID().toString(),
                                        actor.tenantId(),
                                        id,
                                        SecurityUtils.getUserId(),
                                        "READ_TEST",
                                        expectedRevision + 1,
                                        expectedRevision,
                                        beforeHash,
                                        ConfigurationFingerprint.of(stored),
                                        ConfigurationFingerprint.ALGORITHM,
                                        "[\"verificationStatus\"]",
                                        normalizedReason));
                    });
            return Map.of("configuration", get(id), "result", result);
        } finally {
            plaintext.clear();
        }
    }

    private View view(Row row) {
        Map<String, String> encrypted = decodeSecrets(row.secretsJson);
        Map<String, SecretState> secrets = new LinkedHashMap<>();
        ConfigurationCatalog.section(row.section).fields().stream()
                .filter(field -> field.type().equals("secret"))
                .forEach(
                        field ->
                                secrets.put(
                                        field.key(),
                                        new SecretState(
                                                encrypted.containsKey(field.key()),
                                                encrypted.containsKey(field.key())
                                                        ? "已配置（不回显）"
                                                        : "未配置")));
        return new View(
                row.id,
                row.section,
                row.name,
                row.enabled,
                row.revision,
                decodeSettings(row.settingsJson),
                secrets,
                row.verificationStatus,
                row.verifiedAt,
                row.updatedAt);
    }

    private Row load(String tenantId, String id) {
        Row row = repository.find(tenantId, id);
        if (row == null) {
            throw new ConfigurationException(404, "NOT_FOUND", "配置不存在或不在当前可见范围");
        }
        return row;
    }

    private Map<String, Object> decodeSettings(String value) {
        try {
            return json.readValue(value, new TypeReference<LinkedHashMap<String, Object>>() {});
        } catch (Exception exception) {
            throw new ConfigurationException(500, "STORAGE_INVALID", "配置数据无法读取，请联系管理员核查");
        }
    }

    private Map<String, String> decodeSecrets(String value) {
        try {
            return json.readValue(value, new TypeReference<LinkedHashMap<String, String>>() {});
        } catch (Exception exception) {
            throw new ConfigurationException(500, "STORAGE_INVALID", "凭据数据无法读取，请联系管理员核查");
        }
    }

    private String payloadHash(String id, long revision, WriteRequest request) {
        try {
            java.security.MessageDigest hash = java.security.MessageDigest.getInstance("SHA-256");
            hash.update(
                    (String.valueOf(id) + ":" + revision + ":")
                            .getBytes(java.nio.charset.StandardCharsets.UTF_8));
            byte[] bytes = json.writeValueAsBytes(request);
            try {
                return java.util.HexFormat.of().formatHex(hash.digest(bytes));
            } finally {
                java.util.Arrays.fill(bytes, (byte) 0);
            }
        } catch (Exception exception) {
            throw new ConfigurationException(500, "REQUEST_HASH_FAILED", "配置请求无法生成幂等校验");
        }
    }

    private String encode(Object value) {
        try {
            return json.writeValueAsString(value);
        } catch (Exception exception) {
            throw new ConfigurationException(500, "SERIALIZATION_FAILED", "配置保存失败");
        }
    }

    private static ConfigurationException conflict() {
        return new ConfigurationException(409, "REVISION_CONFLICT", "配置已变化，请刷新后重试");
    }

    private static ConfigurationException invalidSecret() {
        return new ConfigurationException(422, "SECRET_INVALID", "密钥操作或格式无效；请使用保持、替换或清除，不要提交掩码");
    }
}
