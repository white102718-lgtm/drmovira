package com.ruoyi.system.orbit.scope;

import com.fasterxml.jackson.annotation.JsonIgnore;
import com.fasterxml.jackson.databind.*;
import com.ruoyi.system.orbit.rules.*;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.time.Instant;
import java.util.*;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.*;

/** 账户范围冻结底层事务；公开访问由ScopeHttpService授权，Meta来源仍未验证。 */
@Service
public class AccountScopeService {
    public record Access(String role, String subject, List<String> teams) {
        public Access {
            teams = List.copyOf(teams);
        }
    }

    public static class Member {
        public String accountId, externalId, name, authStatus, accountStatus, sourceState;
        public long revision;

        @Override
        public String toString() {
            return "ScopeMember[REDACTED]";
        }
    }

    public static class Snapshot {
        public String tenantId, id, requestKey, requestHash, accessHash, membersHash;
        public long actorId, directoryRevision;
        public Long scopeVersion;
        public int memberCount;
        public boolean ready;
        public Instant createdAt;
        @JsonIgnore public String requestJson;

        @Override
        public String toString() {
            return "ScopeSnapshot[REDACTED]";
        }
    }

    public record Frozen(Snapshot snapshot, List<Member> members) {
        public Frozen {
            members = List.copyOf(members);
        }
    }

    public static final class Failure extends RuntimeException {
        private final int status;
        private final String code;

        public Failure(int status, String message) {
            this(
                    status,
                    switch (status) {
                        case 400 -> "INVALID_REQUEST";
                        case 401 -> "SESSION_REQUIRED";
                        case 403 -> "PERMISSION_DENIED";
                        case 404 -> "NOT_FOUND";
                        case 409 -> "SCOPE_CHANGED";
                        case 503 -> "DEPENDENCY_UNAVAILABLE";
                        default -> "BUSINESS_VALIDATION_FAILED";
                    },
                    message);
        }

        public Failure(int status, String code, String message) {
            super(message);
            this.status = status;
            this.code = code;
        }

        public String code() {
            return code;
        }

        public int status() {
            return status;
        }
    }

    private final AccountScopeMapper mapper;
    private final RuleDraftMapper identities;
    private final RuleOwnership ownership;
    private final ScopeRequestGuard guard;
    private final ObjectMapper json;
    private final ScopeVersionService versions;
    private final TenantScopeVersionProof tenantProofs;
    private final ServerTenantScope tenants;

    public AccountScopeService(
            AccountScopeMapper mapper,
            RuleDraftMapper identities,
            RuleOwnership ownership,
            ScopeRequestGuard guard,
            ObjectMapper json,
            ScopeVersionService versions,
            TenantScopeVersionProof tenantProofs,
            ServerTenantScope tenants) {
        this.mapper = mapper;
        this.identities = identities;
        this.ownership = ownership;
        this.guard = guard;
        this.json = json;
        this.versions = versions;
        this.tenantProofs = tenantProofs;
        this.tenants = tenants;
    }

    @Transactional(isolation = Isolation.REPEATABLE_READ)
    public Frozen freezeTrusted(String tenant, long actor, String key, JsonNode input) {
        return freezeTrusted(tenant, actor, key, input, null);
    }

    /** HTTP入口显式传入服务端请求UUID；内部非HTTP调用不伪造请求关联。 */
    @Transactional(isolation = Isolation.REPEATABLE_READ)
    public Frozen freezeTrusted(
            String tenant, long actor, String key, JsonNode input, String requestId) {
        requestId = requestId == null ? null : ScopeRequestGuard.uuid(requestId);
        tenant = ScopeRequestGuard.uuid(tenant);
        key = requestKey(key);
        var selection = guard.prepare(input);
        Access access = access(tenant, actor);
        return freeze(tenant, actor, key, selection, access, null, requestId);
    }

    /** 当前会话的目标租户冻结；公开入口另行校验当前动作权限与CSRF。 */
    @Transactional(isolation = Isolation.REPEATABLE_READ)
    public Frozen freezeForSessionTrusted(String target, String key, JsonNode input) {
        return freezeForSessionTrusted(target, key, input, null);
    }

    @Transactional(isolation = Isolation.REPEATABLE_READ)
    public Frozen freezeForSessionTrusted(
            String target, String key, JsonNode input, String requestId) {
        requestId = requestId == null ? null : ScopeRequestGuard.uuid(requestId);
        target = sessionTarget(target);
        // 与目录发布器统一先锁目录门闩，再锁权限版本，避免相反锁序形成死锁。
        mapper.reserveClock(target);
        mapper.clock(target);
        var proof = tenantProofs.currentTrusted(target);
        // 普通身份仍只读自己的数据；跨租户SUPER角色由当前home授权决定，不伪造target用户映射。
        Access access = access(proof.homeTenant(), proof.actorId());
        return freeze(
                proof.targetTenant(),
                proof.actorId(),
                requestKey(key),
                guard.prepare(input),
                access,
                proof,
                requestId);
    }

