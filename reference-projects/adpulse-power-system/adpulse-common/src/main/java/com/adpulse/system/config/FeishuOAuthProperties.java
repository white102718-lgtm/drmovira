package com.adpulse.system.config;

import java.time.Duration;
import org.springframework.boot.context.properties.ConfigurationProperties;

/** 飞书网页扫码登录配置。 */
@ConfigurationProperties(prefix = "adpulse.feishu.oauth")
public record FeishuOAuthProperties(String redirectUri, Duration stateTtl) {

    /** 未显式配置时，OAuth state 与飞书授权码统一按五分钟有效期处理。 */
    public FeishuOAuthProperties {
        if (stateTtl == null) {
            stateTtl = Duration.ofMinutes(5);
        }
    }
}
