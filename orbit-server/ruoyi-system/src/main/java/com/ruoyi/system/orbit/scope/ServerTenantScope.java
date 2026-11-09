package com.ruoyi.system.orbit.scope;

import com.ruoyi.common.core.domain.model.LoginUser;
import com.ruoyi.common.utils.SecurityUtils;
import com.ruoyi.system.orbit.rules.RuleDraftMapper;
import com.ruoyi.system.orbit.rules.RuleOwnership;
import java.util.List;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Isolation;
import org.springframework.transaction.annotation.Transactional;

/** 会话身份下的服务端租户目录；不接受客户端角色、actor或任意租户列表。 */
@Service
public class ServerTenantScope {
    /** 内部只读结果，不是可缓存的授权凭证；业务操作仍须同事务复核权限、版本和审计。 */
    public record Snapshot(
            long actorId, String homeTenant, String dataRole, List<String> tenantIds) {
        public Snapshot {
            tenantIds = List.copyOf(tenantIds);
        }

        @Override
        public String toString() {
            return "ServerTenantScope[REDACTED]";
        }
    }

    private final RuleDraftMapper identities;
    private final RuleOwnership ownership;
    private final AccountScopeMapper mapper;

    public ServerTenantScope(
            RuleDraftMapper identities, RuleOwnership ownership, AccountScopeMapper mapper) {
        this.identities = identities;
        this.ownership = ownership;
        this.mapper = mapper;
    }

    /** 每次读取当前有效身份；SUPER_ADMIN的全部仅指系统内启用租户。 */
    @Transactional(isolation = Isolation.REPEATABLE_READ)
    public Snapshot current() {
        LoginUser login;
        try {
            login = SecurityUtils.getLoginUser();
            if (login.getUserId() == null
                    || login.getToken() == null
                    || !login.getToken().matches("[A-Za-z0-9_-]{16,128}"))
                throw new IllegalArgumentException();
        } catch (Exception failure) {
            throw new AccountScopeService.Failure(401, "SESSION_REQUIRED", "请重新登录");
        }
        String home = identities.ownershipContextTenant(login.getUserId());
        if (home == null)
            throw new AccountScopeService.Failure(403, "PERMISSION_DENIED", "当前数据授权已失效");
        var actor = ownership.actor(home, login.getUserId());
        List<String> tenants =
                "SUPER_ADMIN".equals(actor.dataRole) ? mapper.enabledTenantIds() : List.of(home);
        if (!tenants.contains(home))
            throw new AccountScopeService.Failure(403, "PERMISSION_DENIED", "当前租户授权已失效");
        return new Snapshot(login.getUserId(), home, actor.dataRole, tenants);
    }

    /** 只解析受控写请求头；解析成功不表示跨租户业务存储、权限版本或审计已实现。 */
    @Transactional(isolation = Isolation.REPEATABLE_READ)
    public String resolveWriteTarget(String header) {
        Snapshot scope = current();
        if (header == null) return scope.homeTenant();
        if (!"SUPER_ADMIN".equals(scope.dataRole()))
            throw new AccountScopeService.Failure(403, "PERMISSION_DENIED", "当前身份不能指定目标租户");
        String tenant;
        try {
            tenant = ScopeRequestGuard.uuid(header);
        } catch (IllegalArgumentException failure) {
            throw new AccountScopeService.Failure(400, "INVALID_REQUEST", "目标租户格式无效");
        }
        if (!scope.tenantIds().contains(tenant))
            throw new AccountScopeService.Failure(404, "NOT_FOUND", "目标租户不可用");
        return tenant;
    }
}
