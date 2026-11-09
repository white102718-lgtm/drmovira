package com.adpulse.main.deliveryreport.google;

import com.adpulse.main.google.dto.GoogleDtos.DriveFile;
import com.adpulse.main.google.dto.GoogleDtos.SheetTab;
import jakarta.validation.Valid;
import jakarta.validation.constraints.*;
import java.time.LocalDateTime;
import java.util.List;
import java.util.Map;

/** 投放日报Google模板、预览和推送结果的接口契约。 */
public final class DeliveryReportGooglePushDtos {
    private DeliveryReportGooglePushDtos() {}

    /** 可映射的稳定系统字段。 */
    public record FieldDefinition(String field, String label, boolean required, String type) {}

    /** 日报目标表格需要共享给此服务账户。 */
    public record ServiceAccountInfo(String email) {}

    /** 根据项目日报链接解析并验证的Google目标。 */
    public record ProjectTarget(
            boolean configured,
            String dailyReportUrl,
            DriveFile spreadsheet,
            List<SheetTab> sheets,
            String sheetId,
            String message) {}

    /** 一个系统字段到Google目标列的映射。 */
    public record FieldMapping(
            @NotBlank String systemField,
            @NotBlank @Pattern(regexp = "[A-Z]{1,8}") String targetColumn,
            @NotBlank @Size(max = 255) String targetHeader,
            boolean required,
            boolean uniqueKey) {}

    /** 创建或更新项目日报写入模板。 */
    public record TemplateSave(
            @NotNull @Positive Long projectId,
            @NotBlank @Size(max = 255) String templateName,
            @NotNull @Min(1) @Max(100) Integer headerRow,
            @NotNull @Size(max = 50) List<@NotNull @Valid FieldMapping> fieldMappings,
            @NotNull @Min(0) @Max(1) Integer enableFlag) {}

    /** 模板详情包含项目和Google表格展示快照。 */
    public record TemplateView(
            String id,
            String projectId,
            String projectName,
            String templateName,
            String spreadsheetId,
            String spreadsheetName,
            String sheetId,
            String sheetTitle,
            Integer headerRow,
            List<FieldMapping> fieldMappings,
            Integer enableFlag,
            LocalDateTime updatedAt) {}

    /** 预览或确认推送时仅接受稳定日报ID。 */
    public record ReportSelection(
            @NotEmpty @Size(max = 100) List<@NotNull @Positive Long> reportIds) {}

    /** 预览中的单条目标数据，values按系统字段编码返回。 */
    public record PreviewRow(String reportId, Map<String, Object> values) {}

    /** 同一项目模板对应的一组预览数据。 */
    public record PreviewGroup(
            String projectId,
            String projectName,
            String templateId,
            String templateName,
            String spreadsheetName,
            String sheetTitle,
            List<FieldMapping> fieldMappings,
            List<PreviewRow> rows) {}

    /** 跨项目推送预览。 */
    public record Preview(int totalCount, List<PreviewGroup> groups) {}

    /** 推送明细状态。 */
    public record PushItemView(
            String id,
            String reportId,
            String projectId,
            Integer status,
            Integer targetRow,
            Integer attemptCount,
            String errorMessage) {}

    /** 推送批次状态及逐条结果。 */
    public record PushBatchView(
            String id,
            Integer status,
            Integer totalCount,
            Integer successCount,
            Integer failedCount,
            String errorMessage,
            LocalDateTime startedAt,
            LocalDateTime finishedAt,
            LocalDateTime createdAt,
            List<PushItemView> items) {}
}
