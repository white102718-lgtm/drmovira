package com.adpulse.main.task.mapper;

import com.adpulse.main.task.dto.TaskViews;
import com.adpulse.main.task.model.TaskModels;
import java.time.LocalDateTime;
import java.util.List;
import org.apache.ibatis.annotations.Mapper;
import org.apache.ibatis.annotations.Param;

/** 任务、专业详情、交付和文件绑定持久化接口。 */
@Mapper
public interface TaskMapper {
    /** 按名称分页查询未删除代理线。 */
    List<TaskViews.AgencyLineOption> findDeliveryAgencyLines(
            @Param("keyword") String keyword,
            @Param("offset") int offset,
            @Param("limit") int limit);

    /** 仅查询本次提交引用的代理线，避免加载全部数据。 */
    List<TaskViews.AgencyLineOption> findDeliveryAgencyLinesByIds(@Param("ids") List<String> ids);

    /** 导入按名称精确匹配候选，歧义由业务层和导入行校验处理。 */
    List<TaskViews.AgencyLineOption> findDeliveryAgencyLinesByNames(
            @Param("names") List<String> names);

    /** 校验参与团队对应的部门仍启用且未删除。 */
    String findActiveDeliveryDepartment(@Param("id") Long id);

    TaskModels.Draft findDraft(@Param("id") Long id);

    TaskModels.Draft findDraftForUpdate(@Param("id") Long id);

    List<TaskModels.Draft> findDrafts(@Param("creatorId") Long creatorId);

    void insertDraft(TaskModels.Draft draft);

    int updateDraft(TaskModels.Draft draft);

    int deleteDraft(
            @Param("id") Long id,
            @Param("creatorId") Long creatorId,
            @Param("deletedAt") long deletedAt);

    void insertActivity(TaskModels.Activity activity);

    List<TaskModels.Activity> findActivities(
            @Param("userId") Long userId, @Param("limit") int limit);

    TaskModels.Task findTask(@Param("id") Long id);

    TaskModels.Task findTaskForUpdate(@Param("id") Long id);

    List<TaskModels.Task> findTasks(
            @Param("userId") Long userId,
            @Param("scope") String scope,
            @Param("taskType") String taskType,
            @Param("status") String status,
            @Param("keyword") String keyword,
            @Param("offset") int offset,
            @Param("limit") int limit);

    long countTasks(
            @Param("userId") Long userId,
            @Param("scope") String scope,
            @Param("taskType") String taskType,
            @Param("status") String status,
            @Param("keyword") String keyword);

    long countFailedTasks(
            @Param("userId") Long userId,
            @Param("scope") String scope,
            @Param("taskType") String taskType,
            @Param("status") String status,
            @Param("keyword") String keyword);

    long countFollowedTasks(@Param("userId") Long userId);

    long countAssignedTasks(@Param("userId") Long userId);

    long countActivities(@Param("userId") Long userId);

    long countDrafts(@Param("creatorId") Long creatorId);

    List<Long> findFollowedTaskIds(@Param("userId") Long userId);

    int countTaskFollow(@Param("taskId") Long taskId, @Param("userId") Long userId);

    void insertTaskFollow(@Param("taskId") Long taskId, @Param("userId") Long userId);

    int deleteTaskFollow(
            @Param("taskId") Long taskId,
            @Param("userId") Long userId,
            @Param("deletedAt") long deletedAt);

    String findProjectName(@Param("id") Long id);

    TaskModels.ProjectTaskOwners findProjectTaskOwners(@Param("id") Long id);

    List<TaskModels.UserSnapshot> findProjectAms(@Param("projectId") Long projectId);

    List<TaskModels.UserSnapshot> findDeliveryTaskAms(@Param("taskId") Long taskId);

    void insertDeliveryTaskAm(
            @Param("taskId") Long taskId,
            @Param("userId") Long userId,
            @Param("userName") String userName,
            @Param("sortOrder") int sortOrder,
            @Param("createdBy") Long createdBy);

    void deleteDeliveryTaskAms(@Param("taskId") Long taskId, @Param("deletedAt") long deletedAt);

    String findActiveUserName(@Param("id") Long id);

