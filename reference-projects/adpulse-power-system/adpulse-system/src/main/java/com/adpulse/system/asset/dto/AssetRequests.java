package com.adpulse.system.asset.dto;

import jakarta.validation.Valid;
import jakarta.validation.constraints.Max;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotEmpty;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Size;
import java.util.List;
import java.util.Map;
import java.util.Set;

/** 资产流程写接口的请求契约。 */
public final class AssetRequests {
    private AssetRequests() {}

    /** 创建或修改资产。 */
    public record AssetSave(
            @NotBlank String assetType,
            @NotBlank String assetName,
            String assetCode,
            String projectId,
            String projectName,
            String channelId,
            String channelName,
            String secretData,
            String remark,
            String status,
            Long assigneeId,
            List<@Min(1) Long> assigneeIds,
            Long usageTeamId) {}

    /** 通用资产批量修改支持的非明细字段。 */
    public enum AssetBatchField {
        CHANNEL,
        INVENTORY_STATUS,
        PROJECT,
        REMARK,
        USAGE_TEAM,
        USAGE_USERS
    }

    /**
     * 通用资产批量字段覆盖请求。
     *
     * <p>明细字段以 Map 中存在的键作为修改白名单；空字符串表示清空非必填字段，未出现的键保持原值。
     */
    public record AssetBatchUpdate(
            @NotEmpty @Size(max = 100) List<@NotNull @Min(1) Long> assetIds,
            @NotNull Set<@NotNull AssetBatchField> changedFields,
            @NotNull @Size(max = 30) Map<@NotBlank @Size(max = 100) String, @Size(max = 500) String> detailUpdates,
            String channelId,
            String channelName,
            String projectId,
            String projectName,
            @Size(max = 300) String remark,
            @Size(max = 24) String status,
            @Min(1) Long assigneeId,
            @Size(max = 100) List<@Min(1) Long> assigneeIds,
            @Min(1) Long usageTeamId) {}

    /** 资产电子表格按主键批量读取；一次弹窗最多处理 1000 行。 */
    public record AssetBatchQuery(
            @NotEmpty @Size(max = 1000) List<@NotNull @Min(1) Long> assetIds) {}

    /** 电子表格粘贴时按资产类型和业务唯一标识精确匹配已有资产。 */
    public record AssetIdentifierBatchQuery(
            @NotBlank String assetType,
            @NotEmpty @Size(max = 1000) List<@NotBlank @Size(max = 500) String> identifiers) {}

    /** 电子表格暂存行。已有资产仅应用显式白名单中的变更；assetId 为空时按完整 values 新增。 */
    public record AssetSpreadsheetRow(
            @Min(1) Long assetId,
            @NotNull @Valid AssetSave values,
            @NotNull Set<@NotNull AssetBatchField> changedFields,
            @NotNull @Size(max = 30) Map<@NotBlank @Size(max = 100) String, @Size(max = 500) String> detailUpdates,
            @Size(max = 100) List<@Min(1) Long> assigneeIds,
            @Min(1) Long usageTeamId) {}

    /** 电子表格一次保存请求；服务端在同一事务内完成全部新增和修改。 */
    public record AssetSpreadsheetSave(
            @NotBlank String subtype,
            @NotEmpty @Size(max = 1000) List<@NotNull @Valid AssetSpreadsheetRow> rows) {}

    /** 已分配广告账户在台账抽屉中直接指定的实际使用人。 */
    public record UsageUserSave(@NotNull Long usageUserId) {}

    /** 创建资源申请。 */
    public record ApplicationCreate(
            @NotBlank String assetType,
            @NotBlank String title,
            @NotNull @Min(1) @Max(100) Integer quantity,
            @NotBlank String reason) {}

    /** 保存审批人配置。 */
    public record ApprovalConfigSave(
            @NotBlank String assetType,
            @NotNull Long approverId,
            @NotBlank String approverName,
            String ccUserIds) {}

    /** 审批决定。 */
    public record Decision(String remark) {}

    /** 将当前审批或办理节点转交给负责人主部门内的其他同事。 */
    public record ApprovalTransfer(
            @NotNull @Min(1) Long recipientId, @NotBlank @Size(max = 300) String remark) {}

    /** 一次性处理多条资产申请的审批决定。 */
    public record BatchDecision(
            @NotEmpty @Size(max = 100) List<@NotNull Long> ids,
            @NotNull DecisionAction action,
            @Size(max = 300) String remark) {}

    /** 一次导出多张当前用户可见的审批单。 */
    public record ApprovalExport(@NotEmpty @Size(max = 100) List<@NotNull @Min(1) Long> ids) {}

    /** 批量审批支持的决定类型。 */
    public enum DecisionAction {
        APPROVE,
        REJECT
    }

    /** 发布审批流程评论。 */
    public record ApprovalCommentCreate(@NotBlank @Size(max = 500) String content) {}

    /** 资产管理列表的服务端筛选条件。明细字段保存在加密 JSON 中，字段键和值因此使用受限 Map 传递， 由服务端解密后统一匹配并分页，避免浏览器读取完整资产清单。 */
    public record AssetSearch(
            String assetType,
            String subtype,
            @Size(max = 500) String keyword,
            @Size(max = 30) Map<@Size(max = 100) String, @Size(max = 500) String> filters,
            @Size(max = 30) Map<
                                    @Size(max = 100) String,
                                    @NotNull @Size(max = 100) List<
                                            @NotNull @Size(max = 500) String>>
                            filterValues,
            @Size(max = 30) Map<@Size(max = 100) String, @Size(max = 20) String> filterControls,
            @Min(1) Integer page,
            @Min(1) @Max(1000) Integer pageSize,
            boolean mine) {}
}
