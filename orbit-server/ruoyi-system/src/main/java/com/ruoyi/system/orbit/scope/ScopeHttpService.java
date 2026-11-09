package com.ruoyi.system.orbit.scope;

import com.fasterxml.jackson.annotation.JsonProperty;
import com.fasterxml.jackson.core.JsonParser;
import com.fasterxml.jackson.databind.*;
import com.ruoyi.common.core.domain.model.LoginUser;
import com.ruoyi.common.utils.SecurityUtils;
import com.ruoyi.system.orbit.config.SecretCipher;
import java.time.Instant;
import java.util.*;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.*;

/** 公开范围操作的事务边界；身份来自若依JWT/Redis会话，权限每次查当前数据库。 */
@Service
public class ScopeHttpService {
    public record View(
            String id,
            int count,
            @JsonProperty("scope_version") long scopeVersion,
            String hash,
            @JsonProperty("created_at") Instant createdAt) {}

    private record Context(
            String tenant, long actor, String session, String role, List<String> tenants) {}

    private final AccountScopeMapper mapper;
    private final ServerTenantScope tenants;
    private final AccountScopeService scopes;
    private final ScopeMemberPager pager;
    private final SecretCipher cipher;
    private final ObjectMapper json;

    public ScopeHttpService(
            AccountScopeMapper mapper,
            ServerTenantScope tenants,
            AccountScopeService scopes,
            ScopeMemberPager pager,
            SecretCipher cipher,
            ObjectMapper json) {
        this.mapper = mapper;
        this.tenants = tenants;
        this.scopes = scopes;
        this.pager = pager;
        this.cipher = cipher;
        this.json = json;
    }

    @Transactional(isolation = Isolation.REPEATABLE_READ)
    public Map<String, String> csrf() {
        Context ctx = context();
        ready();
        return Map.of(
                "csrf_token",
                cipher.encrypt(
                        "scope-csrf-v1", ctx.tenant, ctx.session, "ORBIT_SCOPE_CSRF/" + ctx.actor));
    }

    @Transactional(isolation = Isolation.REPEATABLE_READ)
    public View create(String key, String csrf, String target, String body) {
        return create(key, csrf, target, body, null);
    }

    @Transactional(isolation = Isolation.REPEATABLE_READ)
    public View create(String key, String csrf, String target, String body, String requestId) {
        requestId = requestId == null ? null : ScopeRequestGuard.uuid(requestId);
        Context ctx = context();
        ready();
        String writeTenant = ctx.tenant;
        if (target != null) {
            if (!"SUPER_ADMIN".equals(ctx.role))
                throw fail(403, "PERMISSION_DENIED", "当前身份不能指定目标租户");
            String normalized;
            try {
                normalized = ScopeRequestGuard.uuid(target);
            } catch (Exception error) {
                throw fail(400, "INVALID_REQUEST", "目标租户格式无效");
            }
            if (!ctx.tenants.contains(normalized)) throw fail(404, "NOT_FOUND", "目标租户不在当前服务端授权范围");
            writeTenant = normalized;
        }
        try {
            if (csrf == null
                    || csrf.length() < 16
                    || csrf.length() > 255
                    || !"scope-csrf-v1"
                            .equals(
                                    cipher.decrypt(
                                            csrf,
                                            ctx.tenant,
                                            ctx.session,
                                            "ORBIT_SCOPE_CSRF/" + ctx.actor)))
                throw new IllegalArgumentException();
        } catch (Exception error) {
            throw fail(403, "CSRF_INVALID", "会话校验令牌无效，请重新获取");
        }
        JsonNode input;
        try {
            input =
                    json.reader()
                            .with(JsonParser.Feature.STRICT_DUPLICATE_DETECTION)
                            .with(DeserializationFeature.FAIL_ON_TRAILING_TOKENS)
                            .readTree(body);
        } catch (Exception error) {
            throw fail(400, "INVALID_REQUEST", "请求JSON结构无效");
        }
        exact(input, Set.of("mode", "account_ids", "filter"));
        if (!input.path("mode").isTextual()
                || !input.path("account_ids").isArray()
                || !(input.path("filter").isNull() || input.path("filter").isObject()))
            throw fail(400, "INVALID_REQUEST", "范围字段类型无效");
        if (input.path("filter").isObject())
            exact(
                    input.path("filter"),
                    Set.of("q", "status", "auth_status", "operator_user_id", "vendor_id"));
        AccountScopeService.Frozen frozen;
        try {
            frozen =
                    ctx.tenant.equals(writeTenant)
                            ? scopes.freezeTrusted(ctx.tenant, ctx.actor, key, input, requestId)
                            : scopes.freezeForSessionTrusted(writeTenant, key, input, requestId);
        } catch (IllegalArgumentException error) {
            throw fail(422, "BUSINESS_VALIDATION_FAILED", "范围模式、ID或筛选无效");
        }
        var row = frozen.snapshot();
        return new View(row.id, row.memberCount, row.scopeVersion, row.membersHash, row.createdAt);
    }

    @Transactional(isolation = Isolation.REPEATABLE_READ)
    public ScopeMemberPager.Page members(String id, String q, int size, String cursor) {
        Context ctx = context();
        try {
            id = ScopeRequestGuard.uuid(id);
            ScopeMemberPager.validateParameters(q, size, cursor);
            // 这里只定位服务端允许的本人快照；不锁快照，避免在目录门闩之前引入反向锁序。
            // 定位不是授权证明：下方分页仍在同事务按当前身份、门闩及权限版本锁定复核。
            var targets = mapper.snapshotTenants(ctx.actor, id, ctx.tenants);
            if (targets.isEmpty()) throw fail(404, "NOT_FOUND", "范围不存在或不可见");
            if (targets.size() != 1) throw fail(409, "SCOPE_CHANGED", "范围标识不唯一，请重新生成");
            String target = targets.getFirst();
            return ctx.tenant.equals(target)
                    ? pager.pageTrusted(ctx.tenant, ctx.actor, id, q, size, cursor)
                    : pager.pageForSessionTrusted(target, id, q, size, cursor);
        } catch (IllegalArgumentException error) {
            throw fail(400, "INVALID_REQUEST", "范围标识格式无效");
        }
    }

    private Context context() {
        var scope = tenants.current();
        LoginUser login = SecurityUtils.getLoginUser();
        if (!new HashSet<>(mapper.readableMenuIds(scope.actorId()))
                .containsAll(Set.of(31000L, 31010L, 31011L)))
            throw fail(403, "PERMISSION_DENIED", "没有对应菜单或读取权限");
        return new Context(
                scope.homeTenant(),
                scope.actorId(),
                login.getToken(),
                scope.dataRole(),
                scope.tenantIds());
    }

    private void exact(JsonNode node, Set<String> fields) {
        if (node == null || !node.isObject()) throw fail(400, "INVALID_REQUEST", "请求必须为对象");
        node.fieldNames()
                .forEachRemaining(
                        key -> {
                            if (!fields.contains(key)) throw fail(400, "UNKNOWN_FIELD", "请求包含未知字段");
                        });
        if (node.size() != fields.size()) throw fail(400, "INVALID_REQUEST", "请求缺少必要字段");
    }

    private void ready() {
        if (!cipher.isReady()) throw fail(503, "DEPENDENCY_UNAVAILABLE", "服务端独立密钥尚未配置");
    }

    private AccountScopeService.Failure fail(int status, String code, String message) {
        return new AccountScopeService.Failure(status, code, message);
    }
}
