package com.adpulse.main.adaccountasset;

import static org.assertj.core.api.Assertions.assertThat;

import java.io.InputStream;
import java.nio.charset.StandardCharsets;
import org.junit.jupiter.api.Test;

/** 飞书广告账户资料同步字典开关初始化脚本的契约测试。 */
class AdAccountAssetFeishuSyncSwitchMigrationTest {

    @Test
    void shouldSeedEnabledSwitchWithoutOverwritingExistingConfiguration() throws Exception {
        String resource = "db/migration/V44__seed_ad_account_asset_feishu_sync_switch.sql";
        try (InputStream stream = getClass().getClassLoader().getResourceAsStream(resource)) {
            assertThat(stream).isNotNull();
            String migration = new String(stream.readAllBytes(), StandardCharsets.UTF_8);

            assertThat(migration)
                    .contains("'AD_ACCOUNT_ASSET_FEISHU_SYNC'")
                    .contains("'1'")
                    .contains("'开启同步'")
                    .contains("WHERE NOT EXISTS")
                    .contains("item.deleted_at = 0");
        }
    }
}
