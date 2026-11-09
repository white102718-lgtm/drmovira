package com.adpulse.main.migration;

import static org.assertj.core.api.Assertions.assertThat;

import com.adpulse.main.migration.AssetMigrationModels.Item;
import java.io.InputStream;
import java.util.List;
import java.util.Map;
import org.apache.ibatis.builder.xml.XMLMapperBuilder;
import org.apache.ibatis.session.Configuration;
import org.junit.jupiter.api.Test;

class AssetMigrationMapperTest {
    @Test
    void loadsMappersAndEnforcesWhitelistedWritesAndUnambiguousLockedReads() throws Exception {
        Configuration config = new Configuration();
        for (String name : List.of("AssetMigrationMapper", "LegacyAssetMapper")) {
            String resource = "mapper/migration/" + name + ".xml";
            try (InputStream stream = getClass().getClassLoader().getResourceAsStream(resource)) {
                new XMLMapperBuilder(stream, config, resource, config.getSqlFragments()).parse();
            }
        }
        String prefix = AssetMigrationMapper.class.getName() + ".";
        String testLedger =
                config.getMappedStatement(prefix + "channelLedger")
                        .getBoundSql(
                                Map.of(
                                        "environment",
                                        "TEST",
                                        "batchKey",
                                        "mpower-prod-to-test-channels-v1"))
                        .getSql();
        String prodLedger =
                config.getMappedStatement(prefix + "channelLedger")
                        .getBoundSql(
                                Map.of(
                                        "environment",
                                        "PRODUCTION",
                                        "batchKey",
                                        "mpower-prod-to-prod-channels-v1"))
                        .getSql();
        assertThat(testLedger)
                .contains(
                        "mig_channel_prod_test_batch",
                        "batch_key = ?",
                        "FOR SHARE",
                        "ORDER BY item.ordinal")
                .doesNotContain("mig_channel_prod_prod_batch");
        assertThat(prodLedger)
                .contains("mig_channel_prod_prod_batch")
                .doesNotContain("mig_channel_prod_test_batch");
        String invalid =
                config.getMappedStatement(prefix + "channelLedger")
                        .getBoundSql(Map.of("environment", "TEST; DROP TABLE x", "batchKey", "x"))
                        .getSql();
        assertThat(invalid).doesNotContain("DROP TABLE").contains("mig_asset_invalid_environment");
        String reads =
                config.getMappedStatement(prefix + "assets")
                        .getBoundSql(Map.of("accountIds", List.of("123"), "lock", true))
                        .getSql();
        assertThat(reads)
                .contains("FOR UPDATE", "deleted_at = 0")
                .doesNotContain("LIMIT 1", "card_number", "managed_bm");
        Item item = new Item();
        item.setId(1);
        item.setTargetId(99L);
        for (String statement : List.of("updateAssets", "insertAssets")) {
            String sql =
                    config.getMappedStatement(prefix + statement)
                            .getBoundSql(Map.of("items", List.of(item), "operatorId", 7L))
                            .getSql();
            assertThat(sql)
                    .contains("channel_id", "channel_name", "account_type", "account_attribute")
                    .doesNotContain(
                            "ON DUPLICATE KEY",
                            "managed_bm",
                            "card_number",
                            "account_status",
                            "is_manually_updated =",
                            "inventory_status =",
                            "account_name =");
        }
        String source =
                config.getMappedStatement(LegacyAssetMapper.class.getName() + ".snapshot")
                        .getBoundSql(null)
                        .getSql();
        assertThat(source)
                .contains(
                        "fb_account_id AS accountId",
                        "account_id AS sourceId",
                        "whitelist_type AS attribute")
                .doesNotContain("SELECT *");
    }
}
