package com.ruoyi.system.orbit.rules;

import org.apache.ibatis.annotations.Param;

/** 内部草稿持久化；所有查询显式租户，正文/事件/幂等记录同事务。 */
public interface RuleDraftMapper {
    String ownershipContextTenant(@Param("user") long user);

    RuleOwnership.Actor ownershipActor(@Param("tenant") String tenant, @Param("user") long user);

    RuleOwnership.Owner ownershipOwner(
            @Param("tenant") String tenant, @Param("owner") String owner);

    Integer ownershipTeam(@Param("tenant") String tenant, @Param("team") String team);

    java.util.List<String> managedTeams(@Param("tenant") String tenant, @Param("user") long user);

    Integer activeTenant(@Param("tenant") String tenant);

    void reserve(
            @Param("tenant") String tenant,
            @Param("actor") long actor,
            @Param("key") String key,
            @Param("hash") String hash);

    RuleDraftStore.Row replay(
            @Param("tenant") String tenant, @Param("actor") long actor, @Param("key") String key);

    RuleDraftStore.Row lock(@Param("tenant") String tenant, @Param("id") String id);

    RuleDraftStore.Row version(
            @Param("tenant") String tenant,
            @Param("id") String id,
            @Param("revision") long revision);

    void insert(RuleDraftStore.Row row);

    int update(RuleDraftStore.Row row);

    void freeze(RuleDraftStore.Row row);

    void event(
            @Param("row") RuleDraftStore.Row row,
            @Param("actor") long actor,
            @Param("reason") String reason);

    void finish(
            @Param("tenant") String tenant,
            @Param("actor") long actor,
            @Param("key") String key,
            @Param("row") RuleDraftStore.Row row);
}
