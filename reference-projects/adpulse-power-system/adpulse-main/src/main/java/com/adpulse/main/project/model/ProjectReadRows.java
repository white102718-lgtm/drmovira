package com.adpulse.main.project.model;

import java.math.BigDecimal;

/** 项目分页批量读取的关联行，保留项目归属以避免跨项目混合。 */
public final class ProjectReadRows {
    private ProjectReadRows() {}

    /** 平台、地区、产品链接或外包团队的有序值。 */
    public record Value(Long projectId, String value) {}

    /** 带项目归属的 KPI。 */
    public record Kpi(
            Long projectId,
            String metric,
            String comparator,
            BigDecimal target,
            BigDecimal targetMax) {}

    /** 带项目归属的人员。 */
    public record User(Long projectId, Long userId, String userName) {}
}
