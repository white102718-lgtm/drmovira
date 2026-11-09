package com.adpulse.system.asset.mapper;

import static org.assertj.core.api.Assertions.assertThat;

import java.nio.charset.StandardCharsets;
import org.junit.jupiter.api.Test;

/** 资产单条读取与列表读取的使用人回显字段契约。 */
class AssetMapperContractTest {

    @Test
    void shouldOrderAssetListsByNewestCreationTime() throws Exception {
        assertThat(statement("findAssets"))
                .contains("ORDER BY asset.created_at DESC, asset.id DESC");
    }

    @Test
    void shouldPageImportHistoryAfterFilteringCurrentOperator() throws Exception {
        assertThat(statement("findImportLogsByOperatorId"))
                .contains("WHERE operator_id = #{operatorId}")
                .contains("ORDER BY created_at DESC, id DESC")
                .contains("LIMIT #{pageSize} OFFSET #{offset}");
        assertThat(statement("countImportLogsByOperatorId"))
                .contains("WHERE operator_id = #{operatorId}");
    }

    @Test
    void shouldReturnSharedUsageFieldsWhenReadingOneAsset() throws Exception {
        String findAssetStatement = statement("findAsset");

        assertThat(findAssetStatement)
                .contains("AS usage_user_names")
                .contains("AS usage_user_ids")
                .contains("AS usage_department_names")
                .contains("assignment.asset_id = asset.id")
                .contains("assignment.deleted_at = 0");
    }

    @Test
    void shouldResolveUsageDepartmentsFromUsersCurrentPrimaryDepartments() throws Exception {
        for (String statementId : new String[] {"findAssets", "findAsset"}) {
            assertThat(statement(statementId))
                    .contains("SELECT department.dept_name")
                    .contains("DISTINCT department.dept_name")
                    .doesNotContain("parent_department");
        }
    }

    @Test
    void shouldReadAdAccountSharedUsersFromChannelAccountAssignments() throws Exception {
        for (String statementId : new String[] {"findAssets", "findAsset"}) {
            String statement = statement(statementId);
            int adAccountBranchStart =
                    statement.indexOf("WHEN asset.asset_type = 'AD_ACCOUNT' THEN (");
            int adAccountBranchEnd =
                    statement.indexOf("END AS usage_user_names", adAccountBranchStart);

            assertThat(adAccountBranchStart).isGreaterThanOrEqualTo(0);
            assertThat(adAccountBranchEnd).isGreaterThan(adAccountBranchStart);
            assertThat(statement.substring(adAccountBranchStart, adAccountBranchEnd))
                    .contains("FROM media_channel_account_assignment assignment")
                    .contains("assignment.account_id = asset.asset_code")
                    .contains("channel_account.operator_name")
                    .doesNotContain("FROM media_asset_user_assignment assignment");
        }
    }

    @Test
    void shouldReleaseDepartingUsersWithoutDiscardingOtherSharedUsers() throws Exception {
        String xml = mapperXml();

        assertThat(statement(xml, "refreshChannelAccountUsageForDepartingUser"))
                .contains("assignment.assignee_id != #{userId}")
                .contains("usage_status = CASE")
                .contains("operator_id = (");
        assertThat(statement(xml, "deactivateChannelAccountAssignmentsForUser"))
                .contains("UPDATE ad_account_asset_assignment")
                .contains("assignment_status = 'RELEASED'")
                .contains("WHERE user_id = #{userId}");
        assertThat(statement(xml, "deactivatePixelUsageAssignmentsForUser"))
                .contains("WHERE user_id = #{userId} AND deleted_at = 0");
        assertThat(statement(xml, "releaseAssetsAssignedToUser"))
                .contains("ELSE 'AVAILABLE'")
                .contains("asset.asset_type = 'PIXEL'")
                .contains("asset.asset_type = 'AD_ACCOUNT'");
    }

    private String statement(String id) throws Exception {
        return statement(mapperXml(), id);
    }

    private String mapperXml() throws Exception {
        try (var stream =
                getClass().getClassLoader().getResourceAsStream("mapper/asset/AssetMapper.xml")) {
            assertThat(stream).isNotNull();
            return new String(stream.readAllBytes(), StandardCharsets.UTF_8);
        }
    }

    private String statement(String xml, String id) {
        int statementStart = xml.indexOf("<select id=\"" + id + "\"");
        if (statementStart < 0) statementStart = xml.indexOf("<update id=\"" + id + "\"");
        int statementEnd = xml.indexOf("</select>", statementStart);
        if (statementEnd < 0) statementEnd = xml.indexOf("</update>", statementStart);
        assertThat(statementStart).isGreaterThanOrEqualTo(0);
        assertThat(statementEnd).isGreaterThan(statementStart);
        return xml.substring(statementStart, statementEnd);
    }
}
