package com.adpulse.main.migration;

import static com.adpulse.main.migration.AssetMigrationService.require;

import com.adpulse.main.migration.AssetMigrationModels.ChannelSnapshot;
import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.databind.ObjectMapper;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.time.Duration;
import java.util.HashMap;
import java.util.HexFormat;
import java.util.Map;
import org.springframework.data.redis.core.StringRedisTemplate;

/** 账本是唯一依据，Redis 只缓存 ID 映射；缓存不可用、损坏时回源当前环境数据库。 */
public class ChannelMigrationMappingResolver {
    private final AssetMigrationMapper mapper;
    private final AssetMigrationProperties properties;
    private final ObjectMapper json;
    private final StringRedisTemplate redis;

    public ChannelMigrationMappingResolver(
            AssetMigrationMapper mapper,
            AssetMigrationProperties properties,
            ObjectMapper json,
            StringRedisTemplate redis) {
        this.mapper = mapper;
        this.properties = properties;
        this.json = json;
        this.redis = redis;
    }

    /** 必须在目标事务中调用；先锁定有效账本，任何缓存命中都不能绕过数据库校验。 */
    public ChannelSnapshot resolve() {
        return resolve(false);
    }

    /** 首次渠道同步允许空映射，账户同步仍要求已有映射。 */
    public ChannelSnapshot resolveForChannelPlan() {
        return resolve(true);
    }

    private ChannelSnapshot resolve(boolean allowEmpty) {
        properties.validateEnvironment();
        String environment = properties.getTargetEnvironment().name();
        String batch = properties.channelBatchKey();
        boolean legacyTable = mapper.ledgerExists(environment) == 1;
        boolean incrementalReady = mapper.channelIncrementSchemaReady() == 1;
        require(legacyTable || incrementalReady, "当前环境的渠道迁移账本尚未创建");
        Map<Long, Long> ids = new HashMap<>();
        StringBuilder versions =
                new StringBuilder(environment)
                        .append('|')
                        .append(properties.getSourceUuid())
                        .append('|')
                        .append(properties.getSourceSchema())
                        .append('|')
                        .append(properties.getTargetUuid())
                        .append('|')
                        .append(properties.getTargetSchema());
        if (legacyTable) {
            var ledger = mapper.channelLedger(environment, batch);
            require(ledger != null || incrementalReady, "当前环境渠道迁移尚未提交或已回滚");
            if (ledger != null) {
                require(
                        fingerprint(properties.getSourceUuid(), properties.getSourceSchema())
                                .equals(ledger.sourceFingerprint()),
                        "渠道账本来源实例不符，不能复用其他来源的映射");
                require(
                        fingerprint(properties.getTargetUuid(), properties.getTargetSchema())
                                .equals(ledger.targetFingerprint()),
                        "渠道账本目标实例不符，不能复用其他环境的映射");
                require(ledger.payloadHash() != null && ledger.mappingHash() != null, "渠道账本映射缺失");
                String legacyVersion =
                        sha256(
                                environment
                                        + "|"
                                        + batch
                                        + "|"
                                        + ledger.sourceFingerprint()
                                        + "|"
                                        + ledger.targetFingerprint()
                                        + "|"
                                        + ledger.payloadHash()
                                        + "|"
                                        + ledger.mappingHash());
                if (!incrementalReady) {
                    String legacyKey =
                            "adpulse:asset-migration:channel-map:v2:"
                                    + environment
                                    + ":"
                                    + legacyVersion;
                    String cachedJson = cached(legacyKey);
                    if (cachedJson != null && sha256(cachedJson).equals(ledger.mappingHash())) {
                        return new ChannelSnapshot(legacyVersion, parse(cachedJson));
                    }
                }
                String legacyJson = mapper.channelMapping(environment, batch);
                require(
                        legacyJson != null && sha256(legacyJson).equals(ledger.mappingHash()),
                        "渠道映射读取期间变化，请重新预检");
                merge(ids, parse(legacyJson));
                if (!incrementalReady) {
                    String legacyKey =
                            "adpulse:asset-migration:channel-map:v2:"
                                    + environment
                                    + ":"
                                    + legacyVersion;
                    cache(legacyKey, legacyJson);
                    return new ChannelSnapshot(legacyVersion, Map.copyOf(ids));
                }
                versions.append('|')
                        .append(batch)
                        .append('|')
                        .append(ledger.payloadHash())
                        .append('|')
                        .append(ledger.mappingHash());
            }
        }
        if (incrementalReady) {
            var incremental =
                    mapper.incrementalMappings(
                            environment,
                            properties.getSourceUuid(),
                            properties.getSourceSchema(),
                            properties.getTargetUuid(),
                            properties.getTargetSchema());
            for (var mapping : incremental) {
                Long old = ids.putIfAbsent(mapping.sourceId(), mapping.targetId());
                require(old == null || old == mapping.targetId(), "同一来源渠道存在冲突映射");
                require(
                        old != null
                                || ids.entrySet().stream()
                                        .noneMatch(
                                                entry ->
                                                        entry.getKey() != mapping.sourceId()
                                                                && entry.getValue()
                                                                        == mapping.targetId()),
                        "不同来源渠道不能映射到同一目标渠道");
            }
            versions.append('|').append(incremental);
        }
        require(allowEmpty || !ids.isEmpty(), "当前环境尚无已应用的渠道迁移映射，请先同步渠道");
        String version = sha256(versions.toString());
        String key = "adpulse:asset-migration:channel-map:v2:" + environment + ":" + version;
        String mappingJson = cached(key);
        if (mappingJson != null) {
            try {
                Map<Long, Long> cachedIds = parse(mappingJson);
                if (cachedIds.equals(ids)) return new ChannelSnapshot(version, cachedIds);
            } catch (RuntimeException ignored) {
                // 缓存损坏时使用已核对的数据库映射，不中断迁移。
            }
        }
        mappingJson = encode(ids);
        cache(key, mappingJson);
        return new ChannelSnapshot(version, Map.copyOf(ids));
    }

