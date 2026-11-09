package com.adpulse.system.file.mapper;

import static org.assertj.core.api.Assertions.assertThat;

import java.nio.charset.StandardCharsets;
import org.junit.jupiter.api.Test;

/** 通用文件查询 SQL 的有效状态约束测试。 */
class FileMapperContractTest {

    @Test
    void openFileQueryShouldOnlyReturnActiveAvailableFiles() throws Exception {
        String mapperXml;
        try (var input = getClass().getResourceAsStream("/mapper/file/FileMapper.xml")) {
            assertThat(input).isNotNull();
            mapperXml = new String(input.readAllBytes(), StandardCharsets.UTF_8);
        }

        String query =
                mapperXml.substring(
                        mapperXml.indexOf("<select id=\"findActiveFile\""),
                        mapperXml.indexOf("</select>", mapperXml.indexOf("findActiveFile")));
        assertThat(query)
                .contains("object.storage_status = 'AVAILABLE'")
                .contains("object.deleted_at = 0")
                .contains("file.deleted_at = 0")
                .doesNotContain("file.uploader_id =");
    }
}
