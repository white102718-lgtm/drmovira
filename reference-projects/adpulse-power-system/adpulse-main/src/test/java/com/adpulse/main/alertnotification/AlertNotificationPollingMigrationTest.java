package com.adpulse.main.alertnotification;

import static org.assertj.core.api.Assertions.assertThat;

import java.io.InputStream;
import java.nio.charset.StandardCharsets;
import org.junit.jupiter.api.Test;

/** 限额通知改为固定时间窗口轮询后的数据库迁移契约测试。 */
class AlertNotificationPollingMigrationTest {
    @Test
    void shouldAddPollingConfigAndRemoveCursorTable() throws Exception {
        String sql = resource("db/migration/V53__configure_limit_alert_polling.sql");

        assertThat(sql)
                .contains(
                        "limit_poll_interval_minutes",
                        "DEFAULT 15",
                        "limit_change_enabled_at",
                        "DROP TABLE IF EXISTS ad_alert_poll_cursor");
    }

    private String resource(String path) throws Exception {
        try (InputStream stream = getClass().getClassLoader().getResourceAsStream(path)) {
            assertThat(stream).as(path).isNotNull();
            return new String(stream.readAllBytes(), StandardCharsets.UTF_8);
        }
    }
}
