package com.adpulse.main.deliveryreport;

import jakarta.validation.Valid;
import jakarta.validation.constraints.*;
import java.math.BigDecimal;
import java.math.RoundingMode;
import java.time.LocalDate;
import java.util.List;

/** 投放日报的固定业务契约；平台金额只出现在响应中，不接受客户端写入。 */
public final class DeliveryReportTypes {
    private DeliveryReportTypes() {}

    /** 投手可编辑的业务指标，金额统一为美元。 */
    public record Metrics(
            @NotNull @DecimalMin("0") @Digits(integer = 14, fraction = 2) BigDecimal dailySpend,
            @NotNull @Min(0) Long impressions,
            @NotNull @Min(0) Long clicks,
            @NotNull @Min(0) Long installs,
            @NotNull @Min(0) Long registrations,
            @NotNull @Min(0) Long firstPurchases,
            @NotNull @Digits(integer = 14, fraction = 2) BigDecimal adjustmentAmount,
            @NotNull @DecimalMin("0") @Digits(integer = 14, fraction = 2) BigDecimal secondaryDeduction,
            @NotNull @Pattern(regexp = "未设置|公司承担|本人承担") String adjustmentType,
            @NotNull @Size(max = 2000) String remark) {
        /** 新提交和历史JSON回显均使用两位金额，避免旧四位数据再次写回。 */
        public Metrics {
            dailySpend = money(dailySpend);
            adjustmentAmount = money(adjustmentAmount);
            secondaryDeduction = money(secondaryDeduction);
        }
    }

    private static BigDecimal money(BigDecimal value) {
        return value == null ? null : value.setScale(2, RoundingMode.HALF_UP);
    }

    /** 一次保存一个日期的若干行；自然键冲突时更新本人原记录。 */
    public record SaveRequest(
            @NotNull LocalDate date,
            @NotEmpty @Size(max = 500) List<@NotNull @Valid SaveRow> rows) {}

    /** 客户端只传稳定归属和人工字段，来源集合由服务端重新取数。 */
    public record SaveRow(
            @NotNull @Positive Long projectId,
            @NotNull @Positive Long agencyLineId,
            @NotBlank @Size(max = 64) String platform,
            @NotNull @Valid Metrics metrics,
            @NotNull @Size(max = 5) List<@NotNull @Positive Long> attachmentIds) {}

    /** 可用于匹配及手工补录的有效项目、代理线组合。 */
    public record LineOption(
            String projectId, String projectName, String agencyLineId, String agencyLineName) {}

    /** 本人上传的截图元数据。 */
    public record Attachment(String id, String name, String mimeType) {}

    /** Doris campaign 层按人员、项目、代理线和平台聚合后的事实。 */
    public record PlatformRow(
            String projectName,
            String agencyLineName,
            String platform,
            BigDecimal actualSpend,
            long impressions,
            long clicks,
            long installs,
            long registrations,
            long firstPurchases,
            List<String> accountIds,
            List<String> campaignIds) {
        /** 平台聚合完成后统一四舍五入，保留两位小数。 */
        public PlatformRow {
            actualSpend = money(actualSpend);
        }
    }

    /** 已保存内容与最新平台事实合并后的单行。 */
    public record Row(
            String id,
            String projectId,
            String projectName,
            String agencyLineId,
            String agencyLineName,
            String platform,
            BigDecimal actualSpend,
            Metrics metrics,
            List<Attachment> attachments,
            List<String> accountIds,
            List<String> campaignIds,
            boolean saved) {}

    /** 当日仅返回本人记录；未匹配数量用于说明被隐藏的平台数据。 */
    public record Result(
            LocalDate date,
            String reporterId,
            String reporterName,
            int unmatchedCount,
            List<Row> rows,
            String departmentName) {
        public Result(
                LocalDate date,
                String reporterId,
                String reporterName,
                int unmatchedCount,
                List<Row> rows) {
            this(date, reporterId, reporterName, unmatchedCount, rows, "未设置");
        }
    }

    /** 可查看的填报人员，只返回导航所需信息。 */
    public record Reporter(String id, String name) {}

    /** 批量平台查询仅返回回显需要的消耗，不收集大量账户及广告系列ID。 */
    public record SpendRow(
            LocalDate date,
            String placerId,
            String projectName,
            String agencyLineName,
            String platform,
            BigDecimal actualSpend) {}

    /** 批量读取截图元数据的归属。 */
    public record ReportAttachment(String reportId, String id, String name, String mimeType) {}

    /** 已填日报的服务端分页，days仅包含当前页记录。 */
    public record ReadPage(long total, int page, int pageSize, List<Result> days) {}

    /** 当前筛选范围的统计，不随翻页改变。 */
    public record ReadStats(long count, BigDecimal dailySpend, BigDecimal actualSpend) {}

    /** Google推送使用的服务端可信日报快照，不接受客户端覆盖业务字段。 */
    public record PushSourceRow(
            String reportId,
            LocalDate date,
            String reporterName,
            String departmentName,
            String projectId,
            String projectName,
            String agencyLineName,
            String platform,
            BigDecimal actualSpend,
            Metrics metrics,
            List<String> accountIds,
            List<String> campaignIds) {}

    /** 时间段内本人已保存的逐日日报，作为绩效聚合和展开明细的同一数据源。 */
    public record PerformanceResult(
            LocalDate startDate, LocalDate endDate, String departmentName, List<Result> days) {}
}
