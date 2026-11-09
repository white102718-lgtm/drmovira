package com.adpulse.system.asset.dto;

import com.adpulse.system.asset.model.MediaAsset;
import java.math.BigDecimal;
import java.time.LocalDateTime;
import java.util.List;

/** 资产流程查询接口的响应契约。 */
public final class AssetViews {
    private AssetViews() {}

    /** 审批配置分组视图；ID 使用字符串避免前端大整数精度丢失。 */
    /** 审批流程评论视图；评论身份由服务端根据流程参与关系生成。 */
    public record ApprovalCommentView(
            String id, String actor, String actorRole, LocalDateTime at, String content) {}

    /** 广告账户列表补充展示用的申请摘要；不携带审批轨迹等详情字段。 */
    public record ApplicationSummary(String id, String status, String requesterName) {}

    /** 审批转交候选人；候选范围由服务端按当前办理人的主部门限定。 */
    public record ApprovalTransferCandidate(
            String id, String name, String departmentId, String departmentName) {}

    /** 顶部导航红点所需的轻量未读状态。 */
    public record NotificationUnreadStatus(boolean hasUnread) {}

    /** 站内通知列表项；ID 使用字符串避免前端大整数精度丢失。 */
    public record NotificationView(
            String id,
            String title,
            String message,
            String targetPath,
            String businessType,
            String businessId,
            boolean isRead,
            LocalDateTime createdAt) {}

    /** 站内通知分页结果，供前端滚动加载。 */
    public record NotificationPage(
            List<NotificationView> items, long total, int page, int pageSize, boolean hasMore) {}

    /** 资产管理列表的服务端筛选分页结果。 */
    public record AssetPage(List<MediaAsset> items, long total, int page, int pageSize) {}

    /** 审批中心卡片列表所需的轻量摘要；完整表单和审批轨迹由详情接口返回。 */
    public record ApprovalListItem(
            String id,
            String applicationNo,
            String applicationDefinitionId,
            String assetType,
            String configCategory,
            String title,
            int quantity,
            String reason,
            String status,
            String requesterId,
            String requesterName,
            String approverId,
            String approverName,
            String departmentId,
            String departmentName,
            String projectName,
            List<ApprovalCcUser> ccUsers,
            LocalDateTime createdAt,
            LocalDateTime updatedAt) {}

    /** 审批抄送人读模型；历史无效 ID 仍保留稳定标识，避免页面把抄送配置静默丢失。 */
    public record ApprovalCcUser(String id, String displayName, boolean active, boolean resolved) {}

    /** 审批中心服务端分页结果。 */
    public record ApprovalPage(
            List<ApprovalListItem> items, long total, int page, int pageSize, boolean hasMore) {}

    /** 审批中心筛选选项，值始终按字符串返回以保护大整数 ID。 */
    public record ApprovalFilterOption(String value, String label) {}

    /** 左侧审批队列的未筛选总数。 */
    public record ApprovalQueueCounts(
            long pending, long handling, long processed, long copied, long initiated) {}

    /** 审批中心初始化所需的轻量统计和筛选元数据。 */
    public record ApprovalMetadata(
            ApprovalQueueCounts queueCounts,
            List<ApprovalFilterOption> departments,
            List<ApprovalFilterOption> requesters) {}

    /** 生命周期详情中的非敏感资产身份摘要。 */
    public record LifecycleAsset(
            String id,
            String assetType,
            String assetName,
            String assetCode,
            String status,
            String currentUserName,
            String projectName,
            String teamName) {}

    /** 同一使用人连续占用资产的区间。 */
    public record LifecycleUsagePeriod(
            String userId,
            String userName,
            LocalDateTime startedAt,
            LocalDateTime endedAt,
            String status,
            String applicationId,
            String projectName,
            String teamName) {}

    /** 生命周期时间线的脱敏事件。 */
    public record LifecycleEvent(
            String id,
            String eventType,
            String status,
            String actorName,
            String description,
            String applicationId,
            String projectName,
            String teamName,
            LocalDateTime occurredAt,
            String updateSource,
            List<LifecycleFieldChange> changes) {}

    /** 选项值在更新当时的 ID 与名称快照。 */
    public record LifecycleValueReference(String id, String name) {}

    /** 资料更新字段值；敏感字段只返回设置状态。 */
    public record LifecycleChangeValue(
            String display, List<LifecycleValueReference> references, boolean redacted) {}

    /** 一次资料更新中的单字段实际差异。 */
    public record LifecycleFieldChange(
            String fieldKey,
            String fieldLabel,
            LifecycleChangeValue before,
            LifecycleChangeValue after) {}

    /** 普通库存资产生命周期详情。 */
    public record AssetLifecycleDetail(
            LifecycleAsset asset,
            List<LifecycleUsagePeriod> usagePeriods,
            List<LifecycleEvent> events) {}

    /** 电子表格原子保存结果。 */
    public record AssetSpreadsheetSaveResult(
            int createdCount, int updatedCount, List<MediaAsset> items) {}

    /** 广告账户关联申请中的可追溯办理动作。 */
    public record AccountLifecycleAction(
            String id,
            String action,
            String actorName,
            String nodeName,
            String remark,
            LocalDateTime createdAt) {}

    /** 申请提交时的只读字段快照；仅包含允许展示的格式化值。 */
    public record AccountLifecycleFormField(
            String key, String label, String value, boolean fullWidth) {}

    /** 广告账户关联申请的生命周期摘要；不暴露完整表单 JSON 或审批配置。 */
    public record AccountLifecycleApplication(
            String applicationId,
            String applicationCode,
            String title,
            String status,
            String requesterName,
            BigDecimal amount,
            String currency,
            LocalDateTime createdAt,
            LocalDateTime decidedAt,
            List<AccountLifecycleFormField> formFields,
            List<AccountLifecycleAction> actions) {}
}
