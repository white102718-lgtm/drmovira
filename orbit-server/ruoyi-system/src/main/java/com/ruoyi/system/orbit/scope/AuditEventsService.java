package com.ruoyi.system.orbit.scope;

import com.fasterxml.jackson.annotation.JsonProperty;
import com.fasterxml.jackson.databind.*;
import com.ruoyi.system.orbit.config.SecretCipher;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.time.*;
import java.util.*;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.*;

/** 按当前server_scope逐租户查询并归并审计，当前支持范围冻结成功事件。 */
@Service
public class AuditEventsService {
    public record Item(
            String id,
            @JsonProperty("actor_user_id") String actorUserId,
            @JsonProperty("action_code") String actionCode,
            @JsonProperty("target_id") String targetId,
            @JsonProperty("tenant_id") String tenantId,
            String reason,
            @JsonProperty("evidence_ref") String evidenceRef,
            @JsonProperty("occurred_at") Instant occurredAt,
            @JsonProperty("request_id") String requestId) {
        @Override
        public String toString() {
            return "AuditItem[REDACTED]";
        }
    }

    public record Page(
            List<Item> items,
            @JsonProperty("next_cursor") String nextCursor,
            @JsonProperty("data_as_of") Instant dataAsOf,
            @JsonProperty("scope_version") long scopeVersion) {
        public Page {
            items = List.copyOf(items);
        }

        @Override
        public String toString() {
            return "AuditPage[REDACTED]";
        }
    }

    private final ServerTenantScope tenants;
    private final ScopeFreezeAuditReader reader;
    private final AccountScopeMapper mapper;
    private final SecretCipher cipher;
    private final ObjectMapper json;

    public AuditEventsService(
            ServerTenantScope tenants,
            ScopeFreezeAuditReader reader,
            AccountScopeMapper mapper,
            SecretCipher cipher,
            ObjectMapper json) {
        this.tenants = tenants;
        this.reader = reader;
        this.mapper = mapper;
        this.cipher = cipher;
        this.json = json;
    }

