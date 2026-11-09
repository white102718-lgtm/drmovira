package com.adpulse.main.materialsettlement.dto;

import java.math.BigDecimal;
import java.util.List;

/** 素材师月报任务线花费查询响应。 */
public final class MaterialSettlementSpendViews {
    private MaterialSettlementSpendViews() {}

    /** 每条月报任务线在结算自然月内的广告花费；未匹配到广告数据时 amount 为 null。 */
    public record TaskLineSpend(
            String projectName, String taskLineName, BigDecimal amount, String currency) {}

    /** 保持请求任务线顺序的花费查询结果。 */
    public record TaskLineSpendResult(List<TaskLineSpend> items) {}
}
