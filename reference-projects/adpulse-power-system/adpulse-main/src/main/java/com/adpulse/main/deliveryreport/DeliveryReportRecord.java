package com.adpulse.main.deliveryreport;

import java.time.LocalDate;
import lombok.Data;

/** 日报持久化记录；不保存平台消耗快照。 */
@Data
public class DeliveryReportRecord {
    private String reporterName;
    private String departmentName;
    private Long id;
    private LocalDate reportDate;
    private Long reporterId;
    private String reporterEnglishName;
    private Long projectId;
    private String projectName;
    private Long agencyLineId;
    private String agencyLineName;
    private String platform;
    private String metricsJson;
    private String accountIdsJson;
    private String campaignIdsJson;
}