    @Transactional(isolation = Isolation.REPEATABLE_READ)
    public Page pageTrusted(Map<String, List<String>> query) {
        var input = ScopeAuditQueryParameters.parse(query);
        var filter = input.filter();
        var scope = tenants.current();
        reader.currentTargetTrusted(scope.homeTenant());
        if (!mapper.auditPageMenuIds(scope.actorId()).contains(31083L))
            throw new AccountScopeService.Failure(403, "没有审计页面权限");
        if (!cipher.isReady()) throw new AccountScopeService.Failure(503, "审计游标密钥尚未配置");
        var targets = scope.tenantIds().stream().sorted().toList();
        // 统一先取得所有目录门闩，再按同一顺序取版本，保持冻结写入的目录->版本锁序。
        for (String target : targets) mapper.clock(target);
        Map<String, Long> proof = new TreeMap<>();
        for (String target : targets) {
            Long version = mapper.scopeVersion(target);
            if (version == null || version < 1 || version > ScopeVersionService.MAX_VERSION)
                throw new AccountScopeService.Failure(503, "审计授权版本尚不可用");
            proof.put(target, version);
        }
        String authority = hash(List.of(scope.homeTenant(), scope.dataRole(), proof));
        String fingerprint =
                hash(
                        Arrays.asList(
                                filter.q(), filter.operator(), filter.dateFrom(), filter.dateTo()));
        String purpose = "AUDIT_EVENTS_V1/" + scope.actorId();
        Instant now = mapper.auditQueryTime(), cutoff = now, afterAt = null;
        String afterId = null;
        if (input.cursor() != null) {
            try {
                JsonNode state =
                        json.readTree(
                                cipher.decrypt(
                                        input.cursor(),
                                        scope.homeTenant(),
                                        "audit-events",
                                        purpose));
                Set<String> fields = new HashSet<>();
                state.fieldNames().forEachRemaining(fields::add);
                if (!state.isObject()
                        || !fields.equals(
                                Set.of("v", "at", "id", "cutoff", "filter", "size", "authority"))
                        || !number(state, "v", 1)
                        || !number(state, "size", input.size())
                        || !text(state, "filter").equals(fingerprint)
                        || !text(state, "authority").equals(authority)) throw changed();
                cutoff = Instant.parse(text(state, "cutoff"));
                afterAt = Instant.parse(text(state, "at"));
                afterId = ScopeRequestGuard.uuid(text(state, "id"));
                if (cutoff.isAfter(now) || !afterAt.isBefore(cutoff)) throw changed();
            } catch (Exception failure) {
                throw changed();
            }
        }
        Instant from =
                filter.dateFrom() == null
                        ? null
                        : LocalDate.parse(filter.dateFrom())
                                .atStartOfDay(ZoneOffset.UTC)
                                .toInstant();
        Instant until =
                filter.dateTo() == null
                        ? null
                        : LocalDate.parse(filter.dateTo())
                                .plusDays(1)
                                .atStartOfDay(ZoneOffset.UTC)
                                .toInstant();
        String escaped = filter.q().replace("!", "!!").replace("%", "!%").replace("_", "!_");
        var candidates = new ArrayList<ScopeFreezeAuditReader.Entry>();
        for (String target : targets)
            candidates.addAll(
                    mapper.auditCandidates(
                            target,
                            escaped,
                            filter.operator(),
                            from,
                            until,
                            cutoff,
                            afterAt,
                            afterId));
        candidates.sort(
                Comparator.comparing((ScopeFreezeAuditReader.Entry e) -> e.createdAt)
                        .thenComparing(e -> e.id)
                        .reversed());
        List<Item> items = new ArrayList<>();
        int scanned = 0;
        ScopeFreezeAuditReader.Entry last = null;
        for (var candidate : candidates) {
            if (scanned == 200 || items.size() == input.size()) break;
            scanned++;
            last = candidate;
            var visible = reader.visibleEntryTrusted(candidate.targetTenantId, candidate.id);
            if (visible != null) items.add(project(visible));
        }
        String next = null;
        if (scanned < candidates.size()) {
            var state =
                    json.createObjectNode()
                            .put("v", 1)
                            .put("at", last.createdAt.toString())
                            .put("id", last.id)
                            .put("cutoff", cutoff.toString())
                            .put("filter", fingerprint)
                            .put("size", input.size())
                            .put("authority", authority);
            try {
                next =
                        cipher.encrypt(
                                json.writeValueAsString(state),
                                scope.homeTenant(),
                                "audit-events",
                                purpose);
            } catch (Exception failure) {
                throw new AccountScopeService.Failure(503, "审计游标生成失败");
            }
        }
        // 返回当前会话home的真实权限时钟，不对目标版本求和/MAX；全目标版本指纹额外绑定游标。
        return new Page(items, next, cutoff, proof.get(scope.homeTenant()));
    }

    private Item project(ScopeFreezeAuditReader.Entry row) {
        try {
            return new Item(
                    ScopeRequestGuard.uuid(row.id),
                    ScopeRequestGuard.uuid(row.actorSubjectId),
                    row.action,
                    ScopeRequestGuard.uuid(row.snapshotId),
                    ScopeRequestGuard.uuid(row.targetTenantId),
                    "冻结账户范围",
                    null,
                    Objects.requireNonNull(row.createdAt),
                    ScopeRequestGuard.uuid(row.requestId));
        } catch (Exception failure) {
            throw new AccountScopeService.Failure(
                    503, "AUDIT_HISTORY_INCOMPLETE", "历史审计缺少必要身份或请求标识，需先核对数据；未隐藏或补造历史记录");
        }
    }

    private String hash(Object value) {
        try {
            return HexFormat.of()
                    .formatHex(
                            MessageDigest.getInstance("SHA-256")
                                    .digest(
                                            json.writeValueAsString(value)
                                                    .getBytes(StandardCharsets.UTF_8)));
        } catch (Exception failure) {
            throw new AccountScopeService.Failure(503, "审计上下文编码失败");
        }
    }

    private String text(JsonNode node, String field) {
        if (!node.path(field).isTextual()) throw changed();
        return node.path(field).textValue();
    }

    private boolean number(JsonNode node, String field, long expected) {
        return node.path(field).isIntegralNumber()
                && node.path(field).canConvertToLong()
                && node.path(field).longValue() == expected;
    }

    private AccountScopeService.Failure changed() {
        return new AccountScopeService.Failure(409, "审计权限或游标上下文已变化，请重新查询");
    }
}
