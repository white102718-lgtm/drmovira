package com.adpulse.main.project.dto;

import jakarta.validation.Valid;
import jakarta.validation.constraints.DecimalMax;
import jakarta.validation.constraints.DecimalMin;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotEmpty;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Size;
import java.math.BigDecimal;
import java.util.List;

/** 项目管理写入请求。 */
public final class ProjectRequests {
    private ProjectRequests() {}

    /** 项目保存请求。 */
    public record ProjectSave(
            @NotBlank @Size(max = 50) String projectCode,
            @NotBlank @Size(max = 100) String name,
            @NotBlank @Size(max = 30) String projectType,
            @NotNull List<@NotBlank @Size(max = 1000) String> productLinks,
            @NotBlank @Size(max = 100) String responsibleTeam,
            String amUserId,
            @Size(max = 100) String amName,
            String deliveryLeaderId,
            @Size(max = 100) String deliveryLeaderName,
            @NotNull Boolean isOutsourced,
            @NotNull List<@NotBlank @Size(max = 100) String> outsourcingTeams,
            @NotBlank String priority,
            @NotEmpty List<@NotBlank String> platforms,
            @NotEmpty List<@NotBlank String> countryRegions,
            @NotNull @DecimalMin("0") @DecimalMax("100") BigDecimal serviceFeePercent,
            @NotBlank String status,
            @NotBlank @Size(max = 2000) String productInfo,
            @Size(max = 1000) String customerDailyReportUrl,
            @Size(max = 1000) String agencyLineUrl,
            @NotNull Boolean createWallet,
            @NotEmpty List<@Valid KpiSave> kpiRequirements,
            String dataSpecialistId,
            @Size(max = 100) String dataSpecialist,
            List<@Valid UserAssignmentSave> amUsers,
            List<@Valid UserAssignmentSave> dataSpecialists) {
        /** 兼容尚未传入代理线链接的内部调用。 */
        public ProjectSave(
                String projectCode,
                String name,
                String projectType,
                List<String> productLinks,
                String responsibleTeam,
                String amUserId,
                String amName,
                String deliveryLeaderId,
                String deliveryLeaderName,
                Boolean isOutsourced,
                List<String> outsourcingTeams,
                String priority,
                List<String> platforms,
                List<String> countryRegions,
                BigDecimal serviceFeePercent,
                String status,
                String productInfo,
                String customerDailyReportUrl,
                Boolean createWallet,
                List<KpiSave> kpiRequirements,
                String dataSpecialistId,
                String dataSpecialist,
                List<UserAssignmentSave> amUsers,
                List<UserAssignmentSave> dataSpecialists) {
            this(
                    projectCode,
                    name,
                    projectType,
                    productLinks,
                    responsibleTeam,
                    amUserId,
                    amName,
                    deliveryLeaderId,
                    deliveryLeaderName,
                    isOutsourced,
                    outsourcingTeams,
                    priority,
                    platforms,
                    countryRegions,
                    serviceFeePercent,
                    status,
                    productInfo,
                    customerDailyReportUrl,
                    null,
                    createWallet,
                    kpiRequirements,
                    dataSpecialistId,
                    dataSpecialist,
                    amUsers,
                    dataSpecialists);
        }
    }

    /** 项目用户选择项。 */
    public record UserAssignmentSave(
            @NotBlank String userId, @NotBlank @Size(max = 100) String userName) {}

    /** KPI保存请求。 */
    public record KpiSave(
            @NotBlank @Size(max = 100) String metric,
            @NotBlank String comparator,
            @NotNull @DecimalMin("0") BigDecimal target,
            @DecimalMin("0") BigDecimal targetMax) {}

    /** 全量代理线绑定请求。 */
    public record AgencyLineReplace(@NotNull List<String> agencyLineIds) {}

    /** 增量代理线绑定请求。 */
    public record AgencyLinePatch(
            List<String> add, List<String> remove, @Size(max = 200) String requestId) {}

    /** 同一项目代理线的业务状态批量修改，整批成功或回滚。 */
    public record AgencyLineStatusChange(
            @NotEmpty @Size(max = 100) List<@NotBlank String> agencyLineIds,
            @NotBlank String status) {}

    /** 优化师快捷修改，空 ID 表示清空分配。 */
    public record AgencyLineOptimizerChange(String optimizerId) {}

    /** 代理线保存请求，兼容前端的agencyLine包装。 */
    public record AgencyLineCreate(@NotNull @Valid AgencyLineSave agencyLine, String projectId) {}

    /** 代理线字段。 */
    public record AgencyLineSave(
            String id,
            String projectId,
            @NotBlank @Size(max = 80) String name,
            @NotBlank @Size(max = 100) String platform,
            @Size(max = 50) String type,
            @Size(max = 2000) String deliveryUrl,
            @Size(max = 255) String pageId,
            @Size(max = 255) String pixelName,
            @Size(max = 100) String pixelId,
            @Size(max = 10000) String token,
            @Size(max = 200) String testCode,
            @Size(max = 2000) String cloakUrl,
            String optimizerId,
            @Size(max = 100) String optimizerName) {
        /** 兼容尚未补齐投放明细字段的内部调用。 */
        public AgencyLineSave(
                String id,
                String projectId,
                String name,
                String platform,
                String deliveryUrl,
                String pageId,
                String pixelName,
                String optimizerId,
                String optimizerName) {
            this(
                    id,
                    projectId,
                    name,
                    platform,
                    null,
                    deliveryUrl,
                    pageId,
                    pixelName,
                    null,
                    null,
                    null,
                    null,
                    optimizerId,
                    optimizerName);
        }

        @Override
        public String toString() {
            return "AgencyLineSave[redacted]";
        }
    }
}
