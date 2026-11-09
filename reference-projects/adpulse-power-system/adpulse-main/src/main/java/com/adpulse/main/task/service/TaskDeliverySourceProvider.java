package com.adpulse.main.task.service;

import java.math.BigDecimal;
import java.time.LocalDate;
import java.util.List;

/** 按当前投手与任务明细读取 Doris 交付事实。 */
public interface TaskDeliverySourceProvider {
    record Facts(
            List<String> accountIds,
            List<String> campaignIds,
            List<String> adsetIds,
            List<String> adIds,
            BigDecimal actualSpend) {}

    Facts query(
            LocalDate startDate,
            LocalDate endDate,
            String placerId,
            String projectName,
            List<String> agencyLineNames,
            List<String> platforms);
}
