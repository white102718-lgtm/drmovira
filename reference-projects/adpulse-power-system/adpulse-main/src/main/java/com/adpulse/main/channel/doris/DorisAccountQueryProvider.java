package com.adpulse.main.channel.doris;

import com.adpulse.main.channel.dto.ChannelRequests.AccountQuery;
import com.adpulse.main.channel.model.ChannelModels.Account;
import com.adpulse.main.channel.model.ChannelModels.Aggregate;
import com.adpulse.main.channel.service.AccountQueryProvider;
import java.util.List;
import java.util.regex.Pattern;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.context.annotation.Primary;
import org.springframework.jdbc.core.BeanPropertyRowMapper;
import org.springframework.jdbc.core.namedparam.MapSqlParameterSource;
import org.springframework.jdbc.core.namedparam.NamedParameterJdbcTemplate;
import org.springframework.stereotype.Component;

/** 在 Doris 内以广告账户资产台账为基表，关联广告日明细完成分页、筛选与金额汇总。 */
@Component
@Primary
@ConditionalOnProperty(prefix = "adpulse.doris", name = "enabled", havingValue = "true")
public class DorisAccountQueryProvider implements AccountQueryProvider {
    private static final Pattern IDENTIFIER = Pattern.compile("[A-Za-z0-9_]+");
    private static final BeanPropertyRowMapper<Account> ACCOUNT_MAPPER =
            BeanPropertyRowMapper.newInstance(Account.class);
    private static final BeanPropertyRowMapper<Aggregate> AGGREGATE_MAPPER =
            BeanPropertyRowMapper.newInstance(Aggregate.class);

    private final NamedParameterJdbcTemplate jdbc;
    private final String accountTable;
    private final String assignmentTable;
    private final String spendTable;

    public DorisAccountQueryProvider(DorisJdbcClient client, DorisProperties properties) {
        this.jdbc = client.jdbc();
        this.accountTable =
                qualified(
                        properties.mysqlCatalog(), properties.mysqlDatabase(), "ad_account_asset");
        this.assignmentTable =
                qualified(
                        properties.mysqlCatalog(),
                        properties.mysqlDatabase(),
                        "ad_account_asset_assignment");
        this.spendTable =
                qualified(properties.spendCatalog(), properties.spendDatabase(), "ad_daily_detail");
    }

    /** 查询资产台账账户，并以指定日期区间的 Doris 聚合值填充花费金额。 */
    @Override
    public PageResult find(AccountQuery query, int offset, int pageSize) {
        QueryParts parts = queryParts(query);
        MapSqlParameterSource parameters =
                parts.parameters().addValue("offset", offset).addValue("pageSize", pageSize);
        String columns =
                """
                a.id, a.channel_id, a.account_id, a.account_name, a.account_type,
                a.account_id AS fb_account_id,
                NULL AS take_time, NULL AS timezone, a.managed_bm_id AS bm_id,
                a.managed_bm AS bm_from_feishu,
                0 AS opening_balance, 0 AS by_balance, 0 AS by_balance_u,
                %s AS consumption,
                0 AS balance, 0 AS actual_deduction, 0 AS amount_spent,
                0 AS remaining_spend_cap,
                a.account_status AS status, %s AS usage_status,
                a.account_attribute AS subject_name, NULL AS operator_id, u.operator_name,
                NULL AS belong_team, NULL AS belong_team_id, NULL AS open_date,
                NULL AS assign_time, NULL AS remark,
                a.created_by, a.updated_by, a.created_at, a.updated_at
                """;
        List<Account> accounts =
                jdbc.query(
                        "SELECT "
                                + columns.formatted(
                                        parts.consumptionColumn(), parts.usageStatusColumn())
                                + parts.fromWhere()
                                + " ORDER BY a.updated_at DESC, a.id DESC LIMIT :offset, :pageSize",
                        parameters,
                        ACCOUNT_MAPPER);
        Long total =
                jdbc.queryForObject("SELECT COUNT(*) " + parts.fromWhere(), parameters, Long.class);
        return new PageResult(accounts, total == null ? 0L : total);
    }

    /** 使用与列表相同的资产台账范围汇总区间花费。 */
    @Override
    public Aggregate summarize(AccountQuery query) {
        QueryParts parts = queryParts(query);
        String sql =
                """
                SELECT 0 AS opening_balance,
                    0 AS by_balance,
                    0 AS by_balance_u,
                    COALESCE(SUM(%s), 0) AS consumption,
                    0 AS balance,
                    0 AS actual_deduction,
                    0 AS amount_spent,
                    0 AS remaining_spend_cap
                """
                                .formatted(parts.consumptionColumn())
                        + parts.fromWhere();
        return jdbc.queryForObject(sql, parts.parameters(), AGGREGATE_MAPPER);
    }

