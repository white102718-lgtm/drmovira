package com.adpulse.main.channel.doris;

import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

/** 隔离 Doris 与业务 MySQL 的只读连接池。 */
@Configuration
@EnableConfigurationProperties(DorisProperties.class)
public class DorisDataSourceConfig {

    /** 创建不参与 MyBatis 自动配置的 Doris 只读客户端。 */
    @Bean(destroyMethod = "close")
    @ConditionalOnProperty(prefix = "adpulse.doris", name = "enabled", havingValue = "true")
    public DorisJdbcClient dorisJdbcClient(DorisProperties properties) {
        return new DorisJdbcClient(properties);
    }
}
