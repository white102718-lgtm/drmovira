package com.ruoyi.system.orbit.reference;

import com.fasterxml.jackson.annotation.JsonIgnore;
import com.fasterxml.jackson.annotation.JsonProperty;
import com.fasterxml.jackson.core.type.TypeReference;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.ruoyi.system.orbit.rules.RuleDraftMapper;
import com.ruoyi.system.orbit.rules.RuleOwnership;
import com.ruoyi.system.orbit.scope.AccountScopeMapper;
import com.ruoyi.system.orbit.scope.ScopeRequestGuard;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.time.Instant;
import java.util.*;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.*;

/** 引用目录内部事务服务；当前只接可信home租户调用，公开JWT/菜单/CSRF及跨租户入口另行接入。 */
@Service
public class ReferenceImportStore {
    public static class RecordRow {
        public String id, tenantId, kind, sourceKey, ownerTeamId, availability, valueHash;
        @JsonIgnore public String valueJson;
        public long revision, catalogRevision;
        public Instant updatedAt;

        @Override
        public String toString() {
            return "ReferenceRecord[REDACTED]";
        }
    }

    public static class ImportRow {
        public String id, tenantId, state, bodyHash;
        @JsonIgnore public String bodyJson, issuesJson;
        public long actorId, revision, baseCatalogRevision;
        public int createdCount, updatedCount;
        public Instant expiresAt, createdAt;

        @Override
        public String toString() {
            return "ReferencePreview[REDACTED]";
        }
    }

    public static class Replay {
        public String requestHash, importId;
        @JsonIgnore public String responseJson;

        @Override
        public String toString() {
            return "ReferenceReplay[REDACTED]";
        }
    }

    public record Result(
            String id,
            long revision,
            String state,
            @JsonProperty("base_catalog_revision") long baseCatalogRevision,
            @JsonProperty("expires_at") Instant expiresAt,
            List<ReferenceImportGuard.Issue> issues,
            @JsonProperty("created_count") int createdCount,
            @JsonProperty("updated_count") int updatedCount) {
        public Result {
            issues = List.copyOf(issues);
        }
    }

    public static final class Failure extends RuntimeException {
        public final int status;
        public final String code;

        public Failure(int status, String code, String safeMessage) {
            super(safeMessage);
            this.status = status;
            this.code = code;
        }
    }

    private record Context(
            String tenant, long actor, RuleOwnership.Actor identity, long catalog, Instant now) {}

    private record Validation(List<ReferenceImportGuard.Issue> issues, int created, int updated) {}

    private final ReferenceCatalogMapper mapper;
    private final ReferenceImportGuard guard;
    private final RuleDraftMapper identities;
    private final RuleOwnership ownership;
    private final AccountScopeMapper scopes;
    private final ObjectMapper json;

    public ReferenceImportStore(
            ReferenceCatalogMapper mapper,
            ReferenceImportGuard guard,
            RuleDraftMapper identities,
            RuleOwnership ownership,
            AccountScopeMapper scopes,
            ObjectMapper json) {
        this.mapper = mapper;
        this.guard = guard;
        this.identities = identities;
        this.ownership = ownership;
        this.scopes = scopes;
        this.json = json;
    }

    /** 预览成功或逐行拒绝均持久化不可变结果；解析或权限错误整笔不留幂等预占。 */
    @Transactional(isolation = Isolation.REPEATABLE_READ)
    public Result previewTrusted(String tenant, long actor, String key, byte[] body) {
        var prepared = guard.parse(body);
        Context ctx = context(tenant, actor);
        key = uuid(key);
        String fingerprint = hash(List.of("PREVIEW", prepared.hash()));
        Result replay = replay(ctx, key, fingerprint);
        if (replay != null) return replay;
        if (prepared.baseRevision() != ctx.catalog)
            throw fail(409, "CATALOG_CHANGED", "目录版本已变化，请重新查询");
        Validation checked = validate(ctx, prepared);
        ImportRow row = new ImportRow();
        row.id = UUID.randomUUID().toString();
        row.tenantId = ctx.tenant;
        row.actorId = ctx.actor;
        row.revision = 1;
        row.baseCatalogRevision = ctx.catalog;
        row.bodyJson = prepared.body();
        row.bodyHash = prepared.hash();
        row.issuesJson = write(checked.issues);
        row.state = checked.issues.isEmpty() ? "VALIDATED" : "REJECTED";
        row.createdCount = checked.created;
        row.updatedCount = checked.updated;
        row.createdAt = ctx.now;
        row.expiresAt = ctx.now.plusSeconds(900);
        mapper.insertImport(row);
        Result result = view(row, ctx.now);
        mapper.finish(ctx.tenant, ctx.actor, key, row.id, write(result));
        return result;
    }

