package com.adpulse.main.cloak.model;

import java.time.LocalDateTime;
import lombok.Data;

/** 斗篷管理记录持久化模型。 */
@Data
public class CloakRecord {
    private Long id;
    private Long batchId;
    private Long providerCloakId;
    private Long projectId;
    private String projectName;
    private Long agencyLineId;
    private String agencyLineName;
    private String name;
    private String reallyUrl;
    private String virtualUrl;
    private String adUrl;
    private String genId;
    private String genDomain;
    private String promotionUrl;
    private Integer type;
    private String country;
    private String countryLabel;
    private Integer langStatus;
    private Integer pcStatus;
    private Integer vpnStatus;
    private String providerLinkId;
    private Integer status;
    private Integer sheetWritebackStatus;
    private String sheetWritebackMessage;
    private Integer sheetRowNumber;
    private LocalDateTime sheetWritebackAt;
    private Long createdBy;
    private Long updatedBy;
    private LocalDateTime createdAt;
    private LocalDateTime updatedAt;
}