    private Frozen freeze(
            String tenant,
            long actor,
            String key,
            ScopeRequestGuard.Selection selection,
            Access access,
            TenantScopeVersionProof.Proof proof,
            String requestId) {
        Snapshot proposed = new Snapshot();
        proposed.tenantId = tenant;
        proposed.id = UUID.randomUUID().toString();
        proposed.actorId = actor;
        proposed.requestKey = key;
        proposed.requestJson = selection.canonical();
        proposed.requestHash = hash(selection.canonical());
        proposed.accessHash = hash(encode(access));
        proposed.createdAt = Instant.now();
        mapper.reserveClock(tenant);
        proposed.directoryRevision = mapper.clock(tenant);
        proposed.scopeVersion =
                proof == null ? versions.currentTrusted(tenant, actor) : proof.targetVersion();
        mapper.reserve(proposed);
        Snapshot stored = mapper.locked(tenant, actor, key);
        if (!stored.requestHash.equals(proposed.requestHash))
            throw new Failure(409, "IDEMPOTENCY_CONFLICT", "范围幂等键已用于不同筛选");
        if (stored.ready) {
            if (proof != null) requireBoundProof(tenant, stored.id, proof);
            if (stored.scopeVersion == null) throw new Failure(409, "旧范围缺少权限版本，请重新生成");
            List<Member> frozen = mapper.members(tenant, stored.id);
            reauthorize(tenant, access, stored, frozen);
            return new Frozen(stored, frozen);
        }
        List<Member> members = mapper.candidates(tenant, access, selection);
        if (members.size() > 50000) throw new Failure(422, "账户范围超过50000项，不允许截断");
        if (selection.mode().equals("IDS") && members.size() != selection.accountIds().size())
            throw invisible();
        proposed.id = stored.id;
        proposed.memberCount = members.size();
        proposed.membersHash =
                hash(
                        encode(
                                members.stream()
                                        .map(
                                                row ->
                                                        List.of(
                                                                row.accountId,
                                                                row.externalId,
                                                                row.name,
                                                                row.revision))
                                        .toList()));
        for (int i = 0; i < members.size(); i += 1000)
            mapper.insertMembers(
                    tenant, proposed.id, members.subList(i, Math.min(i + 1000, members.size())));
        mapper.recordScopeVersion(proposed);
        mapper.finish(proposed);
        if (proof != null) mapper.bindTenantProof(tenant, proposed.id, proof);
        // 普通同租户与会话目标路径均写真实actor+目标；重放分支已返回，不重复记成功事件。
        var auditProof =
                proof != null
                        ? proof
                        : new TenantScopeVersionProof.Proof(
                                actor,
                                tenant,
                                tenant,
                                access.role(),
                                proposed.scopeVersion,
                                proposed.scopeVersion);
        mapper.recordFreezeAudit(
                proposed, auditProof, ownership.actor(auditProof.homeTenant(), actor), requestId);
        return new Frozen(mapper.locked(tenant, actor, key), mapper.members(tenant, proposed.id));
    }

    /** 内部按会话读取已绑定快照；双版本或身份变化后旧快照必须重新冻结。 */
    @Transactional(isolation = Isolation.REPEATABLE_READ)
    public Snapshot sessionSnapshotTrusted(String target, String id) {
        target = sessionTarget(target);
        if (mapper.clock(target) == null) throw invisible();
        var proof = tenantProofs.currentTrusted(target);
        id = ScopeRequestGuard.uuid(id);
        Snapshot stored = mapper.snapshotById(proof.targetTenant(), proof.actorId(), id);
        if (stored == null || !stored.ready) throw invisible();
        requireBoundProof(proof.targetTenant(), id, proof);
        if (stored.scopeVersion == null || stored.scopeVersion != proof.targetVersion())
            throw new Failure(409, "范围目标权限版本缺失或不一致，请重新生成");
        Access access = access(proof.homeTenant(), proof.actorId());
        if (!stored.accessHash.equals(hash(encode(access)))
                || mapper.hasInvisibleMember(proof.targetTenant(), id, access)) throw invisible();
        return stored;
    }

    private String sessionTarget(String target) {
        target = ScopeRequestGuard.uuid(target);
        var scope = tenants.current();
        if (!target.equals(scope.homeTenant()) && !"SUPER_ADMIN".equals(scope.dataRole()))
            throw new Failure(403, "不能访问其他租户的账户范围");
        if (!scope.tenantIds().contains(target)) throw invisible();
        return target;
    }

