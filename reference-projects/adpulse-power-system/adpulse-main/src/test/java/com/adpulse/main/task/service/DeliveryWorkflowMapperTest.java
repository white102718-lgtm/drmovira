package com.adpulse.main.task.service;

import static org.assertj.core.api.Assertions.assertThat;

import com.adpulse.main.task.mapper.TaskMapper;
import java.util.Map;
import org.apache.ibatis.builder.xml.XMLMapperBuilder;
import org.apache.ibatis.session.Configuration;
import org.junit.jupiter.api.Test;

/** 校验持久层状态与权限条件，防止仅 Service 模拟测试通过而 SQL 流转仍走旧流程。 */
class DeliveryWorkflowMapperTest {
    @Test
    void shouldApplyDeliveryFiltersBeforePaginationAndCounting() throws Exception {
        var configuration = configuration();
        for (String method : new String[] {"findTasks", "countTasks"}) {
            String delivery =
                    sql(
                            configuration,
                            method,
                            Map.of("taskType", "DELIVERY", "status", "FAILED", "keyword", "项目"));
            assertThat(delivery)
                    .contains(
                            "status IN ('REJECTED', 'WITHDRAWN')",
                            "owner_name LIKE",
                            "search_project.project_name LIKE",
                            "search_project.deleted_at = 0");
            assertThat(delivery).doesNotContain("AND status = ?");
            String material =
                    sql(
                            configuration,
                            method,
                            Map.of("taskType", "MATERIAL", "status", "REJECTED", "keyword", "素材"));
            assertThat(material)
                    .contains("AND status = ?")
                    .doesNotContain("owner_name LIKE", "search_project");
            String unfiltered = sql(configuration, method, Map.of("taskType", "DELIVERY"));
            assertThat(unfiltered).doesNotContain("status IN", "AND status = ?", "search_project");
        }
    }

    @Test
    void shouldIncludeTaskAmNamesWithLegacyFallback() throws Exception {
        assertThat(sql(configuration(), "findTask", Map.of("id", 1L)))
                .contains(
                        "task_am.user_name",
                        "task_am.deleted_at = 0",
                        "delivery.am_user_name",
                        "AS am_names");
        assertThat(
                        configuration()
                                .getResultMap("com.adpulse.main.task.mapper.TaskMapper.taskMap")
                                .getResultMappings())
                .anyMatch(
                        mapping ->
                                "amNames".equals(mapping.getProperty())
                                        && "am_names".equals(mapping.getColumn()));
    }

    @Test
    void shouldOnlyOfferExistingSystemChannels() throws Exception {
        assertThat(
                        sql(
                                configuration(),
                                "findDeliveryAgencyLines",
                                Map.of("keyword", "测试", "offset", 30, "limit", 30)))
                .contains(
                        "FROM pm_agency_line",
                        "deleted_at = 0",
                        "line_name AS name",
                        "CAST(id AS CHAR) AS id");
    }

    @Test
    void shouldPersistItemsAndEnforceConfirmationBoundary() throws Exception {
        var configuration = configuration();
        assertThat(sql(configuration, "findDeliveryDetail", Map.of())).contains("items_ciphertext");
        assertThat(sql(configuration, "updateDeliveryTaskForResubmit", Map.of()))
                .contains("status = 'PENDING_CONFIRMATION'", "version = ?", "creator_id = ?");
        assertThat(sql(configuration, "confirmTask", Map.of()))
                .contains("status = 'PENDING_CONFIRMATION'", "owner_id = ?", "version = ?");
        assertThat(sql(configuration, "withdrawTask", Map.of()))
                .contains(
                        "status = 'PENDING_CONFIRMATION'",
                        "task_type = 'MATERIAL'",
                        "creator_id = ?");
    }

    @Test
    void shouldKeepLeaderAcceptanceIndependentFromAmAssigner() throws Exception {
        var configuration = configuration();
        String leader =
                sql(
                        configuration,
                        "findTasks",
                        Map.of(
                                "scope",
                                "LEADER",
                                "taskType",
                                "DELIVERY",
                                "status",
                                "PENDING_ACCEPTANCE"));
        assertThat(leader).contains("AND owner_id = ?").doesNotContain("AND assigner_id = ?");
        String assigned = sql(configuration, "countAssignedTasks", Map.of());
        assertThat(assigned).contains("assigner_id = ?").doesNotContain("status IN");
    }

    private Configuration configuration() throws Exception {
        var configuration = new Configuration();
        String resource = "mapper/task/TaskMapper.xml";
        try (var stream = getClass().getClassLoader().getResourceAsStream(resource)) {
            new XMLMapperBuilder(stream, configuration, resource, configuration.getSqlFragments())
                    .parse();
        }
        return configuration;
    }

    private String sql(Configuration configuration, String method, Map<String, Object> values) {
        return configuration
                .getMappedStatement(TaskMapper.class.getName() + "." + method)
                .getBoundSql(values)
                .getSql()
                .replaceAll("\\s+", " ");
    }
}
