package com.adpulse.system.file.config;

import com.adpulse.system.file.storage.FileStorage;
import com.adpulse.system.file.storage.MinioFileStorage;
import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

/** 文件存储配置入口。 */
@Configuration
@EnableConfigurationProperties(FileStorageProperties.class)
public class FileStorageConfig {

    /**
     * 注册MinIO文件存储，供文件上传、下载与删除服务使用。
     *
     * @param properties 文件存储配置
     * @return 文件存储实现
     */
    @Bean
    public FileStorage fileStorage(FileStorageProperties properties) {
        return new MinioFileStorage(properties);
    }
}
