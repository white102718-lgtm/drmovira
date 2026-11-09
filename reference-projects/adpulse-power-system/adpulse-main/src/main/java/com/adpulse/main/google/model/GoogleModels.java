package com.adpulse.main.google.model;

import java.math.BigDecimal;
import java.time.LocalDate;
import java.time.LocalDateTime;
import lombok.Data;

/** Google数据集成持久化模型。 */
public final class GoogleModels {
    private GoogleModels() {}

    /** Google OAuth账号持久化模型。 */
    @Data
    public static class Account {
        private Long id;
        private String googleSubject;
        private String email;
        private String picture;
        private String accessTokenCiphertext;
        private String refreshTokenCiphertext;
        private LocalDateTime tokenExpiresAt;
        private Integer authStatus;
        private LocalDateTime authorizedAt;
        private Long createdBy;
        private Long updatedBy;
    }

    /** Google Sheets映射持久化模型。 */
    @Data
    public static class Mapping {
        private Long id;
        private Long googleAccountId;
        private String name;
        private Integer reportType;
        private String spreadsheetId;
        private String spreadsheetName;
        private String spreadsheetModifiedTime;
        private String sheetNames;
        private String fieldMappings;
        private Integer syncDirection;
        private Integer conflictStrategy;
        private Integer dateRangeType;
        private String dateRangeConfig;
        private Integer syncFrequency;
        private String syncTime;
        private Integer enableFlag;
        private LocalDateTime lastSyncTime;
        private Long createdBy;
        private Long updatedBy;
    }

    /** Google Sheets同步结果持久化模型。 */
    @Data
    public static class SyncData {
        private Long id;
        private Long mappingId;
        private LocalDate startDate;
        private String taskName;
        private String subtaskName;
        private BigDecimal spendAmount;
        private BigDecimal returnAmount;
        private Long impressions;
        private Long clicks;
        private Long registrations;
        private Long purchases;
        private Long subscriptions;
        private String mediaPlacement;
        private LocalDateTime updatedAt;
    }

    /** 外部同步队列持久化模型。 */
    @Data
    public static class SyncJob {
        private Long id;
        private String businessId;
        private String requestPayload;
        private Integer status;
        private String errorMessage;
        private Long requestedBy;
        private LocalDateTime startedAt;
        private LocalDateTime finishedAt;
        private LocalDateTime createdAt;
    }
}
