package com.adpulse.main.channel.service;

import static org.assertj.core.api.Assertions.assertThat;

import java.io.ByteArrayInputStream;
import org.apache.poi.xssf.usermodel.XSSFWorkbook;
import org.junit.jupiter.api.Test;

/** 渠道账户工作簿格式测试。 */
class ChannelExcelCodecTest {
    private final ChannelExcelCodec codec = new ChannelExcelCodec();

    @Test
    void shouldCreateReadableImportTemplate() throws Exception {
        byte[] content = codec.template();

        try (var workbook = new XSSFWorkbook(new ByteArrayInputStream(content))) {
            assertThat(workbook.getSheetAt(0).getRow(0).getCell(0).getStringCellValue())
                    .isEqualTo("渠道ID");
            assertThat(workbook.getSheetAt(0).getRow(1).getCell(1).getStringCellValue())
                    .isEqualTo("123456789012345");
        }
    }
}
