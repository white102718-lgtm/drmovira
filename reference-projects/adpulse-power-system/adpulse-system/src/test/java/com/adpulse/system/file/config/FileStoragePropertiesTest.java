package com.adpulse.system.file.config;

import static org.assertj.core.api.Assertions.assertThat;

import com.adpulse.system.file.storage.FileStorage;
import com.adpulse.system.file.storage.MinioFileStorage;
import org.junit.jupiter.api.Test;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;

/** 文件存储配置绑定测试。 */
class FileStoragePropertiesTest {
    private final ApplicationContextRunner contextRunner =
            new ApplicationContextRunner()
                    .withUserConfiguration(FileStorageConfig.class)
                    .withPropertyValues(
                            "adpulse.file.root-directory=./data/files",
                            "adpulse.file.max-size=100MB",
                            "adpulse.file.endpoint=http://127.0.0.1:9000",
                            "adpulse.file.access-key=minioadmin",
                            "adpulse.file.secret-key=minioadmin",
                            "adpulse.file.bucket=adpulse-files");

    @Test
    void shouldBindMinioPropertiesWithCanonicalRecordConstructor() {
        contextRunner.run(
                context -> {
                    assertThat(context).hasNotFailed();
                    FileStorageProperties properties = context.getBean(FileStorageProperties.class);
                    assertThat(properties.endpoint()).isEqualTo("http://127.0.0.1:9000");
                    assertThat(properties.bucket()).isEqualTo("adpulse-files");
                    assertThat(properties.maxSize().toMegabytes()).isEqualTo(100L);
                    assertThat(context).hasSingleBean(FileStorage.class);
                    assertThat(context.getBean(FileStorage.class))
                            .isInstanceOf(MinioFileStorage.class);
                });
    }
}
