package com.adpulse.main.project.dto;

import java.math.BigDecimal;
import java.time.LocalDateTime;
import java.util.List;

/** 项目管理接口响应模型。 */
public final class ProjectViews {
    private ProjectViews() {}

    /** 项目绑定搜索只返回代理线标识与展示名称。 */
    public record AgencyLineOption(String id, String name) {}

    /** 项目轻量下拉只返回稳定标识与名称，避免加载项目完整详情。 */
    public record ProjectSearchOption(String id, String name) {}

    /** 斗篷等下游场景读取的项目代理线轻量选项。 */
    public record ProjectAgencyLineDeliveryOption(
            String id, String name, String platform, String deliveryUrl) {}

    /** 项目管理页签总数，不受分页及列表筛选条件影响。 */
    public record TabCounts(long projectCount, long agencyLineCount) {}

    /** KPI响应。 */
    public record Kpi(String metric, String comparator, BigDecimal target, BigDecimal targetMax) {}

    /** 项目用户选择项。 */
    public record UserAssignment(String userId, String userName) {}

    /** 项目详情，保留少量前端兼容投影但不持久化未来字段。 */
    public record ProjectDetail(
            String id,
            String projectCode,
            String name,
            String projectType,
            List<String> productLinks,
            String productName,
            String productInfo,
            String responsibleTeam,
            String amUserId,
            String amName,
            String deliveryLeaderId,
            String deliveryLeaderName,
            boolean isOutsourced,
            List<String> outsourcingTeams,
            String priority,
            List<String> platforms,
            List<String> countryRegions,
            BigDecimal serviceFeePercent,
            String status,
            String customerDailyReportUrl,
            String agencyLineUrl,
            List<Kpi> kpiRequirements,
            String primaryKpi,
            List<String> agencyLineIds,
            List<String> agentLines,
            List<Object> deliveryLines,
            int adAccountCount,
            int materialCount,
            BigDecimal dailyBudget,
            String currency,
            String attributionWindow,
            String timezone,
            String startDate,
            List<String> mediaChannelIds,
            String dataSpecialist,
            String dataSpecialistId,
            List<UserAssignment> amUsers,
            List<UserAssignment> dataSpecialists,
            boolean createWallet,
            ProjectWallet wallet,
            LocalDateTime updatedAt) {}

    /** 项目关联的Safeheron入金币钱包。 */
    public record ProjectWallet(
            String id,
            String key,
            String ethAddress,
            String usdtAddress,
            String feeUnit,
            String accountName) {}

    /** 代理线详情。 */
    public record AgencyLineDetail(
            String id,
            String projectId,
            String name,
            String platform,
            String type,
            String deliveryUrl,
            String pixelName,
            String pixelId,
            String token,
            String testCode,
            String cloakUrl,
            String optimizerId,
            String optimizerName,
            Integer optimizerStatus,
            String status,
            boolean enabled,
            boolean autoRun,
            boolean isSend,
            String objective,
            String packageName,
            String packageType,
            String pageId,
            LocalDateTime createdAt,
            LocalDateTime updatedAt) {
        @Override
        public String toString() {
            return "AgencyLineDetail[redacted]";
        }
    }

    /** 代理线投放链接的不可变历史版本。 */
    public record AgencyLineDeliveryUrlHistory(
            String id,
            String agencyLineId,
            int versionNo,
            String deliveryUrl,
            String changedBy,
            String changedByName,
            LocalDateTime changedAt) {}

    /** 分页响应。 */
    public record Page<T>(List<T> items, long total, int page, int pageSize) {}

    /** 项目页面初始化所需的轻量上下文。 */
    public record ProjectContext(ProjectStatistics statistics, List<ProjectOption> options) {}

    /** 投放地区级联选项。 */
    public record RegionOption(String code, String name, List<CountryOption> countries) {}

    /** 投放国家或地区选项。 */
    public record CountryOption(String code, String name) {}

    /** 项目状态统计。 */
    public record ProjectStatistics(
            long total, long active, long draftOrPending, long endedOrArchived) {}

    /** 代理线筛选及创建所需的轻量项目选项。 */
    public record ProjectOption(
            String id, String name, String projectCode, String status, List<String> platforms) {}

    /** 项目下已完成任务的只读摘要，不包含交付附件等任务私有内容。 */
    public record CompletedTask(
            String id,
            String taskCode,
            String title,
            String kind,
            String ownerName,
            LocalDateTime completedAt) {}

    /** 已完成结项申请中的原始结算字段，保留字符串供业务层校验。 */
    public record ClosureSettlement(String currency, String amount) {}

    /** 按原币种汇总的结项金额，不进行跨币种换算。 */
    public record SettledAmount(String currency, BigDecimal amount) {}

    /** 项目经营概览；结算来自已完成结项申请，其余经营金额暂未接入。 */
    public record OperatingOverview(
            ProjectDetail project,
            BigDecimal actualSpend,
            BigDecimal settledAmount,
            String currency,
            String settlementStatus,
            boolean attributionCompleted,
            String metricCutoff,
            int completedPlanCount,
            List<Object> completedPlans,
            int completedTaskCount,
            List<CompletedTask> completedTasks,
            int totalPlanCount,
            int totalTaskCount,
            String dataQualityStatus,
            String dataQualityNote,
            List<SettledAmount> settledAmounts) {}
}
