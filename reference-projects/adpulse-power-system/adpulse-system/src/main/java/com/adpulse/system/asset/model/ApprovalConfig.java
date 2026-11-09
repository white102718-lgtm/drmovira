package com.adpulse.system.asset.model;

import java.time.LocalDateTime;
import lombok.Data;

/** 单一资产类型的审批人配置。 */
@Data
public class ApprovalConfig {
    private Long id;
    private String assetType;
    private Long approverId;
    private String approverName;
    private String ccUserIds;
    private LocalDateTime updatedAt;
}
