package com.adpulse.main.project.mapper;

import static org.assertj.core.api.Assertions.assertThat;

import java.util.List;
import java.util.Map;
import org.apache.ibatis.builder.xml.XMLMapperBuilder;
import org.apache.ibatis.session.Configuration;
import org.junit.jupiter.api.Test;

/** 校验批量读取始终限定当前页，空集合不能退化为全表查询。 */
class ProjectBatchMapperTest {
    @Test
    void unboundOptionsExcludeBoundAndDeletedLinesAndSelectOnlyDisplayFields() throws Exception {
        Configuration configuration = new Configuration();
        String resource = "mapper/project/ProjectMapper.xml";
        try (var stream = getClass().getClassLoader().getResourceAsStream(resource)) {
            new XMLMapperBuilder(stream, configuration, resource, configuration.getSqlFragments())
                    .parse();
        }
        var statement =
                configuration.getMappedStatement(
                        ProjectMapper.class.getName() + ".findUnboundAgencyLineOptions");
        var query = statement.getBoundSql(Map.of("keyword", "_%代理线"));
        assertThat(query.getSql().replaceAll("\\s+", " "))
                .contains(
                        "SELECT CAST(id AS CHAR) AS id, line_name AS name",
                        "deleted_at = 0",
                        "project_id IS NULL",
                        "LOCATE(?, line_name)",
                        "LIMIT 50")
                .doesNotContain("_%代理线", "optimizer", "pixel_name");
        assertThat(query.getParameterMappings()).hasSize(1);
        assertThat(statement.getBoundSql(Map.of()).getSql()).doesNotContain("LOCATE");
        assertThat(statement.getBoundSql(Map.of("keyword", "")).getSql()).doesNotContain("LOCATE");
    }

    @Test
    void restrictsEveryBatchQueryToRequestedIds() throws Exception {
        Configuration configuration = new Configuration();
        for (String resource :
                List.of(
                        "mapper/project/ProjectMapper.xml",
                        "mapper/safeheron/SafeheronMapper.xml")) {
            try (var stream = getClass().getClassLoader().getResourceAsStream(resource)) {
                new XMLMapperBuilder(
                                stream, configuration, resource, configuration.getSqlFragments())
                        .parse();
            }
        }
        for (String name :
                List.of(
                        "Platforms",
                        "Regions",
                        "ProductLinks",
                        "OutsourcingTeams",
                        "Kpis",
                        "ProjectAms",
                        "ProjectDataSpecialists")) {
            check(
                    configuration,
                    ProjectMapper.class.getName() + ".find" + name + "ByProjectIds",
                    "projectIds",
                    "project_id");
        }
        String walletPrefix = "com.adpulse.main.safeheron.mapper.SafeheronMapper.";
        check(
                configuration,
                walletPrefix + "findWalletsByCustomerRefIds",
                "customerRefIds",
                "customer_ref_id");
        check(
                configuration,
                walletPrefix + "findWalletCoinsByAccountKeys",
                "accountKeys",
                "account_key");
    }

    private void check(
            Configuration configuration, String statement, String parameter, String column) {
        var mapped = configuration.getMappedStatement(statement);
        var batch = mapped.getBoundSql(Map.of(parameter, List.of("1", "2")));
        String sql = batch.getSql().replaceAll("\\s+", " ");
        assertThat(sql).contains("deleted_at = 0", column + " IN", "ORDER BY");
        assertThat(batch.getParameterMappings()).hasSize(2);
        assertThat(mapped.getResultMaps())
                .allSatisfy(result -> assertThat(result.hasNestedQueries()).isFalse());
        assertThat(mapped.getBoundSql(Map.of(parameter, List.of())).getSql()).contains("AND 1 = 0");
        assertThat(mapped.getBoundSql(Map.of()).getSql()).contains("AND 1 = 0");
    }
}
