package com.adpulse.main.channel.doris;

import org.springframework.boot.context.properties.ConfigurationProperties;

/** Doris 渠道账户联合查询数据源配置。 */
@ConfigurationProperties(prefix = "adpulse.doris")
public record DorisProperties(
        boolean enabled,
        String url,
        String username,
        String password,
        String mysqlCatalog,
        String mysqlDatabase,
        String spendCatalog,
        String spendDatabase) {}
