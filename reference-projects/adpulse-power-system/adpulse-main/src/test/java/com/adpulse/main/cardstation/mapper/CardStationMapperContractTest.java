package com.adpulse.main.cardstation.mapper;

import static org.assertj.core.api.Assertions.assertThat;

import java.io.InputStream;
import org.apache.ibatis.builder.xml.XMLMapperBuilder;
import org.apache.ibatis.session.Configuration;
import org.junit.jupiter.api.Test;

/** 卡台Mapper XML主要语句契约测试。 */
class CardStationMapperContractTest {
    @Test
    void shouldParseCardStationMapper() throws Exception {
        String resource = "mapper/cardstation/CardStationMapper.xml";
        try (InputStream stream = getClass().getClassLoader().getResourceAsStream(resource)) {
            assertThat(stream).isNotNull();
            Configuration configuration = new Configuration();
            new XMLMapperBuilder(stream, configuration, resource, configuration.getSqlFragments())
                    .parse();
            assertThat(configuration.hasStatement(statement("findCards"))).isTrue();
            assertThat(configuration.hasStatement(statement("insertSyncJob"))).isTrue();
            assertThat(configuration.hasStatement(statement("findLimitRecords"))).isTrue();
            assertThat(configuration.hasStatement(statement("findLimitRule"))).isTrue();
            assertThat(configuration.hasStatement(statement("upsertLimitRule"))).isTrue();
            assertThat(configuration.hasStatement(statement("updateLimitRuleAutoAdjust"))).isTrue();
        }
    }

    private String statement(String id) {
        return CardStationMapper.class.getName() + "." + id;
    }
}
