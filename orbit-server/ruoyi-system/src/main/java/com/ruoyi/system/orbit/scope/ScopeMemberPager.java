package com.ruoyi.system.orbit.scope;

import com.fasterxml.jackson.annotation.JsonProperty;
import com.fasterxml.jackson.databind.*;
import com.ruoyi.system.orbit.config.SecretCipher;
import java.text.Normalizer;
import java.time.Instant;
import java.util.*;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.*;

/** 冻结成员分页核心；公开登录/动作授权及HTTP参数适配仍由后续入口负责。 */
@Service
public class ScopeMemberPager {
    public record Item(
            @JsonProperty("account_id") String accountId,
            @JsonProperty("external_id") String externalId,
            String name) {
        @Override
        public String toString() {
            return "ScopePageItem[REDACTED]";
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
            return "ScopeMemberPage[REDACTED]";
        }
    }

    private final AccountScopeMapper mapper;
    private final AccountScopeService scopes;
    private final SecretCipher cipher;
    private final ObjectMapper json;

    public ScopeMemberPager(
            AccountScopeMapper mapper,
            AccountScopeService scopes,
            SecretCipher cipher,
            ObjectMapper json) {
        this.mapper = mapper;
        this.scopes = scopes;
        this.cipher = cipher;
        this.json = json;
    }

    /** 共享事务持有目录/授权锁直至成员查询结束；不接受客户端传入actor或tenant作为公开授权依据。 */
    @Transactional(isolation = Isolation.REPEATABLE_READ)
    public Page pageTrusted(
            String tenant, long actor, String id, String query, int pageSize, String cursor) {
        return page(tenant, actor, id, query, pageSize, cursor, false);
    }

    /** 内部会话目标分页；身份由当前会话确定，双租户版本已随冻结快照持久化。 */
    @Transactional(isolation = Isolation.REPEATABLE_READ)
    public Page pageForSessionTrusted(
            String target, String id, String query, int pageSize, String cursor) {
        return page(target, 0, id, query, pageSize, cursor, true);
    }

    private Page page(
            String tenant,
            long actor,
            String id,
            String query,
            int pageSize,
            String cursor,
            boolean session) {
        tenant = ScopeRequestGuard.uuid(tenant);
        id = ScopeRequestGuard.uuid(id);
        String q = validateParameters(query, pageSize, cursor);
        var snapshot =
                session
                        ? scopes.sessionSnapshotTrusted(tenant, id)
                        : scopes.authorizedSnapshotTrusted(tenant, actor, id);
        actor = snapshot.actorId;
        var proof = session ? mapper.boundTenantProof(tenant, id) : null;
        if (session && proof == null) throw new AccountScopeService.Failure(409, "范围缺少双租户权限版本");
        if (!cipher.isReady()) throw new AccountScopeService.Failure(503, "成员游标加密服务尚未配置");
        String after = null;
        String purpose = (session ? "SCOPE_SESSION_MEMBERS_V2/" : "SCOPE_MEMBERS_V1/") + actor;
        Set<String> expectedFields =
                new HashSet<>(Set.of("v", "after", "scope", "hash", "q", "size"));
        if (session) expectedFields.addAll(Set.of("home", "home_scope", "role"));
        if (cursor != null) {
            try {
                JsonNode state = json.readTree(cipher.decrypt(cursor, tenant, id, purpose));
                Set<String> fields = new HashSet<>();
                state.fieldNames().forEachRemaining(fields::add);
                if (!state.isObject()
                        || !fields.equals(expectedFields)
                        || !state.path("v").isIntegralNumber()
                        || !state.path("v").canConvertToInt()
                        || state.path("v").intValue() != (session ? 2 : 1)
                        || !state.path("scope").isIntegralNumber()
                        || !state.path("scope").canConvertToLong()
                        || state.path("scope").longValue() != snapshot.scopeVersion
                        || !state.path("size").isIntegralNumber()
                        || !state.path("size").canConvertToInt()
                        || state.path("size").intValue() != pageSize
                        || !state.path("hash").isTextual()
                        || !state.path("hash").textValue().equals(snapshot.membersHash)
                        || !state.path("q").isTextual()
                        || !state.path("q").textValue().equals(q)
                        || !state.path("after").isTextual()) throw invalid();
                if (session
                        && (!state.path("home").isTextual()
                                || !state.path("home").textValue().equals(proof.homeTenant())
                                || !state.path("home_scope").isIntegralNumber()
                                || !state.path("home_scope").canConvertToLong()
                                || state.path("home_scope").longValue() != proof.homeVersion()
                                || !state.path("role").isTextual()
                                || !state.path("role").textValue().equals(proof.dataRole())))
                    throw invalid();
                after = ScopeRequestGuard.uuid(state.path("after").textValue());
            } catch (Exception error) {
                throw invalid();
            }
        }
        List<AccountScopeService.Member> rows =
                mapper.memberPage(
                        tenant,
                        id,
                        after,
                        q,
                        q.replace("!", "!!").replace("%", "!%").replace("_", "!_"),
                        pageSize + 1);
        List<Item> items =
                rows.stream()
                        .limit(pageSize)
                        .map(row -> new Item(row.accountId, row.externalId, row.name))
                        .toList();
        String next = null;
        if (rows.size() > pageSize) {
            var state =
                    json.createObjectNode()
                            .put("v", session ? 2 : 1)
                            .put("after", items.getLast().accountId())
                            .put("scope", snapshot.scopeVersion)
                            .put("hash", snapshot.membersHash)
                            .put("q", q)
                            .put("size", pageSize);
            if (session)
                state.put("home", proof.homeTenant())
                        .put("home_scope", proof.homeVersion())
                        .put("role", proof.dataRole());
            try {
                next = cipher.encrypt(json.writeValueAsString(state), tenant, id, purpose);
            } catch (Exception error) {
                throw new AccountScopeService.Failure(503, "成员游标生成失败");
            }
        }
        return new Page(items, next, snapshot.createdAt, snapshot.scopeVersion);
    }

    /** 定位不存在的快照前也校验参数，保持公开422边界且不依赖数据库对象存在。 */
    static String validateParameters(String query, int pageSize, String cursor) {
        if (!Set.of(20, 50, 100, 200).contains(pageSize)
                || (cursor != null && (cursor.isEmpty() || cursor.length() > 2048)))
            throw invalid();
        String q = Normalizer.normalize(query == null ? "" : query, Normalizer.Form.NFC).strip();
        if (q.codePointCount(0, q.length()) > 100
                || q.codePoints().anyMatch(Character::isISOControl)) throw invalid();
        return q;
    }

    private static AccountScopeService.Failure invalid() {
        return new AccountScopeService.Failure(422, "成员分页筛选、页大小或游标无效");
    }
}
