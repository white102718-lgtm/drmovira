package com.adpulse.system.asset.mapper;

import java.util.List;
import java.util.Map;
import org.apache.ibatis.annotations.Mapper;
import org.apache.ibatis.annotations.Param;

/** 动态资产审批流程持久化接口。 */
@Mapper
public interface DynamicAssetFlowMapper {
    int upsertApprovalConfig(@Param("config") Map<String, Object> config);

    int insertApplication(@Param("application") Map<String, Object> application);

    int insertApprovalLog(@Param("log") Map<String, Object> log);

    int updateApplication(@Param("update") Map<String, Object> update);

    Long lockApplication(@Param("id") Long id);

    List<Map<String, Object>> lockAssets(@Param("ids") List<Long> ids);

    int assignAsset(@Param("assignment") Map<String, Object> assignment);

    /** 像素只能从未分配库存领取，并写入申请表中确认的项目与使用团队快照。 */
    int assignPixelAsset(@Param("assignment") Map<String, Object> assignment);

    Map<String, Object> findConfig(@Param("assetType") String assetType);

    List<Map<String, Object>> findApplications(
            @Param("id") Long id,
            @Param("requesterId") Long requesterId,
            @Param("activeOnly") boolean activeOnly);

    List<Map<String, Object>> findAccountLifecycleApplications(
            @Param("accountId") String accountId);

    /** 查询指定广告账户关联申请的审批和办理轨迹。 */
    List<Map<String, Object>> findAccountLifecycleActions(@Param("accountId") String accountId);

    /** 查询当前用户已作出通过或驳回决定的审批单。 */
    List<Map<String, Object>> findProcessedApplications(@Param("actorId") long actorId);

    /** 按当前用户可见队列和筛选条件查询一页审批单。 */
    List<Map<String, Object>> findApprovalPage(@Param("query") Map<String, Object> query);

    /** 按稳定申请单 ID 查询当前用户有权查看的审批导出数据。 */
    List<Map<String, Object>> findVisibleApprovalExportRows(
            @Param("query") Map<String, Object> query);

    /** 按稳定用户 ID 批量查询抄送人；停用用户仍返回，软删除用户按历史无效 ID 处理。 */
    List<Map<String, Object>> findApprovalCcUsersByIds(@Param("ids") List<Long> ids);

    /** 统计当前审批队列在筛选后的记录数。 */
    long countApprovalPage(@Param("query") Map<String, Object> query);

    /** 查询当前用户全部可见审批单涉及的部门选项。 */
    List<Map<String, Object>> findApprovalDepartments(@Param("query") Map<String, Object> query);

    /** 查询当前用户全部可见审批单涉及的申请人选项。 */
    List<Map<String, Object>> findApprovalRequesters(@Param("query") Map<String, Object> query);

    List<Map<String, Object>> findConfigs(
            @Param("userId") Long userId, @Param("managementView") boolean managementView);

    /** 批量查询申请的审批轨迹，供列表接口避免逐单查询。 */
    List<Map<String, Object>> findApprovalLogsByApplicationIds(
            @Param("applicationIds") List<Long> applicationIds);

    /** 批量查询申请已分配的资产摘要，供列表接口避免逐单查询。 */
    List<Map<String, Object>> findAllocatedAssetsByApplicationIds(
            @Param("applicationIds") List<Long> applicationIds);

    /** 查询审批办理结果明确引用的图片文件，不提供任意文件读取入口。 */
    List<Map<String, Object>> findApprovalExportFiles(@Param("fileIds") List<Long> fileIds);

    /** 查询启用用户的有效主部门。 */
    Map<String, Object> findActivePrimaryDepartment(@Param("userId") long userId);

    /** 查询指定主部门内除当前办理人外的启用用户。 */
    List<Map<String, Object>> findActiveUsersByPrimaryDepartment(
            @Param("departmentId") long departmentId, @Param("excludedUserId") long excludedUserId);

    Map<String, Object> findChannelPaymentContext(@Param("channelId") Long channelId);

    Object sumYesterdayChannelSpend(@Param("channelId") Long channelId);

    Map<String, Object> summarizeOwnedFiles(
            @Param("fileIds") List<Long> fileIds, @Param("userId") Long userId);

    int countActiveUser(@Param("userId") Long userId);

    List<Map<String, Object>> findActiveUsers(@Param("ids") List<Long> ids);

    List<Map<String, Object>> findActiveRoles(@Param("ids") List<Long> ids);

    List<Long> findActiveRoleMemberIds(@Param("roleIds") List<Long> roleIds);

    /** 查询可用于审批配置的启用部门。 */
    List<Map<String, Object>> findActiveDepartments(@Param("ids") List<Long> ids);

    /** 按主部门精确查询直属启用成员，不包含下级部门成员。 */
    List<Long> findActiveDepartmentMemberIds(@Param("departmentIds") List<Long> departmentIds);

    List<String> findActiveAccountLabels(@Param("accountId") String accountId);

    List<Map<String, Object>> lockActiveChannelAccounts(
            @Param("selectedIds") List<String> selectedIds);

    /** 查询所选广告账户中已经分配给指定使用人的账户 ID。 */
    List<String> findAssignedChannelAccountIds(
            @Param("accountIds") List<String> accountIds, @Param("assigneeId") long assigneeId);

    int assignChannelAccounts(
            @Param("accountIds") List<String> accountIds,
            @Param("assigneeId") long assigneeId,
            @Param("assigneeName") String assigneeName,
            @Param("operatorId") long operatorId);

    /** 为广告账户写入可并存的申请分配关系，避免覆盖既有使用人。 */
    int insertChannelAccountAssignments(
            @Param("accountIds") List<String> accountIds,
            @Param("applicationId") long applicationId,
            @Param("assigneeId") long assigneeId,
            @Param("assigneeName") String assigneeName,
            @Param("operatorId") long operatorId);

    List<String> findActiveReferenceLabels(@Param("source") String source, @Param("id") Long id);
}
