package com.adpulse.system.feishuorg.model;

import java.time.LocalDateTime;
import lombok.Data;

/** 单组织同步计划；调度时间以 UTC 保存，页面按北京时间展示。 */
@Data
public class FeishuOrganizationSchedule {
    private Long id;
    private boolean enabled;
    private int intervalMinutes;
    private String dailyTime;
    private int missingCountLimit;
    private int missingPercentLimit;
    private String verifiedAppHash;
    private LocalDateTime nextRunAt;
    private Long updatedBy;
}
