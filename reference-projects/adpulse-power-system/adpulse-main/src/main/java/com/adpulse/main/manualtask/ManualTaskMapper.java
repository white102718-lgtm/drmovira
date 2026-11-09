package com.adpulse.main.manualtask;

import com.adpulse.main.adaccountasset.AdAccountAssetModels.AdAccountAsset;
import com.adpulse.main.adaccountasset.AdAccountAssetModels.AdAccountAssetAssignment;
import com.adpulse.main.manualtask.ManualTaskModels.Execution;
import com.adpulse.main.manualtask.ManualTaskModels.UserCandidate;
import java.util.List;
import org.apache.ibatis.annotations.Mapper;
import org.apache.ibatis.annotations.Param;

/** 手动任务执行记录及飞书使用人同步所需的持久化接口。 */
@Mapper
public interface ManualTaskMapper {
    int insertExecution(Execution execution);

    List<Execution> findExecutions(
            @Param("taskCode") String taskCode,
            @Param("excludedTaskCodes") List<String> excludedTaskCodes,
            @Param("offset") long offset,
            @Param("pageSize") int pageSize);

    long countExecutions(
            @Param("taskCode") String taskCode,
            @Param("excludedTaskCodes") List<String> excludedTaskCodes);

    int countActive(@Param("taskCode") String taskCode);

    Execution findExecution(@Param("id") Long id);

    List<Execution> findPending(
            @Param("taskCodes") List<String> taskCodes, @Param("limit") int limit);

    int claim(@Param("id") Long id);

    int appendLog(@Param("id") Long id, @Param("content") String content);

    int complete(@Param("id") Long id, @Param("status") String status);

    int failStale(
            @Param("id") Long id,
            @Param("before") java.time.LocalDateTime before,
            @Param("content") String content);

    List<Execution> findStaleRunning(@Param("before") java.time.LocalDateTime before);

    List<UserCandidate> findUsersByNames(@Param("names") List<String> names);

    AdAccountAsset lockAssetByAccountId(@Param("accountId") String accountId);

    List<AdAccountAssetAssignment> findActiveAssignments(@Param("assetId") Long assetId);

    int insertAssignment(AdAccountAssetAssignment assignment);

    int markAssetAssigned(@Param("assetId") Long assetId, @Param("updatedBy") Long updatedBy);
}
