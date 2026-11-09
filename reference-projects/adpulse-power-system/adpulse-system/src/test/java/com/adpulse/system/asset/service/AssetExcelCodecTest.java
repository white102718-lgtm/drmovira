package com.adpulse.system.asset.service;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import com.adpulse.system.common.exception.BusinessException;
import java.io.ByteArrayOutputStream;
import java.nio.charset.Charset;
import java.nio.charset.StandardCharsets;
import java.util.List;
import org.apache.poi.xssf.usermodel.XSSFWorkbook;
import org.junit.jupiter.api.Test;

/** 资产 Excel 服务端解析规则测试。 */
class AssetExcelCodecTest {
    private final AssetExcelCodec codec = new AssetExcelCodec();

    @Test
    void shouldReadQuotedUtf8CsvWithBomAndEmbeddedNewline() {
        String csv = "\uFEFF*电话号码,*TG 链接,备注\r\n13800138000,https://t.me/test,\"含逗号,以及\n换行\"";

        AssetExcelCodec.ParsedWorkbook parsed =
                codec.read(csv.getBytes(StandardCharsets.UTF_8), "telegram", "资产.csv");

        assertThat(parsed.rows()).hasSize(1);
        assertThat(parsed.rows().getFirst().values())
                .containsEntry("*电话号码", "13800138000")
                .containsEntry("备注", "含逗号,以及\n换行");
    }

    @Test
    void shouldFallbackToGb18030Csv() {
        String csv = "*电话号码,*TG 链接,备注\r\n13800138000,https://t.me/test,中文备注";

        AssetExcelCodec.ParsedWorkbook parsed =
                codec.read(csv.getBytes(Charset.forName("GB18030")), "telegram", "资产.csv");

        assertThat(parsed.rows().getFirst().values()).containsEntry("备注", "中文备注");
    }

    @Test
    void shouldReadTelegramRowsFromMatchingWorksheet() throws Exception {
        try (XSSFWorkbook workbook = new XSSFWorkbook();
                ByteArrayOutputStream output = new ByteArrayOutputStream()) {
            var sheet = workbook.createSheet("TG号");
            sheet.createRow(0).createCell(0).setCellValue("*电话号码");
            sheet.getRow(0).createCell(1).setCellValue("*TG 链接");
            sheet.getRow(0).createCell(2).setCellValue("备注");
            sheet.createRow(1).createCell(0).setCellValue("15362469449");
            sheet.getRow(1).createCell(1).setCellValue("http://1.1111");
            workbook.write(output);

            AssetExcelCodec.ParsedWorkbook parsed = codec.read(output.toByteArray(), "telegram");

            assertThat(parsed.rows()).hasSize(1);
            assertThat(parsed.rows().getFirst().values())
                    .containsEntry("*电话号码", "15362469449")
                    .containsEntry("*TG 链接", "http://1.1111");
        }
    }

    @Test
    void shouldRejectUnexpectedTemplateHeaders() throws Exception {
        try (XSSFWorkbook workbook = new XSSFWorkbook();
                ByteArrayOutputStream output = new ByteArrayOutputStream()) {
            var sheet = workbook.createSheet("TG号");
            sheet.createRow(0).createCell(0).setCellValue("联系电话");
            sheet.getRow(0).createCell(1).setCellValue("*TG 链接");
            sheet.getRow(0).createCell(2).setCellValue("备注");
            workbook.write(output);

            assertThatThrownBy(() -> codec.read(output.toByteArray(), "telegram"))
                    .isInstanceOf(BusinessException.class)
                    .hasMessageContaining("表头");
        }
    }

    @Test
    void shouldReadRowsByHeaderNameAndIgnoreAdditionalColumns() throws Exception {
        try (XSSFWorkbook workbook = new XSSFWorkbook();
                ByteArrayOutputStream output = new ByteArrayOutputStream()) {
            var sheet = workbook.createSheet("TG号");
            var header = sheet.createRow(0);
            header.createCell(0).setCellValue("库存状态");
            header.createCell(1).setCellValue("*TG 链接");
            header.createCell(2).setCellValue("备注");
            header.createCell(3).setCellValue("入库时间");
            header.createCell(4).setCellValue("电话号码");
            var row = sheet.createRow(1);
            row.createCell(0).setCellValue("已分配");
            row.createCell(1).setCellValue("https://t.me/example");
            row.createCell(2).setCellValue("测试备注");
            row.createCell(3).setCellValue("2026-09-22");
            row.createCell(4).setCellValue("15362469449");
            workbook.write(output);

            AssetExcelCodec.ParsedWorkbook parsed = codec.read(output.toByteArray(), "telegram");

            assertThat(parsed.rows().getFirst().values())
                    .containsEntry("*电话号码", "15362469449")
                    .containsEntry("*TG 链接", "https://t.me/example")
                    .containsEntry("备注", "测试备注")
                    .doesNotContainKeys("库存状态", "入库时间");
        }
    }