    private void requireBoundProof(
            String tenant, String id, TenantScopeVersionProof.Proof current) {
        var stored = mapper.boundTenantProof(tenant, id);
        // 不给旧快照补写当前版本，否则会掩盖生成后发生的撤权。
        if (stored == null) throw new Failure(409, "旧范围缺少双租户权限版本，请重新生成");
        if (stored.actorId() != current.actorId()
                || !stored.homeTenant().equals(current.homeTenant())) throw invisible();
        if (!stored.equals(current)) throw new Failure(409, "权限范围已变化，请重新查询");
    }

    /** 每次重放/消费检查当前成员数据权，不以旧成员、旧角色或旧团队管理范围作为授权。 */
    private List<Member> reauthorize(
            String tenant, Access access, Snapshot snapshot, List<Member> frozen) {
        if (!snapshot.accessHash.equals(hash(encode(access)))) throw invisible();
        if (frozen.isEmpty()) return List.of();
        var request = json.createObjectNode().put("mode", "IDS");
        var ids = request.putArray("account_ids");
        frozen.forEach(row -> ids.add(row.accountId));
        request.putNull("filter");
        List<Member> current = mapper.candidates(tenant, access, guard.prepare(request));
        if (current.size() != frozen.size()) throw invisible();
        return current;
    }

    @Transactional(isolation = Isolation.REPEATABLE_READ)
    public void requireExecutableTrusted(String tenant, long actor, String key) {
        tenant = ScopeRequestGuard.uuid(tenant);
        key = requestKey(key);
        Access access = access(tenant, actor);
        Snapshot stored = mapper.locked(tenant, actor, key);
        if (stored == null || !stored.ready) throw invisible();
        List<Member> current =
                reauthorize(tenant, access, stored, mapper.members(tenant, stored.id));
        if (current.isEmpty()) throw new Failure(422, "空账户范围不可执行");
        for (Member row : current)
            if (!"AUTHORIZED".equals(row.authStatus)
                    || !"ACTIVE".equals(row.accountStatus)
                    || !"META_VERIFIED".equals(row.sourceState))
                throw new Failure(422, "账户授权、状态或真实来源尚不可执行");
    }

    private Access access(String tenant, long actor) {
        var principal = ownership.actor(tenant, actor);
        List<String> teams =
                principal.dataRole.equals("TEAM_ADMIN")
                        ? new ArrayList<>(identities.managedTeams(tenant, actor))
                        : new ArrayList<>();
        Collections.sort(teams);
        return new Access(principal.dataRole, principal.subjectId, teams);
    }

    /** 成员分页的可信读取门槛；整份范围撤权即拒绝，不只检查当前显示页。 */
    @Transactional(isolation = Isolation.REPEATABLE_READ)
    public Snapshot authorizedSnapshotTrusted(String tenant, long actor, String id) {
        tenant = ScopeRequestGuard.uuid(tenant);
        id = ScopeRequestGuard.uuid(id);
        Access access = access(tenant, actor);
        // 与创建/重放及目录发布保持相同顺序：目录门闩在快照和权限版本之前。
        if (mapper.clock(tenant) == null) throw invisible();
        Snapshot stored = mapper.snapshotById(tenant, actor, id);
        if (stored == null || !stored.ready) throw invisible();
        if (stored.scopeVersion == null) throw new Failure(409, "旧范围缺少权限版本，请重新生成");
        // 目录门闩已持有到事务结束，权限检查与分页之间不会发生账户转移。
        if (!stored.accessHash.equals(hash(encode(access)))) throw invisible();
        // V009/V010将当前授权及目录身份输入与版本同事务递增；锁定且未变化的版本证明范围授权未变。
        // 版本变化时仍查整份范围，区分对象撤权404与其他授权变化409，不能静默返回部分成员。
        long currentVersion = versions.currentTrusted(tenant, actor);
        if (currentVersion != stored.scopeVersion) {
            if (mapper.hasInvisibleMember(tenant, id, access)) throw invisible();
            throw new Failure(409, "权限范围已变化，请重新查询");
        }
        return stored;
    }

    private String encode(Object value) {
        try {
            return json.writeValueAsString(value);
        } catch (Exception error) {
            throw new Failure(422, "账户范围无法冻结");
        }
    }

    private String hash(String value) {
        try {
            return HexFormat.of()
                    .formatHex(
                            MessageDigest.getInstance("SHA-256")
                                    .digest(value.getBytes(StandardCharsets.UTF_8)));
        } catch (Exception error) {
            throw new Failure(422, "账户范围摘要无法生成");
        }
    }

    private Failure invisible() {
        return new Failure(404, "范围不存在或已不在当前数据权限内");
    }

    private String requestKey(String key) {
        if (key == null || !key.matches("[ -~]{16,128}"))
            throw new Failure(400, "幂等键必须为16至128位可打印ASCII");
        return key;
    }
}
