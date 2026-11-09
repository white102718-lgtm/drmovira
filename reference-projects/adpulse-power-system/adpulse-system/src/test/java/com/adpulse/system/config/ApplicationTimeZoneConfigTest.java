package com.adpulse.system.config;

import static org.assertj.core.api.Assertions.assertThat;

import java.util.TimeZone;
import org.junit.jupiter.api.Test;

/** 应用业务时区配置测试。 */
class ApplicationTimeZoneConfigTest {

    @Test
    void shouldConfigureShanghaiAsJvmDefaultTimeZone() {
        TimeZone original = TimeZone.getDefault();
        try {
            TimeZone.setDefault(TimeZone.getTimeZone("UTC"));

            new ApplicationTimeZoneConfig().configureDefaultTimeZone();

            assertThat(TimeZone.getDefault().toZoneId())
                    .isEqualTo(ApplicationTimeZoneConfig.BUSINESS_ZONE_ID);
        } finally {
            TimeZone.setDefault(original);
        }
    }
}
