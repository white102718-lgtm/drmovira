package com.adpulse.system.asset.model;

import java.time.LocalDateTime;
import lombok.Data;

/** 普通库存资产的脱敏生命周期事件。 */
@Data
public class MediaAssetLifecycleEvent {
    private Long id;
    private Long assetId;
    private String eventType;
    private String status;
    private Long applicationId;
    private Long actorId;
    private String actorName;
    private Long usageUserId;
    private String usageUserName;
    private String projectName;
    private String teamName;
    private String description;
    private String updateSource;
    private String changesJson;
    private LocalDateTime occurredAt;
}
