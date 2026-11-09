package com.ruoyi.system.orbit.analysis;

import static com.ruoyi.system.orbit.analysis.AnalysisJobModels.*;

import com.ruoyi.system.orbit.config.ConfigurationModels.Row;
import java.time.*;
import org.apache.ibatis.annotations.Param;

/** 每个SQL操作强制显式租户；门闩、额度、任务和事件必须在同一事务使用。 */
public interface AnalysisJobMapper {
    Row configurationShared(@Param("tenant") String tenant, @Param("id") String id);

    void reserveGate(
            @Param("tenant") String tenant,
            @Param("rule") String rule,
            @Param("entity") String entity);

    Gate gate(
            @Param("tenant") String tenant,
            @Param("rule") String rule,
            @Param("entity") String entity);

    Job replay(@Param("tenant") String tenant, @Param("hash") String hash);

    void reserveQuota(@Param("job") Job job);

    int quota(@Param("job") Job job);

    int consumeQuota(@Param("job") Job job, @Param("maximum") int maximum);

    void insert(Job job);

    void supersedeEvents(@Param("job") Job job);

    void supersede(@Param("job") Job job);

    void queuedEvent(@Param("job") Job job);

    int advanceGate(@Param("job") Job job);
}
