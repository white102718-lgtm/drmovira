package com.ruoyi.system.orbit.metrics;

import com.fasterxml.jackson.annotation.JsonIgnore;
import com.ruoyi.system.orbit.rules.RuleOwnership;
import java.time.Instant;
import java.util.*;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.*;

/** 内部归因口径版本登记；没有公共写接口或平台验证器，所有新版本固定UNVERIFIED。 */
@Service
public class MetricProfileRegistry {
    public static class Row {
        public String tenantId, id, version, source, bodyHash, verificationState;
        public boolean published;
        @JsonIgnore public String bodyJson;
        public Instant createdAt;

        @Override
        public String toString() {
            return "MetricProfileRow[REDACTED]";
        }
    }

    public static final class Failure extends RuntimeException {
        private final int status;

        public Failure(int status, String safeMessage) {
            super(safeMessage);
            this.status = status;
        }

        public int status() {
            return status;
        }
    }

    private final MetricProfileMapper mapper;
    private final MetricProfileGuard guard;
    private final RuleOwnership ownership;

    public MetricProfileRegistry(
            MetricProfileMapper mapper, MetricProfileGuard guard, RuleOwnership ownership) {
        this.mapper = mapper;
        this.guard = guard;
        this.ownership = ownership;
    }

    /** profileId由可信服务端采集/管理上下文预分配；自然幂等键为tenant/profile/version。 */
    @Transactional(isolation = Isolation.READ_COMMITTED)
    public Row registerTrustedVersion(
            String tenant,
            long actor,
            String profileId,
            com.fasterxml.jackson.databind.JsonNode definition,
            String reason) {
        tenant = uuid(tenant);
        profileId = uuid(profileId);
        var current = ownership.actor(tenant, actor);
        if (!"SUPER_ADMIN".equals(current.dataRole)) throw new Failure(403, "指标口径登记需要当前租户管理授权");
        if (reason == null
                || reason.isBlank()
                || reason.codePointCount(0, reason.length()) > 500
                || reason.codePoints().anyMatch(Character::isISOControl))
            throw new Failure(422, "指标口径登记原因无效");
        var frozen = guard.prepare(definition);
        Row row = new Row();
        row.tenantId = tenant;
        row.id = profileId;
        row.version = frozen.version();
        row.source = frozen.source();
        row.bodyJson = frozen.json();
        row.bodyHash = frozen.sha256();
        row.verificationState = "UNVERIFIED";
        row.createdAt = Instant.now();
        mapper.reserve(row);
        Row stored = mapper.lock(tenant, profileId, row.version);
        if (!row.bodyHash.equals(stored.bodyHash)) throw new Failure(409, "指标口径版本已存在且定义不同");
        if (stored.published) return stored;
        mapper.finish(row);
        mapper.audit(row, actor, reason.strip());
        return mapper.lock(tenant, profileId, row.version);
    }

    /** 后续规则消费必须通过此门槛；FIXTURE及只有格式定义的META均不可用于生产分析。 */
    @Transactional(isolation = Isolation.READ_COMMITTED)
    public Row requireVerifiedMeta(String tenant, long actor, String id, String version) {
        tenant = uuid(tenant);
        id = uuid(id);
        ownership.actor(tenant, actor);
        Row row = mapper.lock(tenant, id, version);
        if (row == null || !row.published) throw new Failure(404, "指标口径不存在或不在当前租户");
        if (!"META".equals(row.source) || !"READ_VERIFIED".equals(row.verificationState))
            throw new Failure(422, "指标口径没有真实Meta验证证据");
        return row;
    }

    private String uuid(String value) {
        try {
            String normalized = UUID.fromString(value).toString();
            if (!normalized.equalsIgnoreCase(value)) throw new IllegalArgumentException();
            return normalized;
        } catch (Exception error) {
            throw new Failure(422, "指标口径身份无效");
        }
    }
}