    /** 投手允许为停用人员，但必须仍是未删除的系统用户。 */
    String findUserName(@Param("id") Long id);

    int countOwnedFiles(@Param("ids") List<Long> ids, @Param("uploaderId") Long uploaderId);

    void insertTask(TaskModels.Task task);

    void insertDeliveryDetail(TaskModels.DeliveryDetail detail);

    void insertDeliveryPlatform(
            @Param("taskId") Long taskId,
            @Param("platform") String platform,
            @Param("sortOrder") int sortOrder);

    void insertAllocation(TaskModels.Allocation allocation);

    int deleteUnsubmittedAllocations(
            @Param("taskId") Long taskId, @Param("deletedAt") long deletedAt);

    void insertMaterialDetail(TaskModels.MaterialDetail detail);

    void insertMaterialRequirement(TaskModels.MaterialRequirement requirement);

    void insertMaterialSize(
            @Param("taskId") Long taskId,
            @Param("size") String size,
            @Param("sortOrder") int sortOrder);

    void insertReferenceLink(
            @Param("taskId") Long taskId,
            @Param("name") String name,
            @Param("url") String url,
            @Param("sortOrder") int sortOrder);

    void insertFileBinding(
            @Param("taskId") Long taskId,
            @Param("fileId") Long fileId,
            @Param("targetType") String targetType,
            @Param("targetId") Long targetId,
            @Param("usageType") String usageType,
            @Param("sortOrder") int sortOrder,
            @Param("boundBy") Long boundBy);

    TaskModels.DeliveryDetail findDeliveryDetail(@Param("taskId") Long taskId);

    List<String> findDeliveryPlatforms(@Param("taskId") Long taskId);

    List<TaskModels.Allocation> findAllocations(@Param("taskId") Long taskId);

    TaskModels.MaterialDetail findMaterialDetail(@Param("taskId") Long taskId);

    List<TaskModels.MaterialRequirement> findMaterialRequirements(@Param("taskId") Long taskId);

    int countEnabledDictionaryValues(
            @Param("dictCode") String dictCode, @Param("values") List<String> values);

    TaskModels.DepartmentSnapshot findUserDepartment(@Param("userId") Long userId);

    List<String> findMaterialSizes(@Param("taskId") Long taskId);

    List<TaskViews.ReferenceLink> findReferenceLinks(@Param("taskId") Long taskId);

    List<TaskViews.FileView> findTaskFiles(@Param("taskId") Long taskId);

    List<TaskModels.DeliverySubmission> findDeliverySubmissions(@Param("taskId") Long taskId);

    List<TaskViews.DeliveryObject> findDeliveryObjects(@Param("submissionId") Long submissionId);

    List<TaskModels.MaterialSubmission> findMaterialSubmissions(@Param("taskId") Long taskId);

    TaskModels.DeliverySubmission findDeliverySubmissionByRequestId(
            @Param("requestId") String requestId);

    TaskModels.DeliverySubmission findDeliverySubmission(
            @Param("id") Long id, @Param("taskId") Long taskId);

    TaskModels.MaterialSubmission findMaterialSubmissionByRequestId(
            @Param("requestId") String requestId);

    /** 按团队—投手执行项生成交付版本号，避免不同投手互相形成历史版本。 */
    int nextDeliveryVersion(@Param("allocationId") Long allocationId);

    TaskModels.Allocation findActiveAllocationForOperator(
            @Param("taskId") Long taskId, @Param("operatorId") Long operatorId);

    int countAllocationForOperator(
            @Param("taskId") Long taskId, @Param("operatorId") Long operatorId);

    boolean allAllocationsSubmitted(@Param("taskId") Long taskId);

    boolean allAllocationsCompleted(@Param("taskId") Long taskId);

    int nextMaterialVersion(@Param("taskId") Long taskId);

    void insertDeliverySubmission(TaskModels.DeliverySubmission submission);

    void insertDeliveryObject(
            @Param("submissionId") Long submissionId,
            @Param("objectType") String objectType,
            @Param("objectId") String objectId,
            @Param("objectName") String objectName,
            @Param("sortOrder") int sortOrder);