    @Test
    void shouldRejectDuplicateHeaders() throws Exception {
        try (XSSFWorkbook workbook = new XSSFWorkbook();
                ByteArrayOutputStream output = new ByteArrayOutputStream()) {
            var sheet = workbook.createSheet("TG号");
            var header = sheet.createRow(0);
            header.createCell(0).setCellValue("*电话号码");
            header.createCell(1).setCellValue("*TG 链接");
            header.createCell(2).setCellValue("备注");
            header.createCell(3).setCellValue("备注");
            workbook.write(output);

            assertThatThrownBy(() -> codec.read(output.toByteArray(), "telegram"))
                    .isInstanceOf(BusinessException.class)
                    .hasMessageContaining("表头重复：备注");
        }
    }

    @Test
    void shouldRejectStarredAndUnstarredVersionsOfTheSameHeader() throws Exception {
        try (XSSFWorkbook workbook = new XSSFWorkbook();
                ByteArrayOutputStream output = new ByteArrayOutputStream()) {
            var sheet = workbook.createSheet("TG号");
            var header = sheet.createRow(0);
            header.createCell(0).setCellValue("*电话号码");
            header.createCell(1).setCellValue("电话号码");
            header.createCell(2).setCellValue("*TG 链接");
            header.createCell(3).setCellValue("备注");
            workbook.write(output);

            assertThatThrownBy(() -> codec.read(output.toByteArray(), "telegram"))
                    .isInstanceOf(BusinessException.class)
                    .hasMessageContaining("电话号码（带星号和不带星号不能同时存在）");
        }
    }

    @Test
    void shouldReadBmTemplateWithChannelNameAfterAssetFields() throws Exception {
        List<String> headers =
                List.of(
                        "日期", "使用途径", "BM 名称", "*BMID", "BM 链接", "使用人个号", "BM 挂日期", "是否移除供应商",
                        "渠道名称", "使用人", "备注");
        try (XSSFWorkbook workbook = new XSSFWorkbook();
                ByteArrayOutputStream output = new ByteArrayOutputStream()) {
            var sheet = workbook.createSheet("BM");
            var headerRow = sheet.createRow(0);
            var dataRow = sheet.createRow(1);
            for (int index = 0; index < headers.size(); index++) {
                headerRow.createCell(index).setCellValue(headers.get(index));
                dataRow.createCell(index).setCellValue(index == 3 ? "BM-001" : "测试值");
            }
            workbook.write(output);

            AssetExcelCodec.ParsedWorkbook parsed = codec.read(output.toByteArray(), "bm");

            assertThat(parsed.rows()).hasSize(1);
            assertThat(parsed.rows().getFirst().values())
                    .containsEntry("*BMID", "BM-001")
                    .containsEntry("渠道名称", "测试值");
        }
    }

