package com.adpulse.system.department.model;

import com.adpulse.system.common.model.AuditedEntity;
import java.util.ArrayList;
import java.util.List;
import lombok.Data;
import lombok.EqualsAndHashCode;

/** 部门树节点持久化模型。 */
@Data
@EqualsAndHashCode(callSuper = true)
public class Department extends AuditedEntity {
    private Long parentId;
    private String deptCode;
    private String deptName;
    private String path;
    private Integer level;
    private Integer sortOrder;
    private Long leaderUserId;
    private Integer status;
    private String remark;
    private String sourceType;
    private String tenantKey;
    private String externalId;
    private java.time.LocalDateTime lastSyncedAt;
    private List<Department> children = new ArrayList<>();
}