    void insertMaterialSubmission(TaskModels.MaterialSubmission submission);

    int confirmTask(
            @Param("id") Long id,
            @Param("ownerId") Long ownerId,
            @Param("version") int version,
            @Param("now") LocalDateTime now);

    int assignTask(
            @Param("id") Long id,
            @Param("creatorId") Long creatorId,
            @Param("ownerId") Long ownerId,
            @Param("ownerName") String ownerName,
            @Param("assignerId") Long assignerId,
            @Param("assignerName") String assignerName,
            @Param("assignedAt") LocalDateTime assignedAt,
            @Param("version") int version);

    int markPendingAcceptance(
            @Param("id") Long id, @Param("ownerId") Long ownerId, @Param("version") int version);

    int startDeliveryAssignments(
            @Param("id") Long id,
            @Param("ownerId") Long ownerId,
            @Param("assignerId") Long assignerId,
            @Param("assignerName") String assignerName,
            @Param("version") int version,
            @Param("now") LocalDateTime now);

    int markAllocationSubmitted(
            @Param("id") Long id,
            @Param("operatorId") Long operatorId,
            @Param("now") LocalDateTime now);

    int acceptDeliveryAllocation(
            @Param("id") Long id, @Param("taskId") Long taskId, @Param("now") LocalDateTime now);

    int rejectDeliveryAllocation(@Param("id") Long id, @Param("taskId") Long taskId);

    int completeTaskByDeliveryLeader(
            @Param("id") Long id,
            @Param("ownerId") Long ownerId,
            @Param("version") int version,
            @Param("now") LocalDateTime now);

    int reopenTaskByDeliveryLeader(
            @Param("id") Long id, @Param("ownerId") Long ownerId, @Param("version") int version);

    int acceptTask(
            @Param("id") Long id,
            @Param("creatorId") Long creatorId,
            @Param("version") int version,
            @Param("now") LocalDateTime now);

    int rejectTask(
            @Param("id") Long id,
            @Param("creatorId") Long creatorId,
            @Param("version") int version);

    int withdrawTask(
            @Param("id") Long id,
            @Param("creatorId") Long creatorId,
            @Param("version") int version,
            @Param("reason") String reason,
            @Param("now") LocalDateTime now);

    int declineTask(
            @Param("id") Long id,
            @Param("ownerId") Long ownerId,
            @Param("version") int version,
            @Param("reason") String reason,
            @Param("now") LocalDateTime now);

    int resubmitTask(
            @Param("id") Long id,
            @Param("creatorId") Long creatorId,
            @Param("version") int version,
            @Param("now") LocalDateTime now);

    int updateDeliveryTaskForResubmit(
            @Param("id") Long id,
            @Param("creatorId") Long creatorId,
            @Param("projectId") Long projectId,
            @Param("title") String title,
            @Param("description") String description,
            @Param("ownerId") Long ownerId,
            @Param("ownerName") String ownerName,
            @Param("priority") String priority,
            @Param("dueAt") LocalDateTime dueAt,
            @Param("version") int version,
            @Param("now") LocalDateTime now);

    int updateDeliveryDetailForResubmit(TaskModels.DeliveryDetail detail);

    int deleteDeliveryPlatforms(@Param("taskId") Long taskId, @Param("deletedAt") long deletedAt);

    int deleteAllocations(@Param("taskId") Long taskId, @Param("deletedAt") long deletedAt);

    int deleteTaskFiles(@Param("taskId") Long taskId, @Param("deletedAt") long deletedAt);

    int reviewDeliverySubmission(
            @Param("id") Long id,
            @Param("taskId") Long taskId,
            @Param("result") String result,
            @Param("reviewerId") Long reviewerId,
            @Param("reviewerName") String reviewerName,
            @Param("comment") String comment,
            @Param("now") LocalDateTime now);

    int reviewMaterialSubmission(
            @Param("id") Long id,
            @Param("taskId") Long taskId,
            @Param("result") String result,
            @Param("reviewerId") Long reviewerId,
            @Param("reviewerName") String reviewerName,
            @Param("comment") String comment,
            @Param("libraryStatus") String libraryStatus,
            @Param("now") LocalDateTime now);
}
