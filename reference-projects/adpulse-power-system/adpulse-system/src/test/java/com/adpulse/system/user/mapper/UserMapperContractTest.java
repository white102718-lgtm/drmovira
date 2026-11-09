package com.adpulse.system.user.mapper;

import static org.assertj.core.api.Assertions.assertThat;

import com.adpulse.system.config.BootstrapMapper;
import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import org.apache.ibatis.annotations.Insert;
import org.junit.jupiter.api.Test;

/** 新建账号默认停用MFA，避免受数据库待绑定默认值影响。 */
class UserMapperContractTest {

    @Test
    void shouldCheckNicknameAcrossUndeletedUsersAndExcludeCurrentUser() throws IOException {
        var configuration = new org.apache.ibatis.session.Configuration();
        String resource = "mapper/user/UserMapper.xml";
        try (var stream = getClass().getClassLoader().getResourceAsStream(resource)) {
            new org.apache.ibatis.builder.xml.XMLMapperBuilder(
                            stream, configuration, resource, configuration.getSqlFragments())
                    .parse();
        }
        var statement =
                configuration.getMappedStatement(
                        UserMapper.class.getName() + ".existsByEnglishNickname");
        var parameters = new java.util.HashMap<String, Object>();
        parameters.put("englishNickname", "Alice");
        parameters.put("excludeId", null);
        String createSql = statement.getBoundSql(parameters).getSql().replaceAll("\\s+", " ");
        assertThat(createSql)
                .contains("english_nickname = ?", "deleted_at = 0")
                .doesNotContain("status", "id !=");

        parameters.put("excludeId", 7L);
        var updateSql = statement.getBoundSql(parameters);
        assertThat(updateSql.getSql().replaceAll("\\s+", " ")).contains("id != ?");
        assertThat(updateSql.getParameterMappings())
                .extracting("property")
                .containsExactly("englishNickname", "excludeId");
    }

    @Test
    void shouldExplicitlyDisableMfaForNewUser() throws IOException {
        String xml = Files.readString(Path.of("src/main/resources/mapper/user/UserMapper.xml"));

        assertThat(xml)
                .containsPattern(
                        "(?s)<insert id=\"insert\".*?password_changed_at, mfa_status\\s*\\) VALUES \\(.*?CURRENT_TIMESTAMP\\(3\\), -1\\s*\\)\\s*</insert>");
    }

    @Test
    void shouldExplicitlyDisableMfaForBootstrapUser() throws NoSuchMethodException {
        String sql =
                String.join(
                        " ",
                        BootstrapMapper.class
                                .getMethod("insertUser", BootstrapMapper.BootstrapUser.class)
                                .getAnnotation(Insert.class)
                                .value());

        assertThat(sql)
                .contains("password_changed_at, mfa_status")
                .contains("CURRENT_TIMESTAMP(3), -1");
    }
}
