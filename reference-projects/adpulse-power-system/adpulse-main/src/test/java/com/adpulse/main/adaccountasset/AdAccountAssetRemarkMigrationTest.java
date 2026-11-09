package com.adpulse.main.adaccountasset;

import static org.assertj.core.api.Assertions.assertThat;

import java.io.InputStream;
import java.nio.charset.StandardCharsets;
import org.junit.jupiter.api.Test;

/** 广告账户备注字段迁移脚本契约测试。 */
class AdAccountAssetRemarkMigrationTest {
    @Test
    void shouldAddNullableRemarkColumnWithExpectedLength() throws Exception {
        String resource = "db/migration/V46__add_remark_to_ad_account_asset.sql";
        try (InputStream stream = getClass().getClassLoader().getResourceAsStream(resource)) {
            assertThat(stream).isNotNull();
            String migration = new String(stream.readAllBytes(), StandardCharsets.UTF_8);

            assertThat(migration)
                    .contains("ADD COLUMN remark VARCHAR(500) NULL")
                    .contains("广告账户资产人工备注");
        }
    }
}
