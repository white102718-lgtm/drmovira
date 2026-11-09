package com.ruoyi.system.orbit.scope;

import com.fasterxml.jackson.databind.*;
import com.ruoyi.system.orbit.config.SecretCipher;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.time.*;
import java.util.*;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.*;

/** 单目标租户的内部审计扫描；不是完整跨租户AuditPage接口，未知历史字段原样保留。 */
@Service
public class ScopeFreezeAuditQuery {
    public record Filter(String q, String operator, String dateFrom, String dateTo) {
        @Override
        public String toString() {
            return "AuditQueryFilter[REDACTED]";
        }
    }

    /** 每批最多扫描200候选；不可见事件不返回，空批次也可能有下一批，调用者不能当作扫描结束。 */
    public record Batch(
            List<ScopeFreezeAuditReader.Entry> entries,
            String continuation,
            int scanned,
            Instant cutoff) {
        public Batch {
            entries = List.copyOf(entries);
        }

        @Override
        public String toString() {
            return "ScopeAuditBatch[REDACTED]";
        }
    }

    private record Prepared(String q, String operator, Instant from, Instant until, String hash) {}

    private final AccountScopeMapper mapper;
    private final ScopeFreezeAuditReader reader;
    private final TenantScopeVersionProof versions;
    private final SecretCipher cipher;
    private final ObjectMapper json;

    public ScopeFreezeAuditQuery(
            AccountScopeMapper mapper,
            ScopeFreezeAuditReader reader,
            TenantScopeVersionProof versions,
            SecretCipher cipher,
            ObjectMapper json) {
        this.mapper = mapper;
        this.reader = reader;
        this.versions = versions;
        this.cipher = cipher;
        this.json = json;
    }

    @Transactional(isolation = Isolation.REPEATABLE_READ)
    public Batch scanTrusted(String target, Filter filter, int size, String cursor) {
        target = ScopeRequestGuard.uuid(target);
        if (!Set.of(20, 50, 100, 200).contains(size)
                || (cursor != null && (cursor.isEmpty() || cursor.length() > 2048)))
            throw invalid();
        Prepared f = prepare(filter);
        var scope = reader.currentTargetTrusted(target);
        // 冻结与查询都先目录门闩、后权限版本，查询本身不创建或改写任何业务记录。
        mapper.clock(target);
        var proof = versions.currentTrusted(target);
        if (!cipher.isReady()) throw new AccountScopeService.Failure(503, "审计游标密钥尚未配置");
        Instant now = mapper.auditQueryTime(), cutoff = now, afterAt = null;
        String afterId = null, purpose = "SCOPE_AUDIT_QUERY_V1/" + scope.actorId();
        if (cursor != null) {
            try {
                JsonNode state =
                        json.readTree(cipher.decrypt(cursor, target, scope.homeTenant(), purpose));
                Set<String> fields = new HashSet<>();
                state.fieldNames().forEachRemaining(fields::add);
                if (!state.isObject()
                        || !fields.equals(
                                Set.of(
                                        "v",
                                        "at",
                                        "id",
                                        "cutoff",
                                        "filter",
                                        "size",
                                        "home_version",
                                        "target_version",
                                        "role"))
                        || !integer(state, "v", 1)
                        || !integer(state, "size", size)
                        || !integer(state, "home_version", proof.homeVersion())
                        || !integer(state, "target_version", proof.targetVersion())
                        || !text(state, "filter").equals(f.hash)
                        || !text(state, "role").equals(proof.dataRole())) throw changed();
                afterAt = Instant.parse(text(state, "at"));
                afterId = ScopeRequestGuard.uuid(text(state, "id"));
                cutoff = Instant.parse(text(state, "cutoff"));
                if (cutoff.isAfter(now) || !afterAt.isBefore(cutoff)) throw changed();
            } catch (Exception error) {
                throw changed();
            }
        }
        String escaped = f.q.replace("!", "!!").replace("%", "!%").replace("_", "!_");
        var rows =
                mapper.auditCandidates(
                        target, escaped, f.operator, f.from, f.until, cutoff, afterAt, afterId);
        var entries = new ArrayList<ScopeFreezeAuditReader.Entry>();
        ScopeFreezeAuditReader.Entry last = null;
        int scanned = 0;
        for (var candidate : rows) {
            if (scanned == 200 || entries.size() == size) break;
            scanned++;
            last = candidate;
            var visible = reader.visibleEntryTrusted(target, candidate.id);
            if (visible != null) entries.add(visible);
        }
        String next = null;
        if (scanned < rows.size()) {
            var state =
                    json.createObjectNode()
                            .put("v", 1)
                            .put("at", last.createdAt.toString())
                            .put("id", last.id)
                            .put("cutoff", cutoff.toString())
                            .put("filter", f.hash)
                            .put("size", size)
                            .put("home_version", proof.homeVersion())
                            .put("target_version", proof.targetVersion())
                            .put("role", proof.dataRole());
            try {
                next =
                        cipher.encrypt(
                                json.writeValueAsString(state),
                                target,
                                scope.homeTenant(),
                                purpose);
            } catch (Exception error) {
                throw new AccountScopeService.Failure(503, "审计游标生成失败");
            }
        }
        return new Batch(entries, next, scanned, cutoff);
    }

    private Prepared prepare(Filter filter) {
        filter = ScopeAuditQueryParameters.normalize(filter);
        String q = filter.q();
        try {
            String operator = filter.operator();
            LocalDate from = filter.dateFrom() == null ? null : LocalDate.parse(filter.dateFrom());
            LocalDate to = filter.dateTo() == null ? null : LocalDate.parse(filter.dateTo());
            Instant start = from == null ? null : from.atStartOfDay(ZoneOffset.UTC).toInstant();
            Instant end =
                    to == null ? null : to.plusDays(1).atStartOfDay(ZoneOffset.UTC).toInstant();
            String canonical =
                    json.writeValueAsString(
                            Arrays.asList(
                                    q,
                                    operator,
                                    start == null ? null : start.toString(),
                                    end == null ? null : end.toString()));
            String hash =
                    HexFormat.of()
                            .formatHex(
                                    MessageDigest.getInstance("SHA-256")
                                            .digest(canonical.getBytes(StandardCharsets.UTF_8)));
            return new Prepared(q, operator, start, end, hash);
        } catch (Exception error) {
            throw invalid();
        }
    }

    private String text(JsonNode node, String field) {
        if (!node.path(field).isTextual()) throw changed();
        return node.path(field).textValue();
    }

    private boolean integer(JsonNode node, String field, long value) {
        return node.path(field).isIntegralNumber()
                && node.path(field).canConvertToLong()
                && node.path(field).longValue() == value;
    }

    private AccountScopeService.Failure invalid() {
        return new AccountScopeService.Failure(422, "审计筛选、UTC日期、页大小或游标长度无效");
    }

    private AccountScopeService.Failure changed() {
        return new AccountScopeService.Failure(409, "审计授权或游标上下文已变化，请重新查询");
    }
}
