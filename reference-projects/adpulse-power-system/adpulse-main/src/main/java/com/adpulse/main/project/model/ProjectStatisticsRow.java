package com.adpulse.main.project.model;

import lombok.Data;

/** 项目状态聚合查询结果。 */
@Data
public class ProjectStatisticsRow {
    private Long total;
    private Long active;
    private Long draftOrPending;
    private Long endedOrArchived;
}
