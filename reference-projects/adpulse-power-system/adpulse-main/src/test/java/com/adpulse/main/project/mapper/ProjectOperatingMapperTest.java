package com.adpulse.main.project.mapper;

import static org.assertj.core.api.Assertions.assertThat;

import java.util.Map;
import org.apache.ibatis.builder.xml.XMLMapperBuilder;
import org.apache.ibatis.session.Configuration;
import org.junit.jupiter.api.Test;

/** 保证项目任务汇总范围和代理线状态更新归属条件。 */
class ProjectOperatingMapperTest {
    @Test
    void filtersNamesWithinProjectForBothRowsAndCount() throws Exception {
        String resource = "mapper/project/ProjectMapper.xml";
        Configuration config = new Configuration();
        try (var stream = getClass().getClassLoader().getResourceAsStream(resource)) {
            new XMLMapperBuilder(stream, config, resource, config.getSqlFragments()).parse();
        }
        for (String statement : new String[] {"findAgencyLines", "countAgencyLines"}) {
            var bound =
                    config.getMappedStatement(ProjectMapper.class.getName() + "." + statement)
                            .getBoundSql(
                                    Map.of(
                                            "lineName",
                                            "渠道_%",
                                            "projectId",
                                            9L,
                                            "offset",
                                            0,
                                            "pageSize",
                                            10));
            assertThat(bound.getSql())
                    .contains("LOCATE(?, line_name) > 0", "project_id = ?", "deleted_at = 0")
                    .doesNotContain("pixel_name LIKE", "optimizer_name LIKE", "渠道_%");
            assertThat(bound.getParameterMappings())
                    .extracting(org.apache.ibatis.mapping.ParameterMapping::getProperty)
                    .contains("lineName", "projectId");
            var empty =
                    config.getMappedStatement(ProjectMapper.class.getName() + "." + statement)
                            .getBoundSql(
                                    Map.of(
                                            "lineName",
                                            "",
                                            "projectId",
                                            9L,
                                            "offset",
                                            0,
                                            "pageSize",
                                            10));
            assertThat(empty.getSql()).doesNotContain("LOCATE").contains("project_id = ?");
        }
    }

    @Test
    void matchesAnyAgencyLineKeywordAcrossDisplayedFields() throws Exception {
        String resource = "mapper/project/ProjectMapper.xml";
        Configuration config = new Configuration();
        try (var stream = getClass().getClassLoader().getResourceAsStream(resource)) {
            new XMLMapperBuilder(stream, config, resource, config.getSqlFragments()).parse();
        }
        Map<String, Object> params = new java.util.HashMap<>();
        params.put("keywords", java.util.List.of("link-a", "link-b"));
        params.put("optimizerId", 9L);
        params.put("offset", 0);
        params.put("pageSize", 20);

        for (String statement : new String[] {"findAgencyLines", "countAgencyLines"}) {
            var bound =
                    config.getMappedStatement(ProjectMapper.class.getName() + "." + statement)
                            .getBoundSql(params);
            String sql = bound.getSql().replaceAll("\\s+", " ");
            assertThat(sql)
                    .contains(
                            "LOCATE(?, line_name) > 0",
                            "LOCATE(?, delivery_url) > 0",
                            "LOCATE(?, pixel_name) > 0",
                            "LOCATE(?, optimizer_name) > 0",
                            "OR",
                            "optimizer_id = ?");
            assertThat(bound.getParameterMappings())
                    .extracting(org.apache.ibatis.mapping.ParameterMapping::getProperty)
                    .anyMatch(property -> property.startsWith("__frch_keyword_"))
                    .contains("optimizerId");
        }
    }

    @Test
    void keepsNullableOptimizerColumnsAndHistoricalStatusInSingleQuery() throws Exception {
        String resource = "mapper/project/ProjectMapper.xml";
        Configuration config = new Configuration();
        try (var stream = getClass().getClassLoader().getResourceAsStream(resource)) {
            new XMLMapperBuilder(stream, config, resource, config.getSqlFragments()).parse();
        }
        String prefix = ProjectMapper.class.getName() + ".";
        var line = new com.adpulse.main.project.model.AgencyLine();
        line.setId(2L);
        var update = config.getMappedStatement(prefix + "updateAgencyLine").getBoundSql(line);
        assertThat(update.getSql()).contains("optimizer_id = ?", "optimizer_name = ?");
        assertThat(update.getParameterMappings())
                .extracting(org.apache.ibatis.mapping.ParameterMapping::getProperty)
                .contains("optimizerId", "optimizerName");
        var list =
                config.getMappedStatement(prefix + "findAgencyLines")
                        .getBoundSql(Map.of("offset", 0, "pageSize", 20))
                        .getSql();
        assertThat(list)
                .contains("optimizer_status", "u.deleted_at = 0")
                .doesNotContain("INNER JOIN", "u.status = 1");
        var reference =
                config.getMappedStatement(prefix + "findUserReference")
                        .getBoundSql(Map.of("id", 3L))
                        .getSql();
        assertThat(reference).contains("deleted_at = 0").doesNotContain("status = 1");
    }

    @Test
    void keepsProjectAndSoftDeleteFilters() throws Exception {
        String resource = "mapper/project/ProjectMapper.xml";
        Configuration config = new Configuration();
        try (var stream = getClass().getClassLoader().getResourceAsStream(resource)) {
            new XMLMapperBuilder(stream, config, resource, config.getSqlFragments()).parse();
        }
        String prefix = ProjectMapper.class.getName() + ".";
        String settlements =
                config.getMappedStatement(prefix + "findClosureSettlements")
                        .getBoundSql(Map.of("projectId", 1L))
                        .getSql()
                        .replaceAll("\\s+", " ");
        assertThat(settlements)
                .contains(
                        "deleted_at = 0",
                        "asset_type = 'PROJECT_CLOSURE'",
                        "status = 'APPROVED'",
                        "'$.projectId'",
                        "CAST(? AS CHAR)",
                        "'$.settlementCurrency'",
                        "'$.settlementAmount'")
                .doesNotContain("requester_id =", "JOIN", "status = 'PROCESSING'");
        String tasks =
                config.getMappedStatement(prefix + "findCompletedProjectTasks")
                        .getBoundSql(Map.of("projectId", 1L, "offset", 0, "pageSize", 10))
                        .getSql()
                        .replaceAll("\\s+", " ");
        assertThat(tasks)
                .contains(
                        "project_id = ?",
                        "deleted_at = 0",
                        "'DELIVERY', 'MATERIAL'",
                        "status = 'COMPLETED'",
                        "LIMIT ?, ?")
                .doesNotContain("creator_id =", "owner_id =", "assigner_id =", "'MEDIA'");
        String update =
                config.getMappedStatement(prefix + "updateAgencyLineStatus")
                        .getBoundSql(
                                Map.of(
                                        "id",
                                        2L,
                                        "projectId",
                                        1L,
                                        "status",
                                        "stopped",
                                        "updatedBy",
                                        9L))
                        .getSql()
                        .replaceAll("\\s+", " ");
        assertThat(update)
                .contains(
                        "status = ?",
                        "id = ? AND project_id <=> ? AND deleted_at = 0",
                        "? IS NULL OR EXISTS");
    }
}
