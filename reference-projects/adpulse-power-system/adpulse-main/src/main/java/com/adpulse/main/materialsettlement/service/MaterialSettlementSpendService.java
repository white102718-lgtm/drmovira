package com.adpulse.main.materialsettlement.service;

import com.adpulse.main.materialsettlement.dto.MaterialSettlementSpendRequests;
import com.adpulse.main.materialsettlement.dto.MaterialSettlementSpendRequests.TaskLine;
import com.adpulse.main.materialsettlement.dto.MaterialSettlementSpendViews;
import com.adpulse.main.materialsettlement.dto.MaterialSettlementSpendViews.TaskLineSpend;
import java.time.YearMonth;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import org.springframework.stereotype.Service;

/** 素材师月报按任务线查询广告花费的业务服务。 */
@Service
public class MaterialSettlementSpendService {
    private static final String USD = "USD";

    private final MaterialSettlementSpendQueryProvider queryProvider;

    public MaterialSettlementSpendService(MaterialSettlementSpendQueryProvider queryProvider) {
        this.queryProvider = queryProvider;
    }

    /**
     * 查询结算自然月的任务线花费。
     *
     * <p>结果按请求顺序返回，并补齐无数据的任务线，前端可明确展示为“无花费数据”而非零值。
     */
    public MaterialSettlementSpendViews.TaskLineSpendResult queryTaskLineSpends(
            MaterialSettlementSpendRequests.TaskLineSpendQuery request) {
        YearMonth settlementMonth = YearMonth.parse(request.settlementMonth());
        List<TaskLine> taskLines = request.taskLines().stream().map(this::normalize).toList();
        Map<String, TaskLineSpend> spendsByTaskLine = new LinkedHashMap<>();
        for (TaskLineSpend spend :
                queryProvider.query(
                        settlementMonth.atDay(1), settlementMonth.atEndOfMonth(), taskLines)) {
            spendsByTaskLine.put(key(spend.projectName(), spend.taskLineName()), spend);
        }

        return new MaterialSettlementSpendViews.TaskLineSpendResult(
                taskLines.stream()
                        .map(
                                taskLine -> {
                                    TaskLineSpend spend =
                                            spendsByTaskLine.get(
                                                    key(
                                                            taskLine.projectName(),
                                                            taskLine.taskLineName()));
                                    return spend == null
                                            ? new TaskLineSpend(
                                                    taskLine.projectName(),
                                                    taskLine.taskLineName(),
                                                    null,
                                                    USD)
                                            : spend;
                                })
                        .toList());
    }

    private TaskLine normalize(TaskLine taskLine) {
        return new TaskLine(taskLine.projectName().trim(), taskLine.taskLineName().trim());
    }

    private String key(String projectName, String taskLineName) {
        return projectName + '\u0000' + taskLineName;
    }
}
