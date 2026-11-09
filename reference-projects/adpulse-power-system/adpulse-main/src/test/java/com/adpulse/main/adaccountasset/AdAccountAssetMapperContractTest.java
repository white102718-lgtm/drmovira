package com.adpulse.main.adaccountasset;

import static org.assertj.core.api.Assertions.assertThat;

import java.io.ByteArrayInputStream;
import java.io.InputStream;
import java.nio.charset.StandardCharsets;
import org.apache.ibatis.builder.xml.XMLMapperBuilder;
import org.apache.ibatis.session.Configuration;
import org.junit.jupiter.api.Test;

/** 广告账户资产信息主表 Mapper XML 契约测试。 */
class AdAccountAssetMapperContractTest {
    @Test
    void shouldParseMapperAndExposeMainTableStatements() throws Exception {
        String resource = "mapper/adaccountasset/AdAccountAssetMapper.xml";
        try (InputStream stream = getClass().getClassLoader().getResourceAsStream(resource)) {
            assertThat(stream).isNotNull();
            byte[] content = stream.readAllBytes();
            Configuration configuration = new Configuration();
            try (InputStream mapperStream = new ByteArrayInputStream(content)) {
                new XMLMapperBuilder(
                                mapperStream,
                                configuration,
                                resource,
                                configuration.getSqlFragments())
                        .parse();
            }

            assertThat(configuration.hasStatement(statement("countEnabledDictionaryValue")))
                    .isTrue();
            assertThat(configuration.hasStatement(statement("findByAccountIds"))).isTrue();
            assertThat(configuration.hasStatement(statement("findByAccountId"))).isTrue();
            assertThat(configuration.hasStatement(statement("findPage"))).isTrue();
            assertThat(configuration.hasStatement(statement("countPage"))).isTrue();
            assertThat(configuration.hasStatement(statement("upsert"))).isTrue();
            assertThat(configuration.hasStatement(statement("updateInventoryStatus"))).isTrue();

            String mapperXml = new String(content, StandardCharsets.UTF_8);
            assertThat(mapperXml)
                    .contains("type.status = 1")
                    .contains("type.deleted_at = 0")
                    .contains("item.status = 1")
                    .contains("item.deleted_at = 0")
                    .contains("collection=\"filter.accountIds\"")
                    .contains("account_id LIKE CONCAT('%', #{accountId}, '%')")
                    .contains("account_status IN")
                    .contains("collection=\"filter.accountStatuses\"")
                    .contains("collection=\"filter.accountTypes\"")
                    .contains("remark = VALUES(remark)")
                    .contains("COALESCE(inventory_status, 'AVAILABLE') IN")
                    .contains("collection=\"filter.inventoryStatuses\"")
                    .contains("FROM ad_account_asset_assignment usage_assignment")
                    .contains("JOIN sys_user usage_user")
                    .contains("collection=\"filter.usageDepartments\"")
                    .contains("department.dept_name LIKE CONCAT('%', #{usageDepartment}, '%')")
                    .doesNotContain("parent_department");
        }
    }

    @Test
    void shouldOrderUserVisibleListsByNewestCreationTime() throws Exception {
        String mapperXml = mapperXml();

        for (String statementId :
                new String[] {
                    "findByAccountIds", "findAll", "findPage", "findByIds", "findByChannelName"
                }) {
            assertThat(statement(mapperXml, statementId))
                    .contains("ORDER BY created_at DESC, id DESC");
        }
    }

    @Test
    void shouldClearDeliveryDateOnlyWhenAssetIsNotManuallyLocked() throws Exception {
        String resource = "mapper/adaccountasset/AdAccountAssetMapper.xml";
        try (InputStream stream = getClass().getClassLoader().getResourceAsStream(resource)) {
            assertThat(stream).isNotNull();
            String mapper = new String(stream.readAllBytes(), StandardCharsets.UTF_8);

            assertThat(mapper)
                    .contains(
                            "delivery_date = IF(is_manually_updated = 0, VALUES(delivery_date), delivery_date)");
        }
    }

    private String statement(String id) {
        return AdAccountAssetMapper.class.getName() + "." + id;
    }

    private String statement(String mapperXml, String id) {
        int statementStart = mapperXml.indexOf("<select id=\"" + id + "\"");
        int statementEnd = mapperXml.indexOf("</select>", statementStart);
        assertThat(statementStart).isGreaterThanOrEqualTo(0);
        assertThat(statementEnd).isGreaterThan(statementStart);
        return mapperXml.substring(statementStart, statementEnd);
    }

    private String mapperXml() throws Exception {
        String resource = "mapper/adaccountasset/AdAccountAssetMapper.xml";
        try (InputStream stream = getClass().getClassLoader().getResourceAsStream(resource)) {
            assertThat(stream).isNotNull();
            return new String(stream.readAllBytes(), StandardCharsets.UTF_8);
        }
    }
}
