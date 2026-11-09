package com.adpulse.system.application.mapper;

import static org.assertj.core.api.Assertions.assertThat;

import java.nio.charset.StandardCharsets;
import org.junit.jupiter.api.Test;

/** 申请入口 Mapper 软删除契约测试。 */
class ApplicationDefinitionMapperContractTest {

    @Test
    void shouldSoftDeleteDefinitionAndExcludeItFromManagedList() throws Exception {
        String xml;
        try (var stream =
                getClass()
                        .getClassLoader()
                        .getResourceAsStream(
                                "mapper/application/ApplicationDefinitionMapper.xml")) {
            assertThat(stream).isNotNull();
            xml = new String(stream.readAllBytes(), StandardCharsets.UTF_8);
        }

        assertThat(xml)
                .contains("WHERE definition.deleted_at = 0")
                .contains("SET status = 0, deleted_at = #{deletedAt}, updated_by = #{updatedBy}");
    }
}
