package com.adpulse.system.config;

import jakarta.annotation.PostConstruct;
import java.time.ZoneId;
import java.util.TimeZone;
import org.springframework.context.annotation.Configuration;

/** 统一应用进程使用的业务时区，避免不同部署环境写入不一致的本地时间。 */
@Configuration
public class ApplicationTimeZoneConfig {

    static final ZoneId BUSINESS_ZONE_ID = ZoneId.of("Asia/Shanghai");

    /** 在业务请求执行前将 JVM 默认时区固定为上海时区。 */
    @PostConstruct
    public void configureDefaultTimeZone() {
        TimeZone.setDefault(TimeZone.getTimeZone(BUSINESS_ZONE_ID));
    }
}
