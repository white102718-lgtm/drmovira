package com.ruoyi.system.orbit.reference;

import java.time.Instant;
import org.apache.ibatis.annotations.*;

/** 所有目录访问显式携带租户；跨租户ID检测只返回所属租户，不暴露资料正文。 */
@Mapper
public interface ReferenceCatalogMapper {
    @Select(
            "SELECT revision FROM orbit_reference_catalog_version WHERE tenant_id=#{tenant} FOR UPDATE")
    Long lockVersion(String tenant);

    @Update(
            "UPDATE orbit_reference_catalog_version SET revision=revision+1 WHERE tenant_id=#{tenant} AND revision=#{version} AND revision<9007199254740991")
    int advance(@Param("tenant") String tenant, @Param("version") long version);

    @Select("SELECT UTC_TIMESTAMP(3)")
    Instant now();

    @Select("SELECT tenant_id FROM orbit_reference_record WHERE id=#{id}")
    String idTenant(String id);

    @Select(
            "SELECT id FROM orbit_reference_record WHERE tenant_id=#{tenant} AND kind=#{kind} AND source_key=#{source}")
    String sourceId(
            @Param("tenant") String tenant,
            @Param("kind") String kind,
            @Param("source") String source);

    @Select(
            "SELECT id,tenant_id AS tenantId,kind,source_key AS sourceKey,owner_team_id AS ownerTeamId,availability,value_json AS valueJson,value_hash AS valueHash,revision,catalog_revision AS catalogRevision,updated_at AS updatedAt FROM orbit_reference_record WHERE tenant_id=#{tenant} AND id=#{id} FOR SHARE")
    ReferenceImportStore.RecordRow record(@Param("tenant") String tenant, @Param("id") String id);

    @Insert(
            "INSERT INTO orbit_reference_record(id,tenant_id,kind,source_key,owner_team_id,availability,value_json,value_hash,revision,catalog_revision,updated_at) VALUES(#{id},#{tenantId},#{kind},#{sourceKey},#{ownerTeamId},#{availability},#{valueJson},#{valueHash},#{revision},#{catalogRevision},#{updatedAt})")
    int insertRecord(ReferenceImportStore.RecordRow row);

    @Update(
            "UPDATE orbit_reference_record SET owner_team_id=#{ownerTeamId},availability=#{availability},value_json=#{valueJson},value_hash=#{valueHash},revision=#{revision},catalog_revision=#{catalogRevision},updated_at=#{updatedAt} WHERE tenant_id=#{tenantId} AND id=#{id} AND kind=#{kind} AND source_key=#{sourceKey} AND revision=#{revision}-1")
    int updateRecord(ReferenceImportStore.RecordRow row);

    @Delete(
            "DELETE FROM orbit_reference_product_agent WHERE tenant_id=#{tenant} AND product_id=#{product}")
    int clearAgents(@Param("tenant") String tenant, @Param("product") String product);

    @Insert(
            "INSERT INTO orbit_reference_product_agent(tenant_id,product_id,agent_id) VALUES(#{tenant},#{product},#{agent})")
    int addAgent(
            @Param("tenant") String tenant,
            @Param("product") String product,
            @Param("agent") String agent);

    @Select("SELECT user_id FROM orbit_business_user WHERE tenant_id=#{tenant} AND id=#{subject}")
    Long userId(@Param("tenant") String tenant, @Param("subject") String subject);

    @Insert(
            "INSERT INTO orbit_reference_import(id,tenant_id,actor_id,revision,state,base_catalog_revision,body_json,body_hash,issues_json,created_count,updated_count,expires_at,created_at) VALUES(#{id},#{tenantId},#{actorId},#{revision},#{state},#{baseCatalogRevision},#{bodyJson},#{bodyHash},#{issuesJson},#{createdCount},#{updatedCount},#{expiresAt},#{createdAt})")
    int insertImport(ReferenceImportStore.ImportRow row);

    @Select(
            "SELECT id,tenant_id AS tenantId,actor_id AS actorId,revision,state,base_catalog_revision AS baseCatalogRevision,body_json AS bodyJson,body_hash AS bodyHash,issues_json AS issuesJson,created_count AS createdCount,updated_count AS updatedCount,expires_at AS expiresAt,created_at AS createdAt FROM orbit_reference_import WHERE tenant_id=#{tenant} AND id=#{id} FOR UPDATE")
    ReferenceImportStore.ImportRow lockImport(
            @Param("tenant") String tenant, @Param("id") String id);

    @Update(
            "UPDATE orbit_reference_import SET state='COMMITTED',revision=revision+1 WHERE tenant_id=#{tenant} AND id=#{id} AND revision=#{revision} AND state='VALIDATED'")
    int commit(
            @Param("tenant") String tenant,
            @Param("id") String id,
            @Param("revision") long revision);

    @Insert(
            "INSERT INTO orbit_reference_idempotency(tenant_id,actor_id,idem_key,request_hash) VALUES(#{tenant},#{actor},#{key},#{hash}) ON DUPLICATE KEY UPDATE idem_key=idem_key")
    int reserve(
            @Param("tenant") String tenant,
            @Param("actor") long actor,
            @Param("key") String key,
            @Param("hash") String hash);

    @Select(
            "SELECT request_hash AS requestHash,import_id AS importId,response_json AS responseJson FROM orbit_reference_idempotency WHERE tenant_id=#{tenant} AND actor_id=#{actor} AND idem_key=#{key} FOR UPDATE")
    ReferenceImportStore.Replay replay(
            @Param("tenant") String tenant, @Param("actor") long actor, @Param("key") String key);

    @Update(
            "UPDATE orbit_reference_idempotency SET import_id=#{id},response_json=#{body} WHERE tenant_id=#{tenant} AND actor_id=#{actor} AND idem_key=#{key}")
    int finish(
            @Param("tenant") String tenant,
            @Param("actor") long actor,
            @Param("key") String key,
            @Param("id") String id,
            @Param("body") String body);

    @Insert(
            "INSERT INTO orbit_reference_event(id,tenant_id,import_id,actor_id,actor_subject_id,request_id,action_code,source,reason,before_catalog_revision,after_catalog_revision,changes_json,created_at) VALUES(#{event},#{tenant},#{id},#{actor},#{subject},#{request},'REFERENCE_IMPORT_COMMITTED',#{source},#{reason},#{before},#{after},#{changes},#{now})")
    int event(
            @Param("event") String event,
            @Param("tenant") String tenant,
            @Param("id") String id,
            @Param("actor") long actor,
            @Param("subject") String subject,
            @Param("request") String request,
            @Param("source") String source,
            @Param("reason") String reason,
            @Param("before") long before,
            @Param("after") long after,
            @Param("changes") String changes,
            @Param("now") Instant now);

    @Insert(
            "INSERT INTO orbit_reference_outbox(event_id,tenant_id,import_id,catalog_revision,created_at) VALUES(#{event},#{tenant},#{id},#{version},#{now})")
    int outbox(
            @Param("event") String event,
            @Param("tenant") String tenant,
            @Param("id") String id,
            @Param("version") long version,
            @Param("now") Instant now);
}
