package com.adpulse.system.asset.model;

import java.time.LocalDateTime;
import lombok.Data;

/** 资产申请及当前审批状态。 */
@Data
public class AssetApplication {
    private Long id;
    private String applicationNo;
    private String assetType;
    private String title;
    private Integer quantity;
    private String reason;
    private String status;
    private Long requesterId;
    private String requesterName;
    private Long approverId;
    private String approverName;
    private String decisionRemark;
    private String formData;
    private String nodesSnapshot;
    private LocalDateTime decidedAt;
    private LocalDateTime createdAt;
    private LocalDateTime updatedAt;
}
