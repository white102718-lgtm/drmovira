package com.adpulse.system.dailyreport.model;

import java.time.LocalDate;
import java.time.LocalDateTime;
import lombok.Data;

@Data
public class DailyReportSubmission {
    private Long id;
    private Long ruleId;
    private LocalDate reportDate;

    /** 用于保证同一填写周期内仅保留一条日报的稳定周期起点。 */
    private LocalDate periodKey;

    private String fieldValuesJson;
    private String attachmentsJson;
    private String ruleSnapshotJson;
    private Long submittedById;
    private String submittedByName;
    private LocalDateTime createdAt;
}
