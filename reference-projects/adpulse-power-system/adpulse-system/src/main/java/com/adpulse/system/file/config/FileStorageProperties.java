package com.adpulse.system.file.config;

import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.util.unit.DataSize;

/** MinIO文件存储配置。 */
@ConfigurationProperties(prefix = "adpulse.file")
public record FileStorageProperties(
        String rootDirectory,
        DataSize maxSize,
        String endpoint,
        String accessKey,
        String secretKey,
        String bucket) {}