    /** 确保页面导出的每一种资产模板都能被服务端原样识别。 */
    @Test
    void shouldReadEveryFrontendExportedAssetTemplate() throws Exception {
        assertFrontendTemplateIsAccepted(
                "fb",
                "个号",
                List.of(
                        "*个号创建日期", "名字", "*邮箱", "*密码", "*2fa", "手机号", "生日", "性别", "分配日期", "Cookie",
                        "邮箱登录网址", "使用人", "备注"));
        assertFrontendTemplateIsAccepted(
                "bm",
                "BM",
                List.of(
                        "日期", "使用途径", "BM 名称", "*BMID", "BM 链接", "使用人个号", "BM 挂日期", "是否移除供应商",
                        "渠道名称", "使用人", "备注"));
        assertFrontendTemplateIsAccepted(
                "pixel",
                "像素",
                List.of(
                        "*BM名称",
                        "*创建BMID",
                        "所属项目",
                        "*像素名称",
                        "*像素ID",
                        "Access Token",
                        "像素测试代码",
                        "使用团队",
                        "备注"));
        assertFrontendTemplateIsAccepted("telegram", "TG号", List.of("*电话号码", "*TG 链接", "备注"));
        assertFrontendTemplateIsAccepted(
                "wechat", "微信号", List.of("*微信号", "微信昵称", "绑定手机号", "使用人", "备注"));
        assertFrontendTemplateIsAccepted("page", "主页", List.of("主页 ID", "*主页名称", "使用人", "备注"));
        assertFrontendTemplateIsAccepted(
                "computer",
                "电脑",
                List.of("*资产编号", "电脑名称", "品牌", "型号", "序列号", "操作系统", "购买日期", "存放位置", "使用人", "备注"));
        assertFrontendTemplateIsAccepted(
                "mobile",
                "手机",
                List.of("*IMEI / 序列号", "手机名称", "品牌", "型号", "手机号", "操作系统", "购买日期", "使用人", "备注"));
        assertFrontendTemplateIsAccepted(
                "static_ip", "静态 IP", List.of("IP名称", "*IP 地址", "IP 国家", "使用人", "备注"));
        assertFrontendTemplateIsAccepted(
                "email", "邮箱", List.of("邮箱名称", "*邮箱账号", "*邮箱密码", "2FA 密钥", "邮箱登录网址", "使用人", "备注"));
    }

    /** 像素字段无论使用历史顺序还是新顺序，都按表头名称正确读取。 */
    @Test
    void shouldKeepReadingLegacyPixelTemplate() throws Exception {
        assertFrontendTemplateIsAccepted(
                "pixel",
                "像素",
                List.of(
                        "*像素ID",
                        "像素测试代码",
                        "*BM名称",
                        "*创建BMID",
                        "*像素名称",
                        "Access Token",
                        "所属项目",
                        "使用团队",
                        "备注"));
    }

    @Test
    void shouldAcceptFiveThousandRows() throws Exception {
        assertThat(codec.read(telegramWorkbook(5000), "telegram").rows()).hasSize(5000);
    }

    @Test
    void shouldRejectMoreThanFiveThousandRows() throws Exception {
        byte[] content = telegramWorkbook(5001);

        assertThatThrownBy(() -> codec.read(content, "telegram"))
                .isInstanceOf(BusinessException.class)
                .hasMessageContaining("单次最多导入 5000 条资产");
    }

    private byte[] telegramWorkbook(int rowCount) throws Exception {
        try (XSSFWorkbook workbook = new XSSFWorkbook();
                ByteArrayOutputStream output = new ByteArrayOutputStream()) {
            var sheet = workbook.createSheet("TG号");
            var header = sheet.createRow(0);
            header.createCell(0).setCellValue("*电话号码");
            header.createCell(1).setCellValue("*TG 链接");
            header.createCell(2).setCellValue("备注");
            for (int index = 1; index <= rowCount; index++) {
                var row = sheet.createRow(index);
                row.createCell(0).setCellValue("1380000" + index);
                row.createCell(1).setCellValue("https://t.me/" + index);
            }
            workbook.write(output);
            return output.toByteArray();
        }
    }

    private void assertFrontendTemplateIsAccepted(
            String subtype, String sheetName, List<String> headers) throws Exception {
        assertHeadersAccepted(subtype, sheetName, headers);
        assertHeadersAccepted(
                subtype,
                sheetName,
                headers.stream().map(header -> header.replaceFirst("^\\*", "")).toList());
    }

    private void assertHeadersAccepted(String subtype, String sheetName, List<String> headers)
            throws Exception {
        try (XSSFWorkbook workbook = new XSSFWorkbook();
                ByteArrayOutputStream output = new ByteArrayOutputStream()) {
            var sheet = workbook.createSheet(sheetName);
            var headerRow = sheet.createRow(0);
            var dataRow = sheet.createRow(1);
            for (int index = 0; index < headers.size(); index++) {
                headerRow.createCell(index).setCellValue(headers.get(index));
                dataRow.createCell(index).setCellValue("测试值");
            }
            workbook.write(output);

            assertThat(codec.read(output.toByteArray(), subtype).rows()).hasSize(1);
        }
    }
}