    @Transactional(isolation = Isolation.REPEATABLE_READ)
    public Result getTrusted(String tenant, long actor, String id) {
        Context ctx = context(tenant, actor);
        ImportRow row = visibleImport(ctx, uuid(id));
        return view(row, ctx.now);
    }

    /** 所有版本、当前拥有者、关联可用性和整批冲突在同一事务重新验证。 */
    @Transactional(isolation = Isolation.REPEATABLE_READ)
    public Result commitTrusted(
            String tenant, long actor, String id, long expected, String key, String requestId) {
        Context ctx = context(tenant, actor);
        id = uuid(id);
        key = uuid(key);
        if (requestId != null) requestId = uuid(requestId);
        if (expected < 1 || expected >= ReferenceImportGuard.MAX_REVISION)
            throw fail(422, "FIELD_VALIDATION_FAILED", "预览版本无效");
        String fingerprint = hash(List.of("COMMIT", id, expected));
        Result replay = replay(ctx, key, fingerprint);
        if (replay != null) return replay;
        ImportRow row = visibleImport(ctx, id);
        if (row.revision != expected) throw fail(409, "REVISION_CONFLICT", "预览版本已变化");
        if (!"VALIDATED".equals(row.state)) throw fail(409, "INVALID_TRANSITION", "当前预览不可提交");
        if (!ctx.now.isBefore(row.expiresAt)) throw fail(410, "IMPORT_EXPIRED", "预览已过期，请重新预检");
        if (row.baseCatalogRevision != ctx.catalog)
            throw fail(409, "CATALOG_CHANGED", "目录版本已变化，请重新预检");
        var prepared = prepareStored(row);
        Validation checked = validate(ctx, prepared);
        if (!checked.issues.isEmpty()) throw fail(422, "REFERENCE_INVALID", "引用或拥有者已变化，请重新预检");
        if (ctx.catalog == ReferenceImportGuard.MAX_REVISION)
            throw fail(409, "REVISION_EXHAUSTED", "目录版本已达上限");
        List<Map<String, Object>> changes = new ArrayList<>();
        for (var item : prepared.items()) {
            RecordRow before = mapper.record(ctx.tenant, item.id());
            RecordRow record = new RecordRow();
            record.id = item.id();
            record.tenantId = ctx.tenant;
            record.kind = item.kind();
            record.sourceKey = item.sourceKey();
            record.ownerTeamId = item.teamId();
            record.availability = item.availability();
            record.valueJson = itemJson(item);
            record.valueHash = hashTree(record.valueJson);
            record.revision = before == null ? 1 : before.revision + 1;
            record.catalogRevision = ctx.catalog + 1;
            record.updatedAt = ctx.now;
            if (before == null) mapper.insertRecord(record);
            else if (mapper.updateRecord(record) != 1)
                throw fail(409, "REVISION_CONFLICT", "引用资料版本已变化");
            if ("PRODUCT".equals(item.kind())) {
                mapper.clearAgents(ctx.tenant, item.id());
                for (String agent : item.agentIds()) mapper.addAgent(ctx.tenant, item.id(), agent);
            }
            Map<String, Object> change = new LinkedHashMap<>();
            change.put("id", item.id());
            change.put("before_hash", before == null ? null : before.valueHash);
            change.put("after_hash", record.valueHash);
            changes.add(change);
        }
        if (mapper.advance(ctx.tenant, ctx.catalog) != 1
                || mapper.commit(ctx.tenant, id, expected) != 1)
            throw fail(409, "REVISION_CONFLICT", "目录或预览版本已变化");
        String event = UUID.randomUUID().toString();
        mapper.event(
                event,
                ctx.tenant,
                id,
                ctx.actor,
                ctx.identity.subjectId,
                requestId,
                prepared.source(),
                prepared.reason(),
                ctx.catalog,
                ctx.catalog + 1,
                write(changes),
                ctx.now);
        mapper.outbox(event, ctx.tenant, id, ctx.catalog + 1, ctx.now);
        row.state = "COMMITTED";
        row.revision++;
        Result result = view(row, ctx.now);
        mapper.finish(ctx.tenant, ctx.actor, key, id, write(result));
        return result;
    }

