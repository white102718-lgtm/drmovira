package com.adpulse.system.common.model;

import java.time.LocalDateTime;
import lombok.Data;

/** 业务实体通用审计字段。 */
@Data
public abstract class AuditedEntity {
    private Long id;
    private Long createdBy;
    private Long updatedBy;
    private LocalDateTime createdAt;
    private LocalDateTime updatedAt;
    private Long deletedAt;
}
