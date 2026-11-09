package com.adpulse.main.safeheron.dto;

import jakarta.validation.constraints.DecimalMin;
import jakarta.validation.constraints.Max;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Positive;
import jakarta.validation.constraints.Size;
import java.math.BigDecimal;
import java.time.LocalDate;

/** Safeheron归集管理接口请求。 */
public final class SafeheronRequests {
    private SafeheronRequests() {}

    /** 归集规则分页条件。 */
    public record RuleQuery(Integer page, Integer pageSize) {}

    /** 归集规则保存请求。 */
    public record RuleSave(
            @NotNull Long deptId,
            @NotBlank String collectAccountKey,
            @NotBlank String coinKey,
            @NotNull @DecimalMin("0") BigDecimal thresholdUsd,
            @NotNull @Positive Integer frequency,
            @NotNull @Min(0) @Max(1) Integer gasStationEnabled,
            @DecimalMin("0") BigDecimal reserveGas,
            @DecimalMin("0") BigDecimal maxTxFee,
            String signer,
            @NotNull @Min(0) @Max(1) Integer status) {}

    /** 规则启停请求。 */
    public record StatusSave(@NotNull @Min(0) @Max(1) Integer status) {}

    /** 团队审批人保存请求。 */
    public record ApproverSave(@NotBlank String teamId, @NotNull Long approverId) {}

    /** Safeheron团队及API凭证新增请求。 */
    public record TeamCreate(
            @NotBlank @Size(max = 64) String teamId,
            @NotBlank @Size(max = 100) String teamName,
            @Size(max = 256) String baseUrl,
            @NotBlank @Size(max = 256) String apiKey,
            @NotBlank String privateKey,
            @NotBlank String safeheronPublicKey,
            @Positive Long requestTimeout) {}

    /** 归集记录查询条件。 */
    public record RecordQuery(
            String teamId,
            Long deptId,
            Integer status,
            String taskId,
            LocalDate startDate,
            LocalDate endDate,
            Integer page,
            Integer pageSize) {}
}