    private Context context(String tenant, long actor) {
        tenant = uuid(tenant);
        // 顺序与既有授权写协议一致：先权限时钟，再当前身份，最后目录版本；引用目录不依赖账户目录是否初始化。
        Long version = scopes.scopeVersion(tenant);
        if (version == null || version < 1)
            throw fail(503, "SCOPE_UNAVAILABLE", "当前授权版本不可用");
        var identity = ownership.actor(tenant, actor);
        Long catalog = mapper.lockVersion(tenant);
        if (catalog == null || catalog < 0 || catalog > ReferenceImportGuard.MAX_REVISION)
            throw fail(503, "CATALOG_UNAVAILABLE", "引用目录版本不可用");
        return new Context(tenant, actor, identity, catalog, mapper.now());
    }

    private Validation validate(Context ctx, ReferenceImportGuard.Prepared input) {
        List<ReferenceImportGuard.Issue> issues = new ArrayList<>(input.issues());
        int created = 0, updated = 0;
        // 格式已有错误的行不参与写入；行号由稳定UUID映射回原数组位置，避免错误行使后续行号错位。
        var raw = tree(input.body()).path("items");
        for (var item : input.items()) {
            int row = 0;
            while (row < raw.size()
                    && !item.id().equalsIgnoreCase(raw.get(row).path("id").asText())) row++;
            String tenantOfId = mapper.idTenant(item.id());
            RecordRow old = mapper.record(ctx.tenant, item.id());
            String sourceId = mapper.sourceId(ctx.tenant, item.kind(), item.sourceKey());
            if ((tenantOfId != null && !tenantOfId.equals(ctx.tenant))
                    || (sourceId != null && !sourceId.equals(item.id()))
                    || (old != null
                            && (!old.kind.equals(item.kind())
                                    || !old.sourceKey.equals(item.sourceKey())))) {
                issue(issues, row, "REFERENCE_CONFLICT");
                continue;
            }
            if ((old != null && !visible(ctx, tree(old.valueJson))) || !assignable(ctx, item)) {
                issue(issues, row, "OWNERSHIP_INVALID");
                continue;
            }
            boolean agentsValid = true;
            for (String id : item.agentIds()) {
                RecordRow agent = mapper.record(ctx.tenant, id);
                if (agent == null
                        || !"BUSINESS_AGENT".equals(agent.kind)
                        || !"AVAILABLE".equals(agent.availability)
                        || !item.teamId().equals(agent.ownerTeamId)
                        || !visible(ctx, tree(agent.valueJson))) {
                    agentsValid = false;
                    break;
                }
                for (String owner : item.ownerIds()) {
                    Long user = mapper.userId(ctx.tenant, owner);
                    if (user == null) {
                        agentsValid = false;
                        break;
                    }
                    var identity = ownership.actor(ctx.tenant, user);
                    if (!visible(
                            new Context(ctx.tenant, user, identity, ctx.catalog, ctx.now),
                            tree(agent.valueJson))) {
                        agentsValid = false;
                        break;
                    }
                }
            }
            if (!agentsValid) {
                issue(issues, row, "AGENT_REFERENCE_INVALID");
                continue;
            }
            if (old != null && old.revision >= ReferenceImportGuard.MAX_REVISION) {
                issue(issues, row, "REVISION_EXHAUSTED");
                continue;
            }
            if (old == null) created++;
            else updated++;
        }
        return new Validation(List.copyOf(issues), created, updated);
    }

    private boolean assignable(Context ctx, ReferenceImportGuard.Item item) {
        if (!Integer.valueOf(1).equals(identities.ownershipTeam(ctx.tenant, item.teamId())))
            return false;
        if ("USER".equals(ctx.identity.dataRole)
                && (!item.teamId().equals(ctx.identity.teamId)
                        || !item.ownerIds().equals(List.of(ctx.identity.subjectId)))) return false;
        if ("TEAM_ADMIN".equals(ctx.identity.dataRole)
                && !identities.managedTeams(ctx.tenant, ctx.actor).contains(item.teamId()))
            return false;
        for (String id : item.ownerIds()) {
            var owner = identities.ownershipOwner(ctx.tenant, id);
            if (owner == null || !owner.usable || !item.teamId().equals(owner.teamId)) return false;
        }
        return true;
    }

    private boolean visible(Context ctx, com.fasterxml.jackson.databind.JsonNode value) {
        return switch (ctx.identity.dataRole) {
            case "SUPER_ADMIN" -> true;
            case "TEAM_ADMIN" ->
                    identities
                            .managedTeams(ctx.tenant, ctx.actor)
                            .contains(value.path("owner_team_id").asText());
            case "USER" -> {
                boolean found = false;
                for (var owner : value.path("data_owner_user_ids"))
                    if (ctx.identity.subjectId.equals(owner.asText())) found = true;
                yield found;
            }
            default -> false;
        };
    }

