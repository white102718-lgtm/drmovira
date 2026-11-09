package com.adpulse.system.dailyreport.model;

import java.time.LocalDateTime;
import lombok.Data;

@Data
public class DailyReportRule {
    private Long id;
    private String ruleKey;
    private String name;
    private String configJson;
    private Boolean reminderEnabled;
    private Boolean status;
    private Long createdBy;
    private Long updatedBy;
    private LocalDateTime createdAt;
    private LocalDateTime updatedAt;
}
