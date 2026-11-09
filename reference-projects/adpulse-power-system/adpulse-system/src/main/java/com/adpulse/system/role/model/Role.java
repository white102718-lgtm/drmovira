package com.adpulse.system.role.model;

import com.adpulse.system.common.model.AuditedEntity;
import lombok.Data;
import lombok.EqualsAndHashCode;

/** 系统角色持久化模型。 */
@Data
@EqualsAndHashCode(callSuper = true)
public class Role extends AuditedEntity {
    private String roleCode;
    private String roleName;
    private Integer status;
    private Integer sortOrder;
    private String remark;
}
