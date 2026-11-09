package com.adpulse.system.config;

import org.springframework.boot.context.properties.ConfigurationProperties;

/** 首次启动管理员配置；仅空库且显式启用时生效。 */
@ConfigurationProperties(prefix = "adpulse.bootstrap-admin")
public record BootstrapAdminProperties(
        boolean enabled, String username, String phone, String password, String displayName) {}
