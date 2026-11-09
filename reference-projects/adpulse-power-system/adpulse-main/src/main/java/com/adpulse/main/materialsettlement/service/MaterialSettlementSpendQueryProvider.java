package com.adpulse.main.materialsettlement.service;

import com.adpulse.main.materialsettlement.dto.MaterialSettlementSpendRequests.TaskLine;
import com.adpulse.main.materialsettlement.dto.MaterialSettlementSpendViews.TaskLineSpend;
import java.time.LocalDate;
import java.util.List;

/** 素材师月报任务线花费的数据源抽象。 */
public interface MaterialSettlementSpendQueryProvider {
    /**
     * 按项目名称、代理线名称与日期区间精确汇总花费。
     *
     * <p>调用方传入的代理线集合来自月报本身，不允许退化为未筛选的项目全量查询。
     */
    List<TaskLineSpend> query(LocalDate startDate, LocalDate endDate, List<TaskLine> taskLines);
}
