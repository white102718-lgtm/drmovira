package com.adpulse.main.cloak.dto;

import java.time.LocalDateTime;
import java.util.List;

/** 斗篷管理只读视图。 */
public final class CloakViews {
    private CloakViews() {}

    /** 推广域名下拉选项，value保留服务商域名ID。 */
    public record DomainOption(String genId, String genDomain, String value, String label) {}

    /** 投放地区下拉选项，country可包含服务商约定的多个地区代码。 */
    public record CountryOption(String country, String value, String label) {}

    /** 批量提交结果。 */
    public record BatchResult(String batchId, int totalCount, boolean reused) {}

    /** Google Sheet回写结果；单条失败不会影响同批其他记录。 */
    public record SheetWritebackResult(
            String batchId,
            int totalCount,
            int successCount,
            int failedCount,
            List<SheetWritebackFailure> failures) {}

    /** Google Sheet单条回写失败摘要。 */
    public record SheetWritebackFailure(
            String recordId, String agencyLineName, String message) {}

    /** 斗篷管理列表多选记录的Google Sheet回填结果。 */
    public record RecordSheetWritebackResult(
            int totalCount,
            int successCount,
            int failedCount,
            List<SheetWritebackFailure> failures) {}

    /** 斗篷管理列表记录。 */
    public record Record(
            String id,
            String projectId,
            String projectName,
            String agencyLineId,
            String agencyLineName,
            String sourceUrl,
            String reviewUrl,
            String promotionUrl,
            String mode,
            String country,
            String countryLabel,
            boolean blockedLanguage,
            boolean blockedPc,
            boolean blockedProxy,
            String sheetWritebackStatus,
            String sheetWritebackMessage,
            LocalDateTime createdAt) {}

    /** 斗篷管理分页结果。 */
    public record Page<T>(List<T> items, long total, int page, int pageSize) {}
}
