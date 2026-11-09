package com.adpulse.main.project.model;

import java.math.BigDecimal;
import java.time.LocalDateTime;
import lombok.Data;

/** 项目持久化模型。 */
@Data
public class Project {
    private Long id;
    private String projectCode;
    private String walletCustomerRefId;
    private String projectName;
    private String projectType;
    private String responsibleTeam;
    private Long amUserId;
    private String amName;
    private Long deliveryLeaderId;
    private String deliveryLeaderName;
    private Long dataSpecialistId;
    private String dataSpecialist;
    private Boolean outsourced;
    private String priority;
    private BigDecimal serviceFeePercent;
    private String status;
    private String productInfo;
    private String customerDailyReportUrl;
    private String agencyLineUrl;
    private Long createdBy;
    private Long updatedBy;
    private LocalDateTime createdAt;
    private LocalDateTime updatedAt;
}
