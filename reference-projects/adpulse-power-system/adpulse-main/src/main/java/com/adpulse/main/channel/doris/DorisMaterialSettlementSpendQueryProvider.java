package com.adpulse.main.channel.doris;

import com.adpulse.main.materialsettlement.dto.MaterialSettlementSpendRequests.TaskLine;
import com.adpulse.main.materialsettlement.dto.MaterialSettlementSpendViews.TaskLineSpend;
import com.adpulse.main.materialsettlement.service.MaterialSettlementSpendQueryProvider;
import java.time.LocalDate;
import java.util.ArrayList;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Map;
import java.util.regex.Pattern;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.jdbc.core.RowMapper;
import org.springframework.jdbc.core.namedparam.MapSqlParameterSource;
import org.springframework.jdbc.core.namedparam.NamedParameterJdbcTemplate;
import org.springframework.stereotype.Component;

/** 通过 Doris 广告日明细按项目和代理线精确汇总素材师月报花费。 */
@Component
@ConditionalOnProperty(prefix = "adpulse.doris", name = "enabled", havingValue = "true")
public class DorisMaterialSettlementSpendQueryProvider
        implements MaterialSettlementSpendQueryProvider {
    private static final Pattern IDENTIFIER = Pattern.compile("[A-Za-z0-9_]+");
    private static final String USD = "USD";
    private static final RowMapper<TaskLineSpend> SPEND_MAPPER =
            (resultSet, rowNumber) ->
                    new TaskLineSpend(
                            resultSet.getString("project_name"),
                            resultSet.getString("task_line_name"),
                            resultSet.getBigDecimal("amount"),
                            USD);

    private final NamedParameterJdbcTemplate jdbc;
    private final String spendTable;

    public DorisMaterialSettlementSpendQueryProvider(
            DorisJdbcClient client, DorisProperties properties) {
        jdbc = client.jdbc();
        spendTable =
                qualified(properties.spendCatalog(), properties.spendDatabase(), "ad_daily_detail");
    }

    /** 同一项目的代理线使用一次 IN 查询；项目之间拆分以保留“项目 + 代理线”的精确组合， 避免同名代理线被跨项目误计入。 */
    @Override
    public List<TaskLineSpend> query(
            LocalDate startDate, LocalDate endDate, List<TaskLine> taskLines) {
        Map<String, LinkedHashSet<String>> taskLineNamesByProject = new java.util.LinkedHashMap<>();
        for (TaskLine taskLine : taskLines) {
            taskLineNamesByProject
                    .computeIfAbsent(taskLine.projectName(), ignored -> new LinkedHashSet<>())
                    .add(taskLine.taskLineName());
        }

        List<TaskLineSpend> result = new ArrayList<>();
        for (Map.Entry<String, LinkedHashSet<String>> entry : taskLineNamesByProject.entrySet()) {
            result.addAll(queryProject(entry.getKey(), entry.getValue(), startDate, endDate));
        }
        return result;
    }

    private List<TaskLineSpend> queryProject(
            String projectName,
            LinkedHashSet<String> taskLineNames,
            LocalDate startDate,
            LocalDate endDate) {
        String sql =
                """
                SELECT game_platform AS project_name,
                    agent_line AS task_line_name,
                    COALESCE(SUM(amount_spent), 0) AS amount
                FROM %s
                WHERE game_platform = :projectName
                  AND agent_line IN (:taskLineNames)
                  AND level = 'ad'
                  AND date >= :startDate
                  AND date <= :endDate
                GROUP BY game_platform, agent_line
                """
                        .formatted(spendTable);
        MapSqlParameterSource parameters =
                new MapSqlParameterSource()
                        .addValue("projectName", projectName)
                        .addValue("taskLineNames", taskLineNames)
                        .addValue("startDate", startDate)
                        .addValue("endDate", endDate);
        return jdbc.query(sql, parameters, SPEND_MAPPER);
    }

    private static String qualified(String catalog, String database, String table) {
        return quote(catalog) + "." + quote(database) + "." + quote(table);
    }

    private static String quote(String value) {
        if (value == null || !IDENTIFIER.matcher(value).matches()) {
            throw new IllegalArgumentException("Doris Catalog或数据库名称不合法");
        }
        return "`" + value + "`";
    }
}
