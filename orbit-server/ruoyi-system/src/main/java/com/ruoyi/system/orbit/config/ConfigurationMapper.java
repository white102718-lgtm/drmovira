package com.ruoyi.system.orbit.config;

import com.ruoyi.system.orbit.config.ConfigurationModels.IdempotencyRow;
import com.ruoyi.system.orbit.config.ConfigurationModels.Principal;
import com.ruoyi.system.orbit.config.ConfigurationModels.Row;
import java.util.List;
import org.apache.ibatis.annotations.Param;

/** 所有配置查询和写入强制包含当前服务端租户，SQL位于Mapper XML。 */
public interface ConfigurationMapper {
    void reserveRequest(
            @Param("tenantId") String tenantId,
            @Param("actorId") Long actorId,
            @Param("requestKey") String requestKey,
            @Param("payloadHash") String payloadHash);

    IdempotencyRow requestForUpdate(
            @Param("tenantId") String tenantId,
            @Param("actorId") Long actorId,
            @Param("requestKey") String requestKey);

    void finishRequest(
            @Param("tenantId") String tenantId,
            @Param("actorId") Long actorId,
            @Param("requestKey") String requestKey,
            @Param("responseJson") String responseJson);

    Principal findPrincipal(@Param("userId") Long userId);

    List<Row> list(@Param("tenantId") String tenantId);

    Row find(@Param("tenantId") String tenantId, @Param("id") String id);

    /** 版本为配置内单调递增游标，读取多一条判断是否还有历史。 */
    List<ConfigurationModels.AuditRow> history(
            @Param("tenantId") String tenantId,
            @Param("configId") String configId,
            @Param("beforeRevision") long beforeRevision,
            @Param("limit") int limit);

    int insert(Row row);

    int update(@Param("row") Row row, @Param("expectedRevision") long expectedRevision);

    int recordVerification(
            @Param("tenantId") String tenantId,
            @Param("id") String id,
            @Param("revision") long revision,
            @Param("status") String status);

    void audit(ConfigurationModels.AuditWrite audit);
}
