package com.adpulse.system.dictionary.mapper;

import static org.assertj.core.api.Assertions.assertThat;

import java.nio.charset.StandardCharsets;
import org.junit.jupiter.api.Test;

/** 字典 Mapper 软删除与启用过滤契约测试。 */
class DictionaryMapperContractTest {

    @Test
    void shouldFilterDeletedAndDisabledRowsForBusinessOptionLookup() throws Exception {
        String xml;
        try (var stream =
                getClass()
                        .getClassLoader()
                        .getResourceAsStream("mapper/dictionary/DictionaryMapper.xml")) {
            assertThat(stream).isNotNull();
            xml = new String(stream.readAllBytes(), StandardCharsets.UTF_8);
        }

        assertThat(xml)
                .contains("dict_code = #{dictCode} AND status = 1 AND deleted_at = 0")
                .contains("dict_type_id = #{dictTypeId} AND status = 1 AND deleted_at = 0")
                .contains("SET status = 0, deleted_at = #{deletedAt}, updated_by = #{updatedBy}");
    }
}
