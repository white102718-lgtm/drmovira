package com.adpulse.system.application.dto;

import com.adpulse.system.application.model.ApplicationDefinition;
import java.time.LocalDateTime;

/** 申请入口管理视图，同时返回关联审批配置的展示信息。 */
public record ApplicationDefinitionView(
        String id,
        String applicationCode,
        String applicationName,
        String applicationTypeId,
        String applicationTypeName,
        String description,
        String icon,
        String approvalConfigId,
        String approvalConfigName,
        String approvalAssetType,
        Boolean approvalConfigEnabled,
        String visibility,
        Boolean showInResourceApplication,
        Integer sortOrder,
        Integer status,
        LocalDateTime createdAt,
        LocalDateTime updatedAt) {

    /** 从申请入口及其审批配置摘要构造前端视图。 */
    public static ApplicationDefinitionView from(ApplicationDefinition definition) {
        return new ApplicationDefinitionView(
                definition.getId().toString(),
                definition.getApplicationCode(),
                definition.getApplicationName(),
                definition.getApplicationTypeId().toString(),
                definition.getApplicationTypeName(),
                definition.getDescription(),
                definition.getIcon(),
                definition.getApprovalConfigId() == null
                        ? null
                        : definition.getApprovalConfigId().toString(),
                definition.getApprovalConfigName(),
                definition.getApprovalAssetType(),
                definition.getApprovalConfigEnabled(),
                definition.getVisibility(),
                definition.getShowInResourceApplication(),
                definition.getSortOrder(),
                definition.getStatus(),
                definition.getCreatedAt(),
                definition.getUpdatedAt());
    }
}
