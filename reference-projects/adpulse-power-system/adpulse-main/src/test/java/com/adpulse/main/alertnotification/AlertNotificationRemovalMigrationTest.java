package com.adpulse.main.alertnotification;

import static org.assertj.core.api.Assertions.assertThat;

import com.adpulse.main.alertnotification.dto.AlertRequests.ConfigSave;
import java.io.InputStream;
import java.nio.charset.StandardCharsets;
import java.util.Arrays;
import org.junit.jupiter.api.Test;

/** 消耗上限预警下线后的接口与数据清理契约测试。 */
class AlertNotificationRemovalMigrationTest {
    @Test
    void shouldRemoveSpendFieldsFromSettingsContract() {
        assertThat(
                        Arrays.stream(ConfigSave.class.getRecordComponents())
                                .map(component -> component.getName())
                                .toList())
                .contains("enabled", "banEnabled", "limitChangeEnabled", "recipients")
                .noneMatch(name -> name.startsWith("spend"));
    }

    @Test
    void shouldDeleteSpendDeliveriesBeforeNotificationsAndDropConfigColumns() throws Exception {
        String sql = resource("db/migration/V48__remove_spend_threshold_alert.sql");
        int deleteDeliveries = sql.indexOf("DELETE delivery");
        int deleteNotifications = sql.indexOf("DELETE FROM ad_alert_notification");
        int dropColumns = sql.indexOf("ALTER TABLE ad_alert_config");

        assertThat(deleteDeliveries).isGreaterThanOrEqualTo(0);
        assertThat(deleteNotifications).isGreaterThan(deleteDeliveries);
        assertThat(dropColumns).isGreaterThan(deleteNotifications);
        assertThat(sql)
                .contains(
                        "DROP COLUMN spend_enabled",
                        "DROP COLUMN spend_upper_limit",
                        "DROP COLUMN spend_ratio",
                        "DROP COLUMN spend_window_value",
                        "DROP COLUMN spend_window_unit");
    }

    private String resource(String path) throws Exception {
        try (InputStream stream = getClass().getClassLoader().getResourceAsStream(path)) {
            assertThat(stream).as(path).isNotNull();
            return new String(stream.readAllBytes(), StandardCharsets.UTF_8);
        }
    }
}
