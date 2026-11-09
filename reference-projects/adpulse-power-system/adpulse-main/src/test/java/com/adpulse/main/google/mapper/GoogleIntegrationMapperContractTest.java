package com.adpulse.main.google.mapper;

import static org.assertj.core.api.Assertions.assertThat;

import java.io.InputStream;
import org.apache.ibatis.builder.xml.XMLMapperBuilder;
import org.apache.ibatis.session.Configuration;
import org.junit.jupiter.api.Test;

/** Google数据集成Mapper XML契约测试。 */
class GoogleIntegrationMapperContractTest {
    @Test
    void shouldParseGoogleIntegrationMapper() throws Exception {
        String resource = "mapper/google/GoogleIntegrationMapper.xml";
        try (InputStream stream = getClass().getClassLoader().getResourceAsStream(resource)) {
            assertThat(stream).isNotNull();
            Configuration configuration = new Configuration();
            new XMLMapperBuilder(stream, configuration, resource, configuration.getSqlFragments())
                    .parse();
            assertThat(configuration.hasStatement(statement("findAccounts"))).isTrue();
            assertThat(configuration.hasStatement(statement("insertMapping"))).isTrue();
            assertThat(configuration.hasStatement(statement("insertSyncJob"))).isTrue();
            assertThat(configuration.hasStatement(statement("findSyncLogs"))).isTrue();
            assertThat(configuration.hasStatement(statement("countSyncLogs"))).isTrue();
        }
    }

    private String statement(String id) {
        return GoogleIntegrationMapper.class.getName() + "." + id;
    }
}
