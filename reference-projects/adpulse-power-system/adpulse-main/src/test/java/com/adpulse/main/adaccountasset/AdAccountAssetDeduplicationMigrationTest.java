package com.adpulse.main.adaccountasset;

import static org.assertj.core.api.Assertions.assertThat;

import java.io.InputStream;
import java.nio.charset.StandardCharsets;
import org.junit.jupiter.api.Test;

/** 广告账户资产去重迁移的结构契约测试。 */
class AdAccountAssetDeduplicationMigrationTest {

    @Test
    void shouldConsolidateDuplicateAssetsBeforeRestoringAccountIdUniqueness() throws Exception {
        String resource = "db/migration/V43__deduplicate_ad_account_assets_by_account_id.sql";
        try (InputStream stream = getClass().getClassLoader().getResourceAsStream(resource)) {
            assertThat(stream).isNotNull();
            String migration = new String(stream.readAllBytes(), StandardCharsets.UTF_8);

            assertThat(migration)
                    .contains("INSERT INTO ad_account_asset_assignment")
                    .contains("DELETE assignment")
                    .contains("DELETE duplicate_asset")
                    .contains("DROP INDEX uk_ad_account_asset_identity_deleted")
                    .contains("ADD UNIQUE KEY uk_ad_account_asset_account_deleted")
                    .contains("(account_id, deleted_at)");
        }
    }
}
