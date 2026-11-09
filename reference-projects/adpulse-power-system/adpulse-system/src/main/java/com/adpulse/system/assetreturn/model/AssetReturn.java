package com.adpulse.system.assetreturn.model;

import java.time.LocalDateTime;
import lombok.Data;

/** 资产回收单，保留申请与完成时的业务快照。 */
@Data
public class AssetReturn {
    private Long id;
    private String returnNo;
    private Long assetId;
    private Long applicationId;
    private String assetType;
    private String assetName;
    private String assetCode;
    private String projectId;
    private String projectName;
    private String channelId;
    private String channelName;
    private Long assigneeId;
    private String assigneeName;
    private String reason;
    private String status;
    private String outcome;
    private Long requestedById;
    private String requestedByName;
    private Long completedById;
    private String completedByName;
    private LocalDateTime completedAt;
    private LocalDateTime createdAt;
    private LocalDateTime updatedAt;
}
