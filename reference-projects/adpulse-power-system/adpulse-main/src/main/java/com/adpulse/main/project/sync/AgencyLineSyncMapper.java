package com.adpulse.main.project.sync;

import com.adpulse.main.project.model.Project;
import com.adpulse.main.project.model.ProjectUserReference;
import com.adpulse.main.project.sync.AgencyLineSyncModels.Batch;
import com.adpulse.main.project.sync.AgencyLineSyncModels.Failure;
import java.util.List;
import org.apache.ibatis.annotations.Mapper;
import org.apache.ibatis.annotations.Param;

/** 项目代理线 Google Sheet 同步持久化接口。 */
@Mapper
public interface AgencyLineSyncMapper {
    List<Project> findProjectsForAutomaticSync();

    List<ProjectUserReference> findActiveUsersByName(@Param("name") String name);

    int failRunningBatches(@Param("projectId") Long projectId);

    int insertBatch(Batch batch);

    int finishBatch(Batch batch);

    int insertFailure(Failure failure);

    Batch findBatch(
            @Param("projectId") Long projectId, @Param("batchId") Long batchId);

    List<Batch> findBatches(
            @Param("projectId") Long projectId,
            @Param("offset") int offset,
            @Param("pageSize") int pageSize);

    long countBatches(@Param("projectId") Long projectId);

    List<Failure> findFailures(
            @Param("batchId") Long batchId,
            @Param("offset") int offset,
            @Param("pageSize") int pageSize);

    long countFailures(@Param("batchId") Long batchId);
}
