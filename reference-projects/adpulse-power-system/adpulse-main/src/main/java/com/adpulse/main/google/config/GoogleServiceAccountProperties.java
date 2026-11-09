package com.adpulse.main.google.config;

import org.springframework.boot.context.properties.ConfigurationProperties;

/** 投放日报Google服务账户凭据配置。 */
@ConfigurationProperties(prefix = "adpulse.google.delivery-service-account")
public record GoogleServiceAccountProperties(String credentialsFile, String credentialsBase64) {}
