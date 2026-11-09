package com.adpulse.main.migration;

import static org.assertj.core.api.Assertions.assertThatThrownBy;

import org.junit.jupiter.api.Test;

/** 来源配置错误应在连接数据库前明确报告，不能暴露凭据。 */
class LegacyAssetReaderTest {
    @Test
    void missingSourceUrlIsReportedBeforeConstructingConnectionPool() {
        var properties = new AssetMigrationProperties();
        properties.setSourceUrl("");
        properties.setSourceUsername("");
        properties.setSourcePassword("");
        var reader = new LegacyAssetReader(properties);
        assertThatThrownBy(reader::read)
                .isInstanceOf(AssetMigrationService.Conflict.class)
                .hasMessageContaining("ASSET_MIGRATION_SOURCE_URL");
    }

    @Test
    void distinguishesMissingUsernamePasswordAndInvalidUrl() {
        var properties = new AssetMigrationProperties();
        properties.setSourceUrl("jdbc:mysql://localhost/legacy");
        var reader = new LegacyAssetReader(properties);
        assertThatThrownBy(reader::read).hasMessageContaining("ASSET_MIGRATION_SOURCE_USERNAME");
        properties.setSourceUsername("read-only-user");
        assertThatThrownBy(reader::read).hasMessageContaining("ASSET_MIGRATION_SOURCE_PASSWORD");
        properties.setSourcePassword("test-only-placeholder");
        properties.setSourceUrl("invalid-url-with-private-data");
        assertThatThrownBy(reader::read)
                .hasMessageContaining("jdbc:mysql://")
                .hasMessageNotContaining("private-data");
    }
}
