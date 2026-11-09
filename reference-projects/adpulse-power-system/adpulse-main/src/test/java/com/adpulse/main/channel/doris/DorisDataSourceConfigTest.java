package com.adpulse.main.channel.doris;

import static org.assertj.core.api.Assertions.assertThat;

import javax.sql.DataSource;
import org.junit.jupiter.api.Test;
import org.springframework.boot.autoconfigure.AutoConfigurations;
import org.springframework.boot.autoconfigure.jdbc.DataSourceAutoConfiguration;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;

class DorisDataSourceConfigTest {

    private final ApplicationContextRunner contextRunner =
            new ApplicationContextRunner()
                    .withConfiguration(AutoConfigurations.of(DataSourceAutoConfiguration.class))
                    .withUserConfiguration(DorisDataSourceConfig.class)
                    .withPropertyValues(
                            "spring.datasource.url=jdbc:mysql://localhost:3306/adpulse_system",
                            "spring.datasource.username=adpulse",
                            "spring.datasource.password=test",
                            "adpulse.doris.enabled=true",
                            "adpulse.doris.url=jdbc:mysql://localhost:9030/ad",
                            "adpulse.doris.username=doris",
                            "adpulse.doris.password=test",
                            "adpulse.doris.mysql-catalog=mysql_adpulse_system",
                            "adpulse.doris.mysql-database=adpulse_system",
                            "adpulse.doris.spend-catalog=internal",
                            "adpulse.doris.spend-database=ad");

    @Test
    void shouldKeepMysqlAsTheOnlySpringDataSourceWhenDorisIsEnabled() {
        contextRunner.run(
                context -> {
                    assertThat(context).hasSingleBean(DataSource.class);
                    assertThat(context).hasSingleBean(DorisJdbcClient.class);
                    assertThat(context.getBean(DataSource.class))
                            .isNotSameAs(context.getBean(DorisJdbcClient.class));
                });
    }
}
