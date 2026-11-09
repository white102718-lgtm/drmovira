package com.adpulse.main.google.dto;

import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import java.math.BigDecimal;
import java.time.LocalDate;
import java.time.LocalDateTime;
import java.util.List;
import java.util.Map;

/** Google数据集成接口请求与响应。 */
public final class GoogleDtos {
    private GoogleDtos() {}

    /** Google账号及其映射。 */
    public record Account(
            String id,
            String email,
            String picture,
            Integer authStatus,
            LocalDateTime authorizedAt,
            List<Mapping> mappings) {}

    /** Google Sheets映射。 */
    public record Mapping(
            String id,
            String googleAccountId,
            String name,
            Integer reportType,
            String spreadsheetId,
            String spreadsheetName,
            String spreadsheetModifiedTime,
            String sheetNames,
            String fieldMappings,
            Integer syncDirection,
            Integer conflictStrategy,
            Integer dateRangeType,
            String dateRangeConfig,
            Integer syncFrequency,
            String syncTime,
            Integer enableFlag,
            LocalDateTime lastSyncTime) {}

    /** Google Sheets映射保存请求。 */
    public record MappingSave(
            @NotNull Long googleAccountId,
            @NotBlank String name,
            @NotNull Integer reportType,
            @NotBlank String spreadsheetId,
            @NotBlank String spreadsheetName,
            String spreadsheetModifiedTime,
            @NotNull List<String> sheetNames,
            @NotNull Map<String, Object> fieldMappings,
            @NotNull Integer syncDirection,
            @NotNull Integer conflictStrategy,
            @NotNull Integer dateRangeType,
            @NotNull Map<String, Object> dateRangeConfig,
            @NotNull Integer syncFrequency,
            String syncTime) {}

    /** 映射启停请求。 */
    public record StatusSave(@NotNull Integer enableFlag) {}

    /** Google Drive表格文件。 */
    public record DriveFile(String id, String name, String modifiedTime) {}

    /** Google Sheet子表。 */
    public record SheetTab(String id, String title) {}

    /** Google Sheets同步结果列表项。 */
    public record SyncData(
            String id,
            LocalDate startDate,
            String taskName,
            String subtaskName,
            BigDecimal spendAmount,
            BigDecimal returnAmount,
            Long impressions,
            Long clicks,
            Long registrations,
            Long purchases,
            Long subscriptions,
            String mediaPlacement,
            LocalDateTime updatedAt) {}

    /** Google Sheets同步结果分页。 */
    public record SyncDataPage(List<SyncData> items, long total, int page, int pageSize) {}

    /** Google Sheets映射同步任务日志。 */
    public record SyncLog(
            String id,
            boolean fullSync,
            Integer status,
            String errorMessage,
            LocalDateTime startedAt,
            LocalDateTime finishedAt,
            LocalDateTime createdAt) {}

    /** Google Sheets映射同步任务日志分页。 */
    public record SyncLogPage(List<SyncLog> items, long total, int page, int pageSize) {}
}
