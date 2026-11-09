package com.adpulse.main.project.sync;

import java.time.LocalDateTime;
import lombok.Data;

/** 项目代理线 Google Sheet 同步持久化模型。 */
public final class AgencyLineSyncModels {
    private AgencyLineSyncModels() {}

    /** 同步批次及其汇总结果。 */
    @Data
    public static class Batch {
        private Long id;
        private Long projectId;
        private String triggerType;
        private String status;
        private String linkSnapshot;
        private String spreadsheetId;
        private String sheetGid;
        private String sheetTitle;
        private int totalRows;
        private int successRows;
        private int failedRows;
        private String errorMessage;
        private Long triggeredBy;
        private String triggeredByName;
        private LocalDateTime startedAt;
        private LocalDateTime finishedAt;
    }

    /** 同步批次中的单行失败明细。 */
    @Data
    public static class Failure {
        private Long id;
        private Long batchId;
        private int sheetRowNumber;
        private String agencyLineName;
        private String failureReason;
        private LocalDateTime createdAt;
    }
}
