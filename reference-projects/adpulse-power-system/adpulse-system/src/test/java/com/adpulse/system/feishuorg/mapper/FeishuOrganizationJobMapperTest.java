package com.adpulse.system.feishuorg.mapper;

import static org.assertj.core.api.Assertions.assertThat;

import java.io.InputStream;
import org.apache.ibatis.builder.xml.XMLMapperBuilder;
import org.apache.ibatis.session.Configuration;
import org.junit.jupiter.api.Test;

/** 真实 MyBatis 解析验证任务映射及租约查询缓存约束。 */
class FeishuOrganizationJobMapperTest {
    @Test
    void shouldRequireMfaBindingOnlyWhenCreatingSyncedUser() throws Exception {
        var configuration = new Configuration();
        String path = "mapper/feishuorg/FeishuOrganizationMapper.xml";
        try (InputStream input = getClass().getClassLoader().getResourceAsStream(path)) {
            new XMLMapperBuilder(input, configuration, path, configuration.getSqlFragments())
                    .parse();
        }
        String namespace = FeishuOrganizationMapper.class.getName();
        String insertSql =
                configuration
                        .getMappedStatement(namespace + ".insertUser")
                        .getBoundSql(null)
                        .getSql()
                        .replaceAll("\\s+", " ");
        assertThat(insertSql)
                .contains("ip_access_mode, mfa_status, remark")
                .contains("?, ?, ?, 0, 0, '飞书组织同步创建'");

        String updateSql =
                configuration
                        .getMappedStatement(namespace + ".updateUser")
                        .getBoundSql(null)
                        .getSql();
        assertThat(updateSql)
                .doesNotContain(
                        "mfa_status",
                        "mfa_secret_ciphertext",
                        "mfa_bound_at",
                        "mfa_last_used_counter");
    }

    @Test
    void parsesMappingsAndRefreshesLeaseClockWithinTransaction() throws Exception {
        var configuration = new Configuration();
        for (String file :
                new String[] {"FeishuOrganizationJobMapper", "FeishuOrganizationMapper"}) {
            String path = "mapper/feishuorg/" + file + ".xml";
            try (InputStream input = getClass().getClassLoader().getResourceAsStream(path)) {
                new XMLMapperBuilder(input, configuration, path, configuration.getSqlFragments())
                        .parse();
            }
        }
        var clock =
                configuration.getMappedStatement(
                        FeishuOrganizationJobMapper.class.getName() + ".now");
        assertThat(clock.isFlushCacheRequired()).isTrue();
        assertThat(clock.isUseCache()).isFalse();
        assertThat(
                        configuration.hasStatement(
                                FeishuOrganizationMapper.class.getName() + ".finishLog"))
                .isTrue();
    }
}
