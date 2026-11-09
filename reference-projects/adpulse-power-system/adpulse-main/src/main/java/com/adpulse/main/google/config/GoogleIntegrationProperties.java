package com.adpulse.main.google.config;

import org.springframework.boot.context.properties.ConfigurationProperties;

/** Google OAuth与Sheets集成配置。 */
@ConfigurationProperties(prefix = "adpulse.google")
public record GoogleIntegrationProperties(
        String clientId, String clientSecret, String redirectUri) {}
