package com.adpulse.system.auth.mapper;

import static org.assertj.core.api.Assertions.assertThat;

import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import org.junit.jupiter.api.Test;

/** 登录用户查询契约测试。 */
class AuthMapperContractTest {

    @Test
    void shouldAuthenticateByPhoneOnly() throws IOException {
        String mapperXml =
                Files.readString(
                        Path.of("src", "main", "resources", "mapper", "auth", "AuthMapper.xml"));

        assertThat(mapperXml)
                .contains("AND phone = #{phone}")
                .doesNotContain("username = #{identifier}")
                .doesNotContain("phone = #{identifier}");
    }
}
