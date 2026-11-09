package com.ruoyi.system.orbit.rules;

import com.fasterxml.jackson.databind.ObjectMapper;
import java.util.Set;
import org.springframework.stereotype.Component;

/** 规则内部写入的数据权限复核；不替代公共入口的登录、菜单、动作及跨租户server_scope鉴权。 */
@Component
public final class RuleOwnership {
    public static class Actor {
        public String subjectId, teamId, dataRole;
    }

    public static class Owner {
        public String subjectId, teamId;
        public boolean usable;
    }

    private final RuleDraftMapper mapper;
    private final ObjectMapper json;

    public RuleOwnership(RuleDraftMapper mapper, ObjectMapper json) {
        this.mapper = mapper;
        this.json = json;
    }

    /** 读取当前数据库授权而非会话缓存；查询共享锁须与规则写事务共同持有。 */
    public Actor actor(String tenant, long userId) {
        String contextTenant = mapper.ownershipContextTenant(userId);
        if (contextTenant == null) throw new RuleDraftStore.Failure(403, "当前规则数据授权已失效");
        if (contextTenant != null && !contextTenant.equals(tenant)) throw invisible();
        Actor actor = mapper.ownershipActor(tenant, userId);
        if (actor == null
                || actor.dataRole == null
                || !Set.of("USER", "TEAM_ADMIN", "SUPER_ADMIN").contains(actor.dataRole))
            throw new RuleDraftStore.Failure(403, "当前规则数据授权已失效");
        return actor;
    }

    public void require(String tenant, long userId, Actor actor, String body, boolean assigning) {
        String ownerId, teamId;
        try {
            var ownership = json.readTree(body).path("ownership");
            ownerId = RuleWriteGuard.uuid(ownership.path("owner_user_id").asText());
            teamId = RuleWriteGuard.uuid(ownership.path("owner_team_id").asText());
        } catch (Exception error) {
            throw invisible();
        }
        Owner owner = mapper.ownershipOwner(tenant, ownerId);
        Integer teamStatus = mapper.ownershipTeam(tenant, teamId);
        if (owner == null || teamStatus == null) throw invisible();
        boolean allowed =
                switch (actor.dataRole) {
                    case "USER" -> actor.subjectId.equals(ownerId);
                    case "TEAM_ADMIN" -> mapper.managedTeams(tenant, userId).contains(teamId);
                    case "SUPER_ADMIN" -> true;
                    default -> false;
                };
        if (!allowed) throw invisible();
        // 存量按冻结owner/team授权，不因成员换队改写旧资源；新分配必须核验当前成员关系。
        if (assigning && (!owner.usable || teamStatus != 1 || !owner.teamId.equals(teamId)))
            throw new RuleDraftStore.Failure(422, "规则拥有者、所属团队或当前成员关系不可用");
    }

    private RuleDraftStore.Failure invisible() {
        return new RuleDraftStore.Failure(404, "规则不存在或不在当前数据范围");
    }
}
