package com.adpulse.main.migration;

import com.fasterxml.jackson.databind.ObjectMapper;
import org.springframework.beans.factory.ObjectProvider;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.transaction.PlatformTransactionManager;

/** 迁移功能按需开启，私有来源连接池不参与主库 Bean 自动装配。 */
@Configuration(proxyBeanMethods = false)
@ConditionalOnProperty(name = "adpulse.asset-migration.enabled", havingValue = "true")
@EnableConfigurationProperties(AssetMigrationProperties.class)
public class AssetMigrationConfiguration {
    @Bean
    LegacyAssetReader legacyAssetReader(AssetMigrationProperties properties) {
        properties.validateEnvironment();
        return new LegacyAssetReader(properties);
    }

    @Bean
    ChannelMigrationMappingResolver channelMigrationMappingResolver(
            AssetMigrationMapper mapper,
            AssetMigrationProperties properties,
            ObjectMapper json,
            ObjectProvider<StringRedisTemplate> redis) {
        return new ChannelMigrationMappingResolver(
                mapper, properties, json, redis.getIfAvailable());
    }

    @Bean
    AssetMigrationService assetMigrationService(
            AssetMigrationMapper mapper,
            LegacyAssetReader reader,
            AssetMigrationProperties properties,
            ObjectMapper json,
            PlatformTransactionManager manager,
            ChannelMigrationMappingResolver mappings) {
        return new AssetMigrationService(mapper, reader, properties, json, manager, mappings);
    }

    @Bean
    ChannelIncrementService channelIncrementService(
            AssetMigrationMapper mapper,
            LegacyAssetReader reader,
            AssetMigrationProperties properties,
            ChannelMigrationMappingResolver mappings,
            ObjectMapper json) {
        return new ChannelIncrementService(mapper, reader, properties, mappings, json);
    }

    @Bean
    AssetMigrationWorker assetMigrationWorker(AssetMigrationService service) {
        return new AssetMigrationWorker(service);
    }
}
