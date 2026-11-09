package com.adpulse.system.application.model;

import com.adpulse.system.common.model.AuditedEntity;
import lombok.Data;
import lombok.EqualsAndHashCode;

/** 资源申请中心左侧展示的申请类型，负责归类申请入口。 */
@Data
@EqualsAndHashCode(callSuper = true)
public class ApplicationType extends AuditedEntity {
    private String typeName;
    private String description;
    private String icon;
    private Integer sortOrder;
    private Integer status;
}
