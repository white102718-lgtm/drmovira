package com.adpulse.system.asset.mapper;

import static org.assertj.core.api.Assertions.assertThat;

import java.nio.charset.StandardCharsets;
import org.junit.jupiter.api.Test;

/** 动态审批列表关联数据的批量查询契约测试。 */
class DynamicAssetFlowMapperContractTest {

    @Test
    void shouldBatchLoadApprovalLogsAndAllocatedAssets() throws Exception {
        String xml = mapperXml();

        assertThat(statement(xml, "findApprovalLogsByApplicationIds"))
                .contains("application_id applicationId")
                .contains("collection=\"applicationIds\"")
                .contains("ORDER BY application_id, id");
        assertThat(statement(xml, "findAllocatedAssetsByApplicationIds"))
                .contains("application_id applicationId")
                .contains("collection=\"applicationIds\"")
                .contains("AND deleted_at = 0")
                .contains("ORDER BY application_id, id");
    }

    @Test
    void shouldPersistAndLoadRequesterDepartmentSnapshot() throws Exception {
        String xml = mapperXml();

        assertThat(insertStatement(xml, "insertApplication"))
                .contains("department_id, department_name")
                .contains("#{application.departmentId}")
                .contains("#{application.departmentName}");
        assertThat(statement(xml, "findApplications"))
                .contains("department_id departmentId")
                .contains("department_name departmentName")
                .contains("form_data formData");
        assertThat(statement(xml, "findProcessedApplications"))
                .contains("a.department_id departmentId")
                .contains("a.department_name departmentName")
                .contains("a.form_data formData");
    }

    @Test
    void shouldResolveOnlyDirectDepartmentMembers() throws Exception {
        String xml = mapperXml();

        assertThat(statement(xml, "findActiveDepartmentMemberIds"))
                .contains("u.primary_department_id IN")
                .contains("collection=\"departmentIds\"")
                .doesNotContain("d.path");
    }

    @Test
    void shouldFilterAllQueuesBeforeStableDatabasePagination() throws Exception {
        String xml = mapperXml();

        assertThat(xml)
                .contains("query.queue == 'pending'")
                .contains("query.queue == 'handling'")
                .contains("query.queue == 'processed'")
                .contains("query.queue == 'copied'")
                .contains("a.requester_id = #{query.userId}")
                .contains("ORDER BY a.created_at DESC, a.id DESC")
                .contains("LIMIT #{query.pageSize} OFFSET #{query.offset}");
    }

    @Test
    void shouldUseStablePrincipalsAndSubmissionDepartmentSnapshot() throws Exception {
        String xml = mapperXml();

        assertThat(xml)
                .contains("JOIN sys_user_role user_role")
                .contains("role_principal.role_id")
                .contains("'$._ccUserIds'")
                .contains("'$._requesterDepartmentId'")
                .contains("'$._requesterDepartmentName'")
                .contains("requester.primary_department_id");
    }

    @Test
    void shouldResolvePendingUsersRolesAndDirectDepartmentMembers() throws Exception {
        String pendingPrincipal = sqlFragment(mapperXml(), "approvalPendingPrincipalExpression");

        assertThat(pendingPrincipal)
                .contains(") = 'USERS'")
                .contains(") = 'ROLES'")
                .contains(") = 'DEPARTMENTS'")
                .contains("].departmentIds")
                .contains("JOIN sys_department pending_department")
                .contains("JOIN sys_user pending_department_user")
                .contains("pending_department_user.primary_department_id = pending_department.id")
                .contains("pending_department_user.id = #{query.userId}")
                .contains("pending_department_user.status = 1")
                .contains("pending_department_user.deleted_at = 0")
                .doesNotContain("!= 'ROLES'")
                .doesNotContain(".path");
    }

    @Test
    void approvalPageShouldNotSelectDetailPayloads() throws Exception {
        String pageSelect = statement(mapperXml(), "findApprovalPage");

        assertThat(pageSelect)
                .doesNotContain("form_data formData")
                .doesNotContain("form_schema_snapshot")
                .doesNotContain("nodes_snapshot nodes")
                .doesNotContain("media_asset_approval_log");
    }

    @Test
    void shouldResolveApprovalCcUsersByStableIdsIncludingDisabledUsers() throws Exception {
        String ccUserSelect = statement(mapperXml(), "findApprovalCcUsersByIds");

        assertThat(ccUserSelect)
                .contains("collection=\"ids\"")
                .contains("COALESCE(")
                .contains("status")
                .contains("AND deleted_at = 0")
                .doesNotContain("status = 1");
    }

    @Test
    void shouldAssignExclusiveAssetsOnlyWhileAvailable() throws Exception {
        String xml = mapperXml();

        assertThat(updateStatement(xml, "assignAsset")).contains("AND status = 'AVAILABLE'");
        assertThat(updateStatement(xml, "assignPixelAsset")).contains("AND status = 'AVAILABLE'");
    }

    private String mapperXml() throws Exception {
        try (var stream =
                getClass()
                        .getClassLoader()
                        .getResourceAsStream("mapper/asset/DynamicAssetFlowMapper.xml")) {
            assertThat(stream).isNotNull();
            return new String(stream.readAllBytes(), StandardCharsets.UTF_8);
        }
    }

    private String statement(String xml, String id) {
        int statementStart = xml.indexOf("<select id=\"" + id + "\"");
        int statementEnd = xml.indexOf("</select>", statementStart);
        assertThat(statementStart).isGreaterThanOrEqualTo(0);
        assertThat(statementEnd).isGreaterThan(statementStart);
        return xml.substring(statementStart, statementEnd);
    }

    private String insertStatement(String xml, String id) {
        int statementStart = xml.indexOf("<insert id=\"" + id + "\"");
        int statementEnd = xml.indexOf("</insert>", statementStart);
        assertThat(statementStart).isGreaterThanOrEqualTo(0);
        assertThat(statementEnd).isGreaterThan(statementStart);
        return xml.substring(statementStart, statementEnd);
    }

    private String sqlFragment(String xml, String id) {
        int statementStart = xml.indexOf("<sql id=\"" + id + "\"");
        int statementEnd = xml.indexOf("</sql>", statementStart);
        assertThat(statementStart).isGreaterThanOrEqualTo(0);
        assertThat(statementEnd).isGreaterThan(statementStart);
        return xml.substring(statementStart, statementEnd);
    }

    private String updateStatement(String xml, String id) {
        int statementStart = xml.indexOf("<update id=\"" + id + "\"");
        int statementEnd = xml.indexOf("</update>", statementStart);
        assertThat(statementStart).isGreaterThanOrEqualTo(0);
        assertThat(statementEnd).isGreaterThan(statementStart);
        return xml.substring(statementStart, statementEnd);
    }
}