    private ImportRow visibleImport(Context ctx, String id) {
        ImportRow row = mapper.lockImport(ctx.tenant, id);
        if (row == null) throw fail(404, "NOT_FOUND", "预览不存在或不可见");
        var input = prepareStored(row);
        if ("REJECTED".equals(row.state)) {
            if (row.actorId != ctx.actor && !"SUPER_ADMIN".equals(ctx.identity.dataRole)) throw fail(404, "NOT_FOUND", "预览不存在或不可见");
            return row;
        }
        if (input.items().isEmpty()
                && row.actorId != ctx.actor
                && !"SUPER_ADMIN".equals(ctx.identity.dataRole))
            throw fail(404, "NOT_FOUND", "预览不存在或不可见");
        for (var item : input.items())
            if (!visible(ctx, tree(itemJson(item)))) throw fail(404, "NOT_FOUND", "预览不存在或不可见");
        return row;
    }

    private Result replay(Context ctx, String key, String fingerprint) {
        mapper.reserve(ctx.tenant, ctx.actor, key, fingerprint);
        Replay replay = mapper.replay(ctx.tenant, ctx.actor, key);
        if (!fingerprint.equals(replay.requestHash))
            throw fail(409, "IDEMPOTENCY_CONFLICT", "幂等键已用于不同请求");
        if (replay.importId == null) return null;
        visibleImport(ctx, replay.importId);
        try {
            return json.readValue(replay.responseJson, Result.class);
        } catch (Exception error) {
            throw fail(503, "IMPORT_UNAVAILABLE", "预览结果暂不可用");
        }
    }

    private Result view(ImportRow row, Instant now) {
        String state =
                !"COMMITTED".equals(row.state) && !now.isBefore(row.expiresAt)
                        ? "EXPIRED"
                        : row.state;
        try {
            return new Result(
                    row.id,
                    row.revision,
                    state,
                    row.baseCatalogRevision,
                    row.expiresAt,
                    json.readValue(
                            row.issuesJson,
                            new TypeReference<List<ReferenceImportGuard.Issue>>() {}),
                    row.createdCount,
                    row.updatedCount);
        } catch (Exception error) {
            throw fail(503, "IMPORT_UNAVAILABLE", "预览结果暂不可用");
        }
    }

    private ReferenceImportGuard.Prepared prepareStored(ImportRow row) {
        var prepared = guard.prepare(tree(row.bodyJson));
        if (!prepared.hash().equals(row.bodyHash))
            throw fail(503, "IMPORT_UNAVAILABLE", "预览内容校验失败");
        return prepared;
    }

    private String itemJson(ReferenceImportGuard.Item item) {
        var value =
                json.createObjectNode()
                        .put("kind", item.kind())
                        .put("id", item.id())
                        .put("name", item.name())
                        .put("availability", item.availability())
                        .put("owner_team_id", item.teamId())
                        .put("source_key", item.sourceKey());
        value.set("data_owner_user_ids", json.valueToTree(item.ownerIds()));
        if ("PRODUCT".equals(item.kind()))
            value.set("allowed_agent_ids", json.valueToTree(item.agentIds()));
        return write(value);
    }

    private com.fasterxml.jackson.databind.JsonNode tree(String body) {
        try {
            return json.readTree(body);
        } catch (Exception error) {
            throw fail(503, "IMPORT_UNAVAILABLE", "引用资料暂不可用");
        }
    }

    private String write(Object value) {
        try {
            return json.writeValueAsString(value);
        } catch (Exception error) {
            throw fail(503, "IMPORT_UNAVAILABLE", "引用资料暂不可用");
        }
    }

    private String hashTree(String body) {
        return hash(tree(body));
    }

    private String hash(Object value) {
        try {
            return HexFormat.of()
                    .formatHex(
                            MessageDigest.getInstance("SHA-256")
                                    .digest(write(value).getBytes(StandardCharsets.UTF_8)));
        } catch (Exception error) {
            throw fail(503, "IMPORT_UNAVAILABLE", "引用摘要暂不可用");
        }
    }

    private String uuid(String value) {
        try {
            return ScopeRequestGuard.uuid(value);
        } catch (Exception error) {
            throw fail(422, "FIELD_VALIDATION_FAILED", "引用标识格式无效");
        }
    }

    private static void issue(List<ReferenceImportGuard.Issue> issues, int row, String code) {
        issues.add(new ReferenceImportGuard.Issue(row, code, "引用或归属校验失败：/items/" + row));
    }

    private static Failure fail(int status, String code, String message) {
        return new Failure(status, code, message);
    }
}
