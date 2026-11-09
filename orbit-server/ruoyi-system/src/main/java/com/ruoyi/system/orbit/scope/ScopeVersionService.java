package com.ruoyi.system.orbit.scope;

import com.ruoyi.system.orbit.rules.RuleOwnership;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.*;

/** 当前已实现授权输入的租户版本；不替代实时对象授权或未来模块的撤权接入。 */
@Service
public class ScopeVersionService {
    public static final long MAX_VERSION = 9007199254740991L;
    private final AccountScopeMapper mapper;
    private final RuleOwnership ownership;

    public ScopeVersionService(AccountScopeMapper mapper, RuleOwnership ownership) {
        this.mapper = mapper;
        this.ownership = ownership;
    }

    @Transactional(isolation = Isolation.REPEATABLE_READ)
    public long currentTrusted(String tenant, long actor) {
        tenant = ScopeRequestGuard.uuid(tenant);
        ownership.actor(tenant, actor);
        Long version = mapper.scopeVersion(tenant);
        if (version == null || version < 1 || version > MAX_VERSION)
            throw new AccountScopeService.Failure(503, "权限版本尚不可用");
        return version;
    }

    /** 读取下一页或消费缓存前使用；必须与实际数据查询共享外层事务及实时对象授权。 */
    @Transactional(isolation = Isolation.REPEATABLE_READ)
    public void requireCurrentTrusted(String tenant, long actor, long expected) {
        if (expected < 1 || expected > MAX_VERSION)
            throw new AccountScopeService.Failure(422, "权限版本无效");
        if (currentTrusted(tenant, actor) != expected)
            throw new AccountScopeService.Failure(409, "权限范围已变化，请重新查询");
    }
}
