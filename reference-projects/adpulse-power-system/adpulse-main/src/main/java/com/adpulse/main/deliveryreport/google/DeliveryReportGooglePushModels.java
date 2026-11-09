package com.adpulse.main.deliveryreport.google;

import java.time.LocalDateTime;
import lombok.Data;

/** 投放日报Google模板和推送任务的持久化模型。 */
public final class DeliveryReportGooglePushModels {
    private DeliveryReportGooglePushModels() {}

    /** 一个项目唯一的Google日报写入模板。 */
    @Data
    public static class Template {
        private Long id;
        private Long projectId;
        private String projectName;
        private String templateName;
        private String spreadsheetId;
        private String spreadsheetName;
        private String sheetId;
        private String sheetTitle;
        private Integer headerRow;
        private String fieldMappings;
        private Integer enableFlag;
        private Long createdBy;
        private Long updatedBy;
        private LocalDateTime updatedAt;
    }

    /** 一次用户确认产生的可恢复推送批次。 */
    @Data
    public static class Batch {
        private Long id;
        private Integer status;
        private Integer totalCount;
        private Integer successCount;
        private Integer failedCount;
        private Long requestedBy;
        private String errorMessage;
        private LocalDateTime startedAt;
        private LocalDateTime finishedAt;
        private LocalDateTime createdAt;
    }

    /** 单条日报的目标位置和待写入值快照。 */
    @Data
    public static class Item {
        private Long id;
        private Long batchId;
        private Long reportId;
        private Long projectId;
        private Long templateId;
        private String spreadsheetId;
        private String sheetId;
        private String sheetTitle;
        private Integer headerRow;
        private String fieldValues;
        private String targetHeaders;
        private String uniqueKeyColumns;
        private String reportIdColumn;
        private Integer status;
        private Integer targetRow;
        private Integer attemptCount;
        private String errorMessage;
        private LocalDateTime startedAt;
        private LocalDateTime finishedAt;
    }
}
