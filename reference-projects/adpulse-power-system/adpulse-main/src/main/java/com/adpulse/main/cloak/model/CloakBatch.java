package com.adpulse.main.cloak.model;

import java.time.LocalDateTime;
import lombok.Data;

/** 斗篷批量提交持久化模型。 */
@Data
public class CloakBatch {
    private Long id;
    private String requestId;
    private String requestFingerprint;
    private Long projectId;
    private String projectName;
    private Integer status;
    private Integer totalCount;
    private Integer successCount;
    private String providerMessage;
    private String errorMessage;
    private Long requestedBy;
    private LocalDateTime startedAt;
    private LocalDateTime finishedAt;
    private LocalDateTime createdAt;
    private LocalDateTime updatedAt;
}