    private QueryParts queryParts(AccountQuery query) {
        boolean hasSpendDateRange = query.startDate() != null && query.endDate() != null;
        MapSqlParameterSource parameters = new MapSqlParameterSource();
        StringBuilder sql =
                new StringBuilder(" FROM ")
                        .append(accountTable)
                        .append(" a LEFT JOIN (SELECT ad_account_asset_id, 1 AS usage_status, ")
                        .append("MAX(user_name) AS operator_name FROM ")
                        .append(assignmentTable)
                        .append(
                                " WHERE assignment_status = 'ACTIVE' AND deleted_at = 0 GROUP BY ad_account_asset_id) u ON u.ad_account_asset_id = a.id");
        if (hasSpendDateRange) {
            parameters
                    .addValue("startDate", query.startDate())
                    .addValue("endDate", query.endDate());
            sql.append(" ")
                    .append(
                            """
                                LEFT JOIN (
                                    SELECT account_id, SUM(amount_spent) AS consumption
                                """)
                    .append(" FROM ")
                    .append(spendTable)
                    .append(
                            """

                                    WHERE `level` = 'account'
                                      AND `date` >= :startDate
                                      AND `date` <= :endDate
                                    GROUP BY account_id
                                ) s ON s.account_id = a.account_id
                                """);
        }
        sql.append(
                " WHERE a.deleted_at = 0 AND NOT EXISTS (SELECT 1 FROM "
                        + accountTable
                        + " newer WHERE newer.account_id = a.account_id"
                        + " AND newer.deleted_at = 0 AND newer.id > a.id) ");
        String usageStatusColumn = "COALESCE(u.usage_status, 0)";
        appendFilters(
                sql,
                parameters,
                query,
                hasSpendDateRange ? "COALESCE(s.consumption, 0)" : "0",
                usageStatusColumn);
        return new QueryParts(
                sql.toString(),
                parameters,
                hasSpendDateRange ? "COALESCE(s.consumption, 0)" : "0",
                usageStatusColumn);
    }

    private void appendFilters(
            StringBuilder sql,
            MapSqlParameterSource parameters,
            AccountQuery query,
            String consumptionColumn,
            String usageStatusColumn) {
        equal(sql, parameters, "a.channel_id", "channelId", query.channelId());
        equal(sql, parameters, "a.account_type", "accountType", text(query.accountType()));
        if (query.accountIds() != null && !query.accountIds().isEmpty()) {
            sql.append(" AND a.account_id IN (:accountIds)");
            parameters.addValue("accountIds", query.accountIds());
        }
        like(sql, parameters, "a.managed_bm_id", "bmId", query.bmId());
        like(sql, parameters, "a.account_attribute", "subjectName", query.subjectName());
        equal(sql, parameters, "a.timezone", "timezone", query.timezone());
        equal(sql, parameters, "a.account_status", "status", query.status());
        equal(sql, parameters, usageStatusColumn, "usageStatus", query.usageStatus());
        like(sql, parameters, "u.operator_name", "operatorName", query.operatorName());
        keyword(sql, parameters, query.keyword());
        compare(sql, parameters, consumptionColumn, ">=", "consumptionMin", query.consumptionMin());
        compare(sql, parameters, consumptionColumn, "<=", "consumptionMax", query.consumptionMax());
    }

    private void keyword(StringBuilder sql, MapSqlParameterSource parameters, String value) {
        String normalized = text(value);
        if (normalized == null) return;
        sql.append(
                " AND (a.account_id LIKE :keyword OR a.account_name LIKE :keyword"
                        + " OR a.managed_bm_id LIKE :keyword"
                        + " OR a.managed_bm LIKE :keyword)");
        parameters.addValue("keyword", "%" + normalized + "%");
    }

    private void equal(
            StringBuilder sql,
            MapSqlParameterSource parameters,
            String column,
            String name,
            Object value) {
        if (value == null) return;
        sql.append(" AND ").append(column).append(" = :").append(name);
        parameters.addValue(name, value);
    }

    private void like(
            StringBuilder sql,
            MapSqlParameterSource parameters,
            String column,
            String name,
            String value) {
        String normalized = text(value);
        if (normalized == null) return;
        sql.append(" AND ").append(column).append(" LIKE :").append(name);
        parameters.addValue(name, "%" + normalized + "%");
    }

    private void compare(
            StringBuilder sql,
            MapSqlParameterSource parameters,
            String column,
            String operator,
            String name,
            Object value) {
        if (value == null) return;
        sql.append(" AND ").append(column).append(' ').append(operator).append(" :").append(name);
        parameters.addValue(name, value);
    }

    private String qualified(String catalog, String database, String table) {
        return quote(catalog) + "." + quote(database) + "." + quote(table);
    }

    private String quote(String value) {
        if (value == null || !IDENTIFIER.matcher(value).matches()) {
            throw new IllegalArgumentException("Doris Catalog或数据库名称不合法");
        }
        return "`" + value + "`";
    }

    private String text(String value) {
        return value == null || value.isBlank() ? null : value.trim();
    }

    private record QueryParts(
            String fromWhere,
            MapSqlParameterSource parameters,
            String consumptionColumn,
            String usageStatusColumn) {}
}
