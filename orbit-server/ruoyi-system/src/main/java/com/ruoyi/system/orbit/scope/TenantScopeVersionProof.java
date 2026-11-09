package com.ruoyi.system.orbit.scope;

import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.*;

/** 跨租户操作的双版本前置校验；不以求和/MAX伪造原合同的单个scope_version。 */
@Service
public class TenantScopeVersionProof {
    public record Proof(
            long actorId,
            String homeTenant,
            String targetTenant,
            String dataRole,
            long homeVersion,
            long targetVersion) {
        @Override
        public String toString() {
            return "TenantScopeVersionProof[REDACTED]";
        }
    }

    private final ServerTenantScope tenants;
    private final AccountScopeMapper mapper;

    public TenantScopeVersionProof(ServerTenantScope tenants, AccountScopeMapper mapper) {
        this.tenants = tenants;
        this.mapper = mapper;
    }

    /** 仅受信内部调用；必须与业务查询/写入共享外层事务，结果不是独立授权凭证。 */
    @Transactional(isolation = Isolation.REPEATABLE_READ)
    public Proof currentTrusted(String target) {
        target = ScopeRequestGuard.uuid(target);
        var scope = tenants.current();
        if (!scope.homeTenant().equals(target) && !"SUPER_ADMIN".equals(scope.dataRole()))
            throw new AccountScopeService.Failure(403, "不能访问其他租户的权限版本");
        if (!scope.tenantIds().contains(target))
            throw new AccountScopeService.Failure(404, "目标租户不可用");
        // 顺序固定，避免home/target顺序相反时引入不同的版本锁顺序；同租户只取一次。
        var ids =
                java.util.stream.Stream.of(scope.homeTenant(), target).distinct().sorted().toList();
        java.util.Map<String, Long> versions = new java.util.HashMap<>();
        for (String tenant : ids) {
            Long value = mapper.scopeVersion(tenant);
            if (value == null || value < 1 || value > ScopeVersionService.MAX_VERSION)
                throw new AccountScopeService.Failure(503, "权限版本尚不可用");
            versions.put(tenant, value);
        }
        return new Proof(
                scope.actorId(),
                scope.homeTenant(),
                target,
                scope.dataRole(),
                versions.get(scope.homeTenant()),
                versions.get(target));
    }

    @Transactional(isolation = Isolation.REPEATABLE_READ)
    public void requireCurrentTrusted(Proof expected) {
        if (expected == null
                || expected.homeVersion() < 1
                || expected.targetVersion() < 1
                || expected.homeVersion() > ScopeVersionService.MAX_VERSION
                || expected.targetVersion() > ScopeVersionService.MAX_VERSION)
            throw new AccountScopeService.Failure(422, "权限版本证明无效");
        Proof current = currentTrusted(expected.targetTenant());
        if (current.actorId() != expected.actorId()
                || !current.homeTenant().equals(expected.homeTenant()))
            throw new AccountScopeService.Failure(404, "权限版本证明不属于当前身份");
        if (!current.equals(expected)) throw new AccountScopeService.Failure(409, "权限范围已变化，请重新查询");
    }
}
