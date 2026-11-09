package com.adpulse.system.user.model;

import com.adpulse.system.common.model.AuditedEntity;
import lombok.Data;
import lombok.EqualsAndHashCode;

/** 通用或用户专属IP访问规则。 */
@Data
@EqualsAndHashCode(callSuper = true)
public class IpRule extends AuditedEntity {
    private Integer scopeType;
    private Long userId;
    private String ipCidr;
    private String ruleName;
    private Integer status;
    private String remark;
}
