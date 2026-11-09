package com.ruoyi.system.orbit.scope;

import java.util.List;
import org.apache.ibatis.annotations.Param;

/** 范围目录、冻结成员与幂等元数据均显式限定租户。 */
public interface AccountScopeMapper {
    void recordFreezeAudit(
            @Param("row") AccountScopeService.Snapshot row,
            @Param("proof") TenantScopeVersionProof.Proof proof,
            @Param("actorIdentity") com.ruoyi.system.orbit.rules.RuleOwnership.Actor actorIdentity,
            @Param("requestId") String requestId);

    void bindTenantProof(
            @Param("tenant") String tenant,
            @Param("id") String id,
            @Param("proof") TenantScopeVersionProof.Proof proof);

    TenantScopeVersionProof.Proof boundTenantProof(
            @Param("tenant") String tenant, @Param("id") String id);

    List<Long> auditMenuIds(@Param("actor") long actor);

    List<Long> auditPageMenuIds(@Param("actor") long actor);

    ScopeFreezeAuditReader.Entry freezeAudit(
            @Param("tenant") String tenant, @Param("id") String id);

    java.time.Instant auditQueryTime();

    List<ScopeFreezeAuditReader.Entry> auditCandidates(
            @Param("tenant") String tenant,
            @Param("q") String escapedQuery,
            @Param("operator") String operator,
            @Param("from") java.time.Instant from,
            @Param("until") java.time.Instant until,
            @Param("cutoff") java.time.Instant cutoff,
            @Param("afterAt") java.time.Instant afterAt,
            @Param("afterId") String afterId);

    List<String> snapshotTenants(
            @Param("actor") long actor,
            @Param("id") String id,
            @Param("tenants") List<String> tenants);

    List<String> enabledTenantIds();

    List<Long> readableMenuIds(@Param("actor") long actor);

    AccountScopeService.Snapshot snapshotById(
            @Param("tenant") String tenant, @Param("actor") long actor, @Param("id") String id);

    boolean hasInvisibleMember(
            @Param("tenant") String tenant,
            @Param("id") String id,
            @Param("access") AccountScopeService.Access access);

    List<AccountScopeService.Member> memberPage(
            @Param("tenant") String tenant,
            @Param("id") String id,
            @Param("after") String after,
            @Param("q") String q,
            @Param("escaped") String escaped,
            @Param("limit") int limit);

    Long scopeVersion(@Param("tenant") String tenant);

    void recordScopeVersion(AccountScopeService.Snapshot row);

    boolean directoryExists(@Param("tenant") String tenant, @Param("id") String id);

    void insertDirectory(
            @Param("tenant") String tenant,
            @Param("row") AccountDirectoryPublisher.Entry row,
            @Param("revision") long revision);

    void updateDirectory(
            @Param("tenant") String tenant,
            @Param("row") AccountDirectoryPublisher.Entry row,
            @Param("revision") long revision);

    int deleteDirectory(@Param("tenant") String tenant, @Param("id") String id);

    void advanceClock(@Param("tenant") String tenant, @Param("revision") long revision);

    void reserveClock(@Param("tenant") String tenant);

    Long clock(@Param("tenant") String tenant);

    void reserve(AccountScopeService.Snapshot row);

    AccountScopeService.Snapshot locked(
            @Param("tenant") String tenant, @Param("actor") long actor, @Param("key") String key);

    List<AccountScopeService.Member> candidates(
            @Param("tenant") String tenant,
            @Param("access") AccountScopeService.Access access,
            @Param("request") ScopeRequestGuard.Selection request);

    void insertMembers(
            @Param("tenant") String tenant,
            @Param("snapshot") String snapshot,
            @Param("members") List<AccountScopeService.Member> members);

    List<AccountScopeService.Member> members(
            @Param("tenant") String tenant, @Param("id") String id);

    void finish(AccountScopeService.Snapshot row);
}
