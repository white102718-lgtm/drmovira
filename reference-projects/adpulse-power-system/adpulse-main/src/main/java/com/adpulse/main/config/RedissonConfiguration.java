package com.adpulse.main.config;

import org.redisson.Redisson;
import org.redisson.api.RedissonClient;
import org.redisson.config.Config;
import org.redisson.config.SingleServerConfig;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.util.StringUtils;

/** 为业务分布式锁提供独立 Redisson 客户端，不替换现有 Spring Data Redis 连接。 */
@Configuration(proxyBeanMethods = false)
public class RedissonConfiguration {
    @Bean(destroyMethod = "shutdown")
    RedissonClient redissonClient(
            @Value("${spring.data.redis.host:localhost}") String host,
            @Value("${spring.data.redis.port:6379}") int port,
            @Value("${spring.data.redis.username:}") String username,
            @Value("${spring.data.redis.password:}") String password,
            @Value("${spring.data.redis.database:0}") int database,
            @Value("${spring.data.redis.ssl.enabled:false}") boolean sslEnabled) {
        Config config = new Config();
        SingleServerConfig server =
                config.useSingleServer()
                        .setAddress((sslEnabled ? "rediss://" : "redis://") + host + ":" + port)
                        .setDatabase(database);
        if (StringUtils.hasText(username)) {
            server.setUsername(username);
        }
        if (StringUtils.hasText(password)) {
            server.setPassword(password);
        }
        return Redisson.create(config);
    }
}
