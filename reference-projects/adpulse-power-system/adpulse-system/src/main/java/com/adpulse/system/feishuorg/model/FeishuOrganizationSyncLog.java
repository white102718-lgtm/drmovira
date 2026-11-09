package com.adpulse.system.feishuorg.model;

import com.adpulse.system.feishuorg.dto.FeishuOrganizationViews.SyncResult;
import java.time.LocalDateTime;
import lombok.Data;

/** 飞书组织同步执行日志持久化模型。 */
@Data
public class FeishuOrganizationSyncLog {
    private Long id;
    private String triggerType;
    private String status;
    private Long startedBy;
    private String errorMessage;
    private SyncResult result;
    private String snapshotHash;
    private String appHash;
    private boolean acceptMissing;
    private int attempts;
    private LocalDateTime startedAt;
    private LocalDateTime availableAt;
    private LocalDateTime leaseUntil;
}