    /** 映射版本包含全部数据库内容，新提交后自然使用新缓存键。 */
    public void evict() {
        // 不删除共享 Redis 的其他环境键；新版本哈希会生成独立键。
    }

    private void merge(Map<Long, Long> destination, Map<Long, Long> additions) {
        for (var entry : additions.entrySet()) {
            Long old = destination.putIfAbsent(entry.getKey(), entry.getValue());
            require(old == null || old.equals(entry.getValue()), "同一来源渠道存在冲突映射");
        }
    }

    private String encode(Map<Long, Long> ids) {
        try {
            var rows =
                    ids.entrySet().stream()
                            .sorted(Map.Entry.comparingByKey())
                            .map(
                                    entry ->
                                            Map.of(
                                                    "sourceId",
                                                    entry.getKey(),
                                                    "targetId",
                                                    entry.getValue()))
                            .toList();
            return json.writeValueAsString(rows);
        } catch (JsonProcessingException exception) {
            throw new AssetMigrationService.Conflict("渠道映射 JSON 序列化失败");
        }
    }

    private Map<Long, Long> parse(String value) {
        try {
            var nodes = json.readTree(value);
            require(nodes != null && nodes.isArray() && !nodes.isEmpty(), "渠道映射为空或格式错误");
            var ids = new HashMap<Long, Long>();
            var targets = new java.util.HashSet<Long>();
            for (var node : nodes) {
                var source = node.path("sourceId");
                var target = node.path("targetId");
                require(
                        source.isIntegralNumber()
                                && source.canConvertToLong()
                                && source.asLong() > 0
                                && target.isIntegralNumber()
                                && target.canConvertToLong()
                                && target.asLong() > 0,
                        "渠道映射 ID 不合法");
                require(
                        ids.putIfAbsent(source.asLong(), target.asLong()) == null
                                && targets.add(target.asLong()),
                        "渠道映射重复或不是一对一关系");
            }
            return Map.copyOf(ids);
        } catch (JsonProcessingException exception) {
            throw new AssetMigrationService.Conflict("渠道映射 JSON 不合法");
        }
    }

    private String cached(String key) {
        if (!properties.isMappingCacheEnabled() || redis == null) return null;
        try {
            return redis.opsForValue().get(key);
        } catch (RuntimeException exception) {
            return null;
        } // 缓存失败不影响数据库校验。
    }

    private void cache(String key, String value) {
        if (!properties.isMappingCacheEnabled() || redis == null) return;
        try {
            redis.opsForValue().set(key, value, Duration.ofMinutes(10));
        } catch (RuntimeException exception) {
            /* 缓存是可丢弃的副本；任务状态仍在数据库持久化。 */
        }
    }

    /** 与既有 Python 渠道迁移账本的 sort_keys=True JSON 指纹保持兼容。 */
    static String fingerprint(String uuid, String schema) {
        try {
            ObjectMapper serializer = new ObjectMapper();
            return sha256(
                    "{\"db\": "
                            + serializer.writeValueAsString(schema)
                            + ", \"server_uuid\": "
                            + serializer.writeValueAsString(uuid)
                            + "}");
        } catch (JsonProcessingException exception) {
            throw new AssetMigrationService.Conflict("环境指纹生成失败");
        }
    }

    static String sha256(String value) {
        try {
            return HexFormat.of()
                    .formatHex(
                            MessageDigest.getInstance("SHA-256")
                                    .digest(value.getBytes(StandardCharsets.UTF_8)));
        } catch (java.security.NoSuchAlgorithmException exception) {
            throw new IllegalStateException(exception);
        }
    }
}
