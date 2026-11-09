package com.ruoyi.system.orbit.scope;

import com.ruoyi.system.orbit.rules.RuleDraftMapper;
import com.ruoyi.system.orbit.rules.RuleOwnership;
import java.time.Instant;
import java.util.*;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.*;

/** 范围冻结审计的内部读取门禁；不是完整AuditPage API，也不提供更新删除。 */
@Service
public class ScopeFreezeAuditReader {
    public static class Entry {
        public String id, targetTenantId, snapshotId, homeTenantId, dataRole, action;
        public String requestHash, membersHash, actorSubjectId, actorTeamId, requestId;
        public long actorId, homeVersion, targetVersion;
        public int memberCount;
        public Instant createdAt;

        @Override
        public String toString() {
            return "ScopeFreezeAudit[REDACTED]";
        }
    }

    private final ServerTenantScope tenants;
    private final AccountScopeMapper mapper;
    private final RuleOwnership ownership;
    private final RuleDraftMapper identities;

    public ScopeFreezeAuditReader(
            ServerTenantScope tenants,
            AccountScopeMapper mapper,
            RuleOwnership ownership,
            RuleDraftMapper identities) {
        this.tenants = tenants;
        this.mapper = mapper;
        this.ownership = ownership;
        this.identities = identities;
    }

    /** 当前会话+当前功能角色并集+当前数据角色；历史角色和调用方传入target都不能授予权限。 */
    @Transactional(isolation = Isolation.REPEATABLE_READ)
    public Entry readTrusted(String target, String id) {
        target = ScopeRequestGuard.uuid(target);
        id = ScopeRequestGuard.uuid(id);
        var scope = currentTargetTrusted(target);
        Entry entry = mapper.freezeAudit(target, id);
        if (entry == null) throw invisible();
        return authorizedEntry(scope, target, entry);
    }

    /** 批次读取的不可见结果在事务代理返回前转为空，不能用捕获代理404的方式跳过并污染外层事务。 */
    @Transactional(isolation = Isolation.REPEATABLE_READ)
    public Entry visibleEntryTrusted(String target, String id) {
        target = ScopeRequestGuard.uuid(target);
        id = ScopeRequestGuard.uuid(id);
        var scope = currentTargetTrusted(target);
        Entry entry = mapper.freezeAudit(target, id);
        if (entry == null) return null;
        try {
            return authorizedEntry(scope, target, entry);
        } catch (AccountScopeService.Failure failure) {
            if (failure.status() == 404) return null;
            throw failure;
        }
    }

    /** 查询批次同样需当前功能授权及受控目标；结果不可作为事务外授权凭据。 */
    @Transactional(isolation = Isolation.REPEATABLE_READ)
    public ServerTenantScope.Snapshot currentTargetTrusted(String target) {
        target = ScopeRequestGuard.uuid(target);
        var scope = tenants.current();
        if (!new HashSet<>(mapper.auditMenuIds(scope.actorId()))
                .containsAll(Set.of(31000L, 31080L, 31082L)))
            throw new AccountScopeService.Failure(403, "没有审计菜单或读取权限");
        if (!scope.tenantIds().contains(target)) throw invisible();
        return scope;
    }

    private Entry authorizedEntry(ServerTenantScope.Snapshot scope, String target, Entry entry) {
        if ("SUPER_ADMIN".equals(scope.dataRole())) return entry;
        if (!entry.homeTenantId.equals(scope.homeTenant())) throw invisible();
        if (entry.actorId == scope.actorId()) return entry;
        if (!"TEAM_ADMIN".equals(scope.dataRole()) || entry.actorTeamId == null) throw invisible();
        var teams = identities.managedTeams(scope.homeTenant(), scope.actorId());
        if (!teams.contains(entry.actorTeamId)) throw invisible();
        // 他人事件须仍有可见原对象；先取目录门闩，避免快照读锁与冻结反序。
        if (mapper.clock(target) == null) throw invisible();
        var snapshot = mapper.snapshotById(target, entry.actorId, entry.snapshotId);
        if (snapshot == null || !snapshot.ready) throw invisible();
        var actor = ownership.actor(scope.homeTenant(), scope.actorId());
        var access = new AccountScopeService.Access(actor.dataRole, actor.subjectId, teams);
        if (mapper.hasInvisibleMember(target, entry.snapshotId, access)) throw invisible();
        return entry;
    }

    private AccountScopeService.Failure invisible() {
        return new AccountScopeService.Failure(404, "审计不存在或不在当前数据范围");
    }
}
