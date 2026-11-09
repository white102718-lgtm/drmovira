package com.adpulse.main.adaccountasset;

import static org.assertj.core.api.Assertions.assertThat;

import java.io.ByteArrayOutputStream;
import java.nio.charset.Charset;
import java.nio.charset.StandardCharsets;
import java.util.List;
import org.apache.poi.hssf.usermodel.HSSFWorkbook;
import org.apache.poi.ss.usermodel.Workbook;
import org.apache.poi.xssf.usermodel.XSSFWorkbook;
import org.junit.jupiter.api.Test;

/** 广告账户导入文件格式兼容与失败文件保真测试。 */
class AdAccountImportCodecTest {
    private static final List<String> HEADERS =
            List.of(
                    "*账户ID", "账户名称", "账户类型", "账户属性", "所属渠道", "管理BM", "管理BM ID", "备份BM", "备份BM ID",
                    "时区", "卡台", "卡号", "备注", "使用人");
    private final AdAccountImportCodec codec = new AdAccountImportCodec();

    @Test
    void shouldReadXlsxAndXlsWithTheSameHeaders() throws Exception {
        assertThat(codec.read(workbook(new XSSFWorkbook()), "账户.xlsx").rows()).hasSize(1);
        assertThat(codec.read(workbook(new HSSFWorkbook()), "账户.xls").rows()).hasSize(1);
    }

    @Test
    void shouldReadUtf8BomCsvWithQuotedCommaAndNewline() {
        String csv =
                "\uFEFF" + String.join(",", HEADERS) + "\r\n100,测试账户,,,,,,,,,,,\"含逗号,以及\n换行\",";

        var parsed = codec.read(csv.getBytes(StandardCharsets.UTF_8), "账户.csv");

        assertThat(parsed.rows()).hasSize(1);
        assertThat(parsed.rows().getFirst().item().accountId()).isEqualTo("100");
        assertThat(parsed.rows().getFirst().item().remark()).isEqualTo("含逗号,以及\n换行");
    }

    @Test
    void shouldFallbackToGb18030Csv() {
        String csv = String.join(",", HEADERS) + "\r\n100,中文账户,,,,,,,,,,,,";

        var parsed = codec.read(csv.getBytes(Charset.forName("GB18030")), "账户.csv");

        assertThat(parsed.rows().getFirst().item().accountName()).isEqualTo("中文账户");
    }

    @Test
    void shouldWriteCsvFailuresAsXlsxWithOriginalValues() throws Exception {
        String csv = String.join(",", HEADERS) + "\r\n100,失败账户,,,,,,,,,,,,";
        var parsed = codec.read(csv.getBytes(StandardCharsets.UTF_8), "账户.csv");
        byte[] failed =
                codec.writeFailures(
                        parsed,
                        List.of(
                                new AdAccountImportCodec.RowFailure(
                                        parsed.rows().getFirst(), "渠道不存在")));

        try (Workbook workbook = new XSSFWorkbook(new java.io.ByteArrayInputStream(failed))) {
            var sheet = workbook.getSheetAt(0);
            assertThat(sheet.getRow(0).getCell(HEADERS.size()).getStringCellValue())
                    .isEqualTo("失败原因");
            assertThat(sheet.getRow(1).getCell(0).getStringCellValue()).isEqualTo("100");
            assertThat(sheet.getRow(1).getCell(HEADERS.size()).getStringCellValue())
                    .isEqualTo("渠道不存在");
        }
    }

    private byte[] workbook(Workbook workbook) throws Exception {
        try (workbook;
                ByteArrayOutputStream output = new ByteArrayOutputStream()) {
            var sheet = workbook.createSheet("广告账户");
            var header = sheet.createRow(0);
            for (int index = 0; index < HEADERS.size(); index++) {
                header.createCell(index).setCellValue(HEADERS.get(index));
            }
            var row = sheet.createRow(1);
            row.createCell(0).setCellValue("100");
            row.createCell(1).setCellValue("测试账户");
            workbook.write(output);
            return output.toByteArray();
        }
    }
}
