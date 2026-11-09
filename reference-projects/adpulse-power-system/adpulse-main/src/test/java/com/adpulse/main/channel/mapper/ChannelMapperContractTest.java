package com.adpulse.main.channel.mapper;

import static org.assertj.core.api.Assertions.assertThat;

import java.io.InputStream;
import org.apache.ibatis.builder.xml.XMLMapperBuilder;
import org.apache.ibatis.session.Configuration;
import org.junit.jupiter.api.Test;

/** 渠道 Mapper XML 与软删除查询契约测试。 */
class ChannelMapperContractTest {

    @Test
    void shouldParseMapperAndKeepSoftDeleteFilters() throws Exception {
        String resource = "mapper/channel/ChannelMapper.xml";
        try (InputStream stream = getClass().getClassLoader().getResourceAsStream(resource)) {
            assertThat(stream).isNotNull();
            Configuration configuration = new Configuration();
            new XMLMapperBuilder(stream, configuration, resource, configuration.getSqlFragments())
                    .parse();

            assertThat(configuration.hasStatement(ChannelMapper.class.getName() + ".findChannels"))
                    .isTrue();
            assertThat(
                            configuration.hasStatement(
                                    ChannelMapper.class.getName() + ".findAssetAccounts"))
                    .isTrue();
            assertThat(
                            configuration.hasStatement(
                                    ChannelMapper.class.getName() + ".findAccountIdsByChannelId"))
                    .isTrue();
            assertThat(
                            configuration.hasStatement(
                                    ChannelMapper.class.getName() + ".countAccountsByChannelId"))
                    .isTrue();
            assertThat(configuration.hasStatement(ChannelMapper.class.getName() + ".findCampaigns"))
                    .isTrue();
        }
    }
}
