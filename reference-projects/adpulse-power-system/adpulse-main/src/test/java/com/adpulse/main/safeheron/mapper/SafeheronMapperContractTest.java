package com.adpulse.main.safeheron.mapper;

import static org.assertj.core.api.Assertions.assertThat;

import java.io.InputStream;
import org.apache.ibatis.builder.xml.XMLMapperBuilder;
import org.apache.ibatis.session.Configuration;
import org.junit.jupiter.api.Test;

/** Safeheron Mapper XML与主要查询契约测试。 */
class SafeheronMapperContractTest {

    @Test
    void shouldParseMapperAndExposeManagementStatements() throws Exception {
        String resource = "mapper/safeheron/SafeheronMapper.xml";
        try (InputStream stream = getClass().getClassLoader().getResourceAsStream(resource)) {
            assertThat(stream).isNotNull();
            Configuration configuration = new Configuration();
            new XMLMapperBuilder(stream, configuration, resource, configuration.getSqlFragments())
                    .parse();

            assertThat(configuration.hasStatement(statement("findRules"))).isTrue();
            assertThat(configuration.hasStatement(statement("findWallets"))).isTrue();
            assertThat(configuration.hasStatement(statement("findTeams"))).isTrue();
            assertThat(configuration.hasStatement(statement("findRecords"))).isTrue();
            assertThat(configuration.hasStatement(statement("summarizeRecords"))).isTrue();
        }
    }

    private String statement(String id) {
        return SafeheronMapper.class.getName() + "." + id;
    }
}
