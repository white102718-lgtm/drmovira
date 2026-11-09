package com.adpulse.main.project.sync;

import java.time.LocalDateTime;
import java.util.List;

/** 项目代理线 Google Sheet 同步接口响应。 */
public final class AgencyLineSyncViews {
    private AgencyLineSyncViews() {}

    /** 同步批次列表项。 */
    public record Batch(
            String id,
            String projectId,
            String triggerType,
            String status,
            String linkSnapshot,
            String sheetTitle,
            int totalRows,
            int successRows,
            int failedRows,
            String errorMessage,
            String triggeredBy,
            String triggeredByName,
            LocalDateTime startedAt,
            LocalDateTime finishedAt) {}

    /** 同步失败行详情，不包含 Token 等敏感单元格内容。 */
    public record Failure(
            String id,
            int sheetRowNumber,
            String agencyLineName,
            String failureReason,
            LocalDateTime createdAt) {}

    /** 分页响应。 */
    public record Page<T>(List<T> items, long total, int page, int pageSize) {}
}
