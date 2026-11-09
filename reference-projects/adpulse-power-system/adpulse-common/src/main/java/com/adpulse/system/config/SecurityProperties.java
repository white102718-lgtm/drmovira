package com.adpulse.system.config;

import java.time.Duration;
import org.springframework.boot.context.properties.ConfigurationProperties;

/** 安全与服务端会话配置。 */
@ConfigurationProperties(prefix = "adpulse.security")
public record SecurityProperties(String jwtSecret, String jwtIssuer, Duration sessionTtl) {}
