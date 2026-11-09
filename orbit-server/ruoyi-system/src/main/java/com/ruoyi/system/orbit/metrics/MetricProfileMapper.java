package com.ruoyi.system.orbit.metrics;

import org.apache.ibatis.annotations.Param;

/** 版本键按tenant/profile/version隔离，同版本不可覆盖，预占失败与审计同事务回滚。 */
public interface MetricProfileMapper {
    void reserve(MetricProfileRegistry.Row row);

    MetricProfileRegistry.Row lock(
            @Param("tenant") String tenant,
            @Param("id") String id,
            @Param("version") String version);

    void finish(MetricProfileRegistry.Row row);

    void audit(
            @Param("row") MetricProfileRegistry.Row row,
            @Param("actor") long actor,
            @Param("reason") String reason);
}
