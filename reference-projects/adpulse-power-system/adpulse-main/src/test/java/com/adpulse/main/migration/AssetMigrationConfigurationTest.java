package com.adpulse.main.migration;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.Mockito.mock;

import com.fasterxml.jackson.databind.ObjectMapper;
import javax.sql.DataSource;
import org.apache.ibatis.session.SqlSessionFactory;
import org.junit.jupiter.api.Test;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;
import org.springframework.transaction.PlatformTransactionManager;

class AssetMigrationConfigurationTest {
    ApplicationContextRunner context =
            new ApplicationContextRunner()
                    .withUserConfiguration(AssetMigrationConfiguration.class)
                    .withBean(ObjectMapper.class, ObjectMapper::new)
                    .withBean(AssetMigrationMapper.class, () -> mock(AssetMigrationMapper.class))
                    .withBean(
                            PlatformTransactionManager.class,
                            () -> mock(PlatformTransactionManager.class));

    @Test
    void disabledByDefaultCreatesNoReaderOrWorker() {
        context.run(
                application -> {
                    assertThat(application).doesNotHaveBean(LegacyAssetReader.class);
                    assertThat(application).doesNotHaveBean(AssetMigrationWorker.class);
                });
    }

    @Test
    void enablingMigrationDoesNotPublishAnAlternativeBusinessDatasourceOrFactory() {
        context.withPropertyValues(
                        "adpulse.asset-migration.enabled=true",
                        "adpulse.asset-migration.target-environment=PRODUCTION",
                        "adpulse.asset-migration.target-uuid=17c4f6b3-a2cc-11f1-99a8-ea697aa9ac3a")
                .run(
                        application -> {
                            assertThat(application).hasSingleBean(LegacyAssetReader.class);
                            assertThat(application).hasSingleBean(AssetMigrationWorker.class);
                            assertThat(application).doesNotHaveBean(DataSource.class);
                            assertThat(application).doesNotHaveBean(SqlSessionFactory.class);
                        });
    }

    @Test
    void enablingWithoutAnExplicitEnvironmentFailsClosed() {
        context.withPropertyValues("adpulse.asset-migration.enabled=true")
                .run(application -> assertThat(application).hasFailed());
    }
}
