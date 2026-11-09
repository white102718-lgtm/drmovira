package com.adpulse.system.application.model;

import com.adpulse.system.common.model.AuditedEntity;
import lombok.Data;
import lombok.EqualsAndHashCode;

/** 申请入口定义；申请与审批配置为多对一逻辑关联，表单仍由审批配置维护。 */
@Data
@EqualsAndHashCode(callSuper = true)
public class ApplicationDefinition extends AuditedEntity {
    private String applicationCode;
    private String applicationName;
    private Long applicationTypeId;
    private String applicationTypeName;
    private String description;
    private String icon;
    private Long approvalConfigId;
    private String visibility;
    private Boolean showInResourceApplication;
    private Integer sortOrder;
    private Integer status;
    private String approvalConfigName;
    private String approvalAssetType;
    private Boolean approvalConfigEnabled;
}
