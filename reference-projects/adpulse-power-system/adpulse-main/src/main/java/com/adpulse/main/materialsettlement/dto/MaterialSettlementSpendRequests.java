package com.adpulse.main.materialsettlement.dto;

import jakarta.validation.Valid;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotEmpty;
import jakarta.validation.constraints.Pattern;
import jakarta.validation.constraints.Size;
import java.util.List;

/** 素材师月报任务线花费查询请求。 */
public final class MaterialSettlementSpendRequests {
    private MaterialSettlementSpendRequests() {}

    /** 结算月份及本次月报实际选择的任务线。列表不设数量上限，避免截断月报结算范围。 */
    public record TaskLineSpendQuery(
            @NotBlank @Pattern(regexp = "\\d{4}-(0[1-9]|1[0-2])", message = "必须为YYYY-MM格式")
                    String settlementMonth,
            @NotEmpty List<@Valid TaskLine> taskLines) {}

    /** 任务线花费查询的精确匹配条件。 */
    public record TaskLine(
            @NotBlank @Size(max = 100) String projectName,
            @NotBlank @Size(max = 200) String taskLineName) {}
}
