package com.adpulse.system.asset.mapper;

import com.adpulse.system.asset.model.ApprovalConfig;
import com.adpulse.system.asset.model.AssetApplication;
import com.adpulse.system.asset.model.AssetApplicationComment;
import com.adpulse.system.asset.model.AssetImportLog;
import com.adpulse.system.asset.model.ChannelReference;
import com.adpulse.system.asset.model.MediaAsset;
import com.adpulse.system.asset.model.SiteNotification;
import java.util.List;
import org.apache.ibatis.annotations.Mapper;
import org.apache.ibatis.annotations.Param;

/** 资产、申请和审批配置持久化接口。 */
@Mapper
public interface AssetMapper {
    List<MediaAsset> findAssets(
            @Param("assetType") String assetType,
            @Param("assigneeId") Long assigneeId,
            @Param("channelId") String channelId);

    MediaAsset findAsset(@Param("id") Long id);

    MediaAsset findAssetByTypeAndCode(
            @Param("assetType") String assetType, @Param("assetCode") String assetCode);

    List<MediaAsset> findAssetsByTypeAndCodes(
            @Param("assetType") String assetType, @Param("assetCodes") List<String> assetCodes);

    List<MediaAsset> findAssetsByTypeAndName(
            @Param("assetType") String assetType, @Param("assetName") String assetName);

    int insertAsset(MediaAsset asset);

    int insertImportLog(AssetImportLog importLog);

    List<AssetImportLog> findImportLogsByOperatorId(
            @Param("operatorId") Long operatorId,
            @Param("offset") long offset,
            @Param("pageSize") int pageSize);

    long countImportLogsByOperatorId(@Param("operatorId") Long operatorId);

    AssetImportLog findImportLogByIdAndOperatorId(
            @Param("id") Long id, @Param("operatorId") Long operatorId);

    int updateAsset(MediaAsset asset);

    int softDeleteAsset(
            @Param("id") Long id,
            @Param("deletedAt") long deletedAt,
            @Param("operatorId") Long operatorId);

    List<ApprovalConfig> findConfigs();

    ApprovalConfig findConfig(@Param("assetType") String assetType);

    int countActiveUser(@Param("userId") Long userId);

    String findActiveUserName(@Param("userId") Long userId);

    List<Long> findActiveUserIdsByName(@Param("name") String name);

    int countActiveProject(
            @Param("projectId") String projectId, @Param("projectName") String projectName);

    List<Long> findActiveProjectIdsByName(@Param("name") String name);

    List<Long> findActiveDepartmentIdsByName(@Param("name") String name);

    String findActiveDepartmentName(@Param("id") Long id);

    int deactivatePixelUsageUsers(
            @Param("assetId") Long assetId,
            @Param("deletedAt") long deletedAt,
            @Param("operatorId") Long operatorId);

    int upsertPixelUsageUser(
            @Param("assetId") Long assetId,
            @Param("userId") Long userId,
            @Param("userName") String userName,
            @Param("operatorId") Long operatorId);

    /** 在人员离职前，按仍有效的共享关系重建渠道账户使用人；没有其他使用人时恢复可分配。 */
    int refreshChannelAccountUsageForDepartingUser(
            @Param("userId") Long userId, @Param("operatorId") Long operatorId);

    /** 软删除离职人员的广告账户共享使用关系，保留历史审计记录。 */
    int deactivateChannelAccountAssignmentsForUser(
            @Param("userId") Long userId,
            @Param("deletedAt") long deletedAt,
            @Param("operatorId") Long operatorId);

    /** 离职解除关系后，将已无使用人的广告账户恢复为可用库存。 */
    int releaseUnassignedAdAccountAssets(@Param("operatorId") Long operatorId);

    /** 软删除离职人员的像素共享使用关系，保留历史审计记录。 */
    int deactivatePixelUsageAssignmentsForUser(
            @Param("userId") Long userId,
            @Param("deletedAt") long deletedAt,
            @Param("operatorId") Long operatorId);

    /** 结项前停用项目像素遗留的使用人关联，保留审计历史。 */
    int deactivatePixelUsageAssignmentsForProject(
            @Param("projectId") String projectId,
            @Param("deletedAt") long deletedAt,
            @Param("operatorId") Long operatorId);

    /** 结项后释放该项目下所有已分配像素，并清空项目及使用快照。 */
    int releasePixelsForProject(
            @Param("projectId") String projectId, @Param("operatorId") Long operatorId);

    List<MediaAsset> findAssignedPixelsByProject(@Param("projectId") String projectId);

    /** 释放直接分配给离职人员的资产；仍存在其他共享使用人的资产保持已分配状态。 */
    int releaseAssetsAssignedToUser(
            @Param("userId") Long userId, @Param("operatorId") Long operatorId);

    int upsertConfig(@Param("config") ApprovalConfig config, @Param("operatorId") Long operatorId);

    int softDeleteConfig(
            @Param("id") Long id,
            @Param("deletedAt") long deletedAt,
            @Param("operatorId") Long operatorId);

    int insertApplication(
            @Param("application") AssetApplication application,
            @Param("operatorId") Long operatorId);

    AssetApplication findApplication(@Param("id") Long id);

    List<AssetApplication> findApplications(
            @Param("requesterId") Long requesterId, @Param("approverId") Long approverId);

    /** 按主键批量读取申请，供仅返回摘要的列表联表展示使用。 */
    List<AssetApplication> findApplicationsByIds(@Param("ids") List<Long> ids);

    List<MediaAsset> lockAvailableAssets(
            @Param("assetType") String assetType, @Param("quantity") int quantity);

    int assignAsset(
            @Param("id") Long id,
            @Param("applicationId") Long applicationId,
            @Param("assigneeId") Long assigneeId,
            @Param("assigneeName") String assigneeName,
            @Param("operatorId") Long operatorId);

    int decideApplication(
            @Param("id") Long id,
            @Param("status") String status,
            @Param("remark") String remark,
            @Param("operatorId") Long operatorId);

    int insertApprovalLog(
            @Param("applicationId") Long applicationId,
            @Param("action") String action,
            @Param("actorId") Long actorId,
            @Param("actorName") String actorName,
            @Param("remark") String remark);

    List<AssetApplicationComment> findApplicationComments(
            @Param("applicationId") Long applicationId);

    AssetApplicationComment findApplicationComment(@Param("id") Long id);

    int insertApplicationComment(AssetApplicationComment comment);

    List<SiteNotification> findNotifications(
            @Param("userId") Long userId,
            @Param("offset") int offset,
            @Param("pageSize") int pageSize);

    long countNotifications(@Param("userId") Long userId);

    boolean hasUnreadNotification(@Param("userId") Long userId);

    int markNotificationRead(@Param("id") Long id, @Param("userId") Long userId);

    int markAllNotificationsRead(@Param("userId") Long userId);

    /** 按名称查询渠道管理中可用于资产归属的正常渠道，保留重复结果供业务层拒绝歧义数据。 */
    /** 按稳定标识查询可用于资产归属的正常渠道。 */
    ChannelReference findActiveChannelById(@Param("id") Long id);

    List<ChannelReference> findActiveChannelsByName(@Param("name") String name);
}
