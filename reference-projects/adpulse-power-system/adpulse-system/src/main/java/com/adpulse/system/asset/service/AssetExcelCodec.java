package com.adpulse.system.asset.service;

import com.adpulse.system.common.exception.BusinessException;
import java.io.ByteArrayInputStream;
import java.io.ByteArrayOutputStream;
import java.io.IOException;
import java.io.StringReader;
import java.nio.ByteBuffer;
import java.nio.charset.CharacterCodingException;
import java.nio.charset.Charset;
import java.nio.charset.CodingErrorAction;
import java.nio.charset.StandardCharsets;
import java.util.ArrayList;
import java.util.HashSet;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Set;
import org.apache.commons.csv.CSVFormat;
import org.apache.commons.csv.CSVParser;
import org.apache.commons.csv.CSVRecord;
import org.apache.poi.ss.usermodel.DataFormatter;
import org.apache.poi.ss.usermodel.Row;
import org.apache.poi.ss.usermodel.Sheet;
import org.apache.poi.ss.usermodel.Workbook;
import org.apache.poi.ss.usermodel.WorkbookFactory;
import org.apache.poi.xssf.usermodel.XSSFWorkbook;
import org.springframework.stereotype.Component;

/**
 * 资产批量导入文件编解码器。
 *
 * <p>模板字段和星号必填规则由服务端维护，避免浏览器解析不同 Excel 客户端生成的工作簿后出现不一致。
 */
@Component
public class AssetExcelCodec {
    private static final int MAX_ROWS = 5000;
    private static final String REMARK_HEADER = "备注";
    private static final String USAGE_USER_HEADER = "使用人";
    private static final Map<String, ImportSpec> SPECS = specs();

    /** 读取指定资产类型的工作表并严格核对模板表头。 */
    public ParsedWorkbook read(byte[] content, String subtype) {
        return read(content, subtype, "未命名导入文件.xlsx");
    }

    /** 根据文件扩展名读取 Excel 或 CSV，并严格核对当前资产类型的模板表头。 */
    public ParsedWorkbook read(byte[] content, String subtype, String fileName) {
        ImportSpec spec = SPECS.get(normalizeSubtype(subtype));
        if (spec == null) throw BusinessException.validation("不支持的资产类型");
        String extension = extension(fileName);
        if ("csv".equals(extension)) return readCsv(content, spec);
        if (!Set.of("xls", "xlsx").contains(extension)) {
            throw BusinessException.validation("仅支持 .xlsx、.xls 或 .csv 文件");
        }
        try (Workbook workbook = WorkbookFactory.create(new ByteArrayInputStream(content))) {
            Sheet sheet = workbook.getSheet(spec.sheetName());
            if (sheet == null) {
                throw BusinessException.validation("未找到“" + spec.sheetName() + "”工作表");
            }
            DataFormatter formatter = new DataFormatter();
            Map<String, Integer> headerIndexes =
                    resolveHeaderIndexes(readExcelHeader(sheet, formatter), spec.headers());
            List<ParsedRow> rows = new ArrayList<>();
            for (int index = 1; index <= sheet.getLastRowNum(); index++) {
                Row row = sheet.getRow(index);
                Map<String, String> values = readRow(row, spec.headers(), headerIndexes, formatter);
                if (values.values().stream().allMatch(String::isBlank)) continue;
                rows.add(new ParsedRow(index + 1, values));
            }
            validateRowCount(rows);
            return new ParsedWorkbook(spec, rows);
        } catch (BusinessException exception) {
            throw exception;
        } catch (Exception exception) {
            throw BusinessException.validation("无法读取 Excel 文件，请使用当前资产类型的导入模板");
        }
    }

    private ParsedWorkbook readCsv(byte[] content, ImportSpec spec) {
        try (CSVParser parser = CSVFormat.DEFAULT.parse(new StringReader(decodeCsv(content)))) {
            List<CSVRecord> records = parser.getRecords();
            if (records.isEmpty()) throw BusinessException.validation("文件中没有表头");
            Map<String, Integer> headerIndexes =
                    resolveHeaderIndexes(csvValues(records.getFirst()), spec.headers());
            List<ParsedRow> rows = new ArrayList<>();
            for (int index = 1; index < records.size(); index++) {
                CSVRecord record = records.get(index);
                Map<String, String> values = readCsvRow(record, spec.headers(), headerIndexes);
                if (values.values().stream().allMatch(String::isBlank)) continue;
                rows.add(new ParsedRow(index + 1, values));
            }
            validateRowCount(rows);
            return new ParsedWorkbook(spec, rows);
        } catch (BusinessException exception) {
            throw exception;
        } catch (Exception exception) {
            throw BusinessException.validation("无法读取 CSV 文件，请使用当前资产类型的导入模板");
        }
    }

    /** 由服务端为失败行生成可再次编辑的 Excel 文件。 */
    public byte[] writeFailures(ParsedWorkbook workbook, List<RowFailure> failures) {
        if (failures.isEmpty()) return new byte[0];
        try (Workbook result = new XSSFWorkbook();
                ByteArrayOutputStream output = new ByteArrayOutputStream()) {
            Sheet sheet = result.createSheet(workbook.spec().sheetName());
            List<String> headers = new ArrayList<>(workbook.spec().headers());
            headers.add("失败原因");
            writeRow(sheet.createRow(0), headers);
            int rowIndex = 1;
            for (RowFailure failure : failures) {
                List<String> values = new ArrayList<>();
                for (String header : workbook.spec().headers()) {
                    values.add(failure.row().values().getOrDefault(header, ""));
                }
                values.add(failure.message());
                writeRow(sheet.createRow(rowIndex++), values);
            }
            for (int index = 0; index < headers.size(); index++) sheet.setColumnWidth(index, 6000);
            result.write(output);
            return output.toByteArray();
        } catch (IOException exception) {
            throw BusinessException.conflict("生成失败数据文件失败");
        }
    }

    /** 标准导入字段必须存在，但列顺序和额外展示列不影响解析。 */
    private static Map<String, Integer> resolveHeaderIndexes(
            List<String> actualHeaderValues, List<String> expectedHeaders) {
        Map<String, Integer> indexes = new LinkedHashMap<>();
        Set<String> actualHeaders = new HashSet<>();
        for (int index = 0; index < actualHeaderValues.size(); index++) {
            String actual = actualHeaderValues.get(index).trim();
            if (actual.isBlank()) continue;
            if (!actualHeaders.add(actual)) {
                throw BusinessException.validation("表头重复：" + actual);
            }

            String standardHeader = resolveStandardHeader(actual, expectedHeaders);
            if (standardHeader == null) continue;
            if (indexes.putIfAbsent(standardHeader, index) != null) {
                throw BusinessException.validation(
                        "表头重复：" + standardHeader.replaceFirst("^\\*", "") + "（带星号和不带星号不能同时存在）");
            }
        }
        for (String expectedHeader : expectedHeaders) {
            if (!indexes.containsKey(expectedHeader)) {
                throw BusinessException.validation("缺少表头：" + expectedHeader);
            }
        }
        return indexes;
    }

    private static List<String> readExcelHeader(Sheet sheet, DataFormatter formatter) {
        Row header = sheet.getRow(0);
        if (header == null) throw BusinessException.validation("文件中没有表头");
        List<String> values = new ArrayList<>();
        for (int index = 0; index < header.getLastCellNum(); index++) {
            values.add(text(header, index, formatter));
        }
        return values;
    }

    /** 带星号字段允许使用无星号旧表头，读取后仍归一为服务端标准字段名。 */
    private static String resolveStandardHeader(String actualHeader, List<String> expectedHeaders) {
        for (String expectedHeader : expectedHeaders) {
            if (expectedHeader.equals(actualHeader)) return expectedHeader;
            if (expectedHeader.startsWith("*")
                    && expectedHeader.substring(1).equals(actualHeader)) {
                return expectedHeader;
            }
        }
        return null;
    }

    private static Map<String, String> readRow(
            Row row,
            List<String> headers,
            Map<String, Integer> headerIndexes,
            DataFormatter formatter) {
        Map<String, String> values = new LinkedHashMap<>();
        for (String header : headers) {
            values.put(header, text(row, headerIndexes.get(header), formatter));
        }
        return values;
    }

    private static Map<String, String> readCsvRow(
            CSVRecord record, List<String> headers, Map<String, Integer> headerIndexes) {
        Map<String, String> values = new LinkedHashMap<>();
        for (String header : headers) {
            int index = headerIndexes.get(header);
            values.put(header, index < record.size() ? record.get(index).trim() : "");
        }
        return values;
    }

    private static List<String> csvValues(CSVRecord record) {
        List<String> values = new ArrayList<>();
        for (String value : record) values.add(value);
        if (!values.isEmpty()) values.set(0, stripBom(values.getFirst()));
        return values;
    }

    private static String decodeCsv(byte[] content) throws CharacterCodingException {
        try {
            return stripBom(
                    StandardCharsets.UTF_8
                            .newDecoder()
                            .onMalformedInput(CodingErrorAction.REPORT)
                            .onUnmappableCharacter(CodingErrorAction.REPORT)
                            .decode(ByteBuffer.wrap(content))
                            .toString());
        } catch (CharacterCodingException exception) {
            return stripBom(
                    Charset.forName("GB18030")
                            .newDecoder()
                            .onMalformedInput(CodingErrorAction.REPORT)
                            .onUnmappableCharacter(CodingErrorAction.REPORT)
                            .decode(ByteBuffer.wrap(content))
                            .toString());
        }
    }

    private static String stripBom(String value) {
        return value != null && value.startsWith("\uFEFF") ? value.substring(1) : value;
    }

    private static String extension(String fileName) {
        if (fileName == null) return "";
        int index = fileName.lastIndexOf('.');
        return index < 0 ? "" : fileName.substring(index + 1).trim().toLowerCase();
    }

    private static void validateRowCount(List<ParsedRow> rows) {
        if (rows.isEmpty()) throw BusinessException.validation("文件中没有可导入的数据");
        if (rows.size() > MAX_ROWS) {
            throw BusinessException.validation("单次最多导入 " + MAX_ROWS + " 条资产");
        }
    }

    private static String text(Row row, int index, DataFormatter formatter) {
        if (row == null || row.getCell(index) == null) return "";
        return formatter.formatCellValue(row.getCell(index)).trim();
    }

    private static void writeRow(Row row, List<String> values) {
        for (int index = 0; index < values.size(); index++)
            row.createCell(index).setCellValue(values.get(index));
    }

    private static String normalizeSubtype(String subtype) {
        return subtype == null ? "" : subtype.trim().toLowerCase();
    }

    private static Map<String, ImportSpec> specs() {
        Map<String, ImportSpec> specs = new LinkedHashMap<>();
        specs.put(
                "fb",
                spec(
                        "fb",
                        "PERSONAL",
                        "个号",
                        "*邮箱",
                        "名字",
                        Set.of("*个号创建日期", "*邮箱", "*密码", "*2fa"),
                        "*个号创建日期",
                        "名字",
                        "*邮箱",
                        "*密码",
                        "*2fa",
                        "手机号",
                        "生日",
                        "性别",
                        "分配日期",
                        "Cookie",
                        "邮箱登录网址",
                        USAGE_USER_HEADER,
                        REMARK_HEADER));
        specs.put(
                "bm",
                spec(
                        "bm",
                        "BM",
                        "BM",
                        "*BMID",
                        "BM 名称",
                        Set.of("*BMID"),
                        "日期",
                        "使用途径",
                        "BM 名称",
                        "*BMID",
                        "BM 链接",
                        "使用人个号",
                        "BM 挂日期",
                        "是否移除供应商",
                        "渠道名称",
                        USAGE_USER_HEADER,
                        REMARK_HEADER));
        specs.put(
                "pixel",
                spec(
                        "pixel",
                        "PIXEL",
                        "像素",
                        "*像素ID",
                        "*像素名称",
                        Set.of("*像素ID", "*BM名称", "*创建BMID", "*像素名称"),
                        "*BM名称",
                        "*创建BMID",
                        "所属项目",
                        "*像素名称",
                        "*像素ID",
                        "Access Token",
                        "像素测试代码",
                        "使用团队",
                        REMARK_HEADER));
        specs.put(
                "telegram",
                spec(
                        "telegram",
                        "TG",
                        "TG号",
                        "*电话号码",
                        "*电话号码",
                        Set.of("*电话号码", "*TG 链接"),
                        "*电话号码",
                        "*TG 链接",
                        REMARK_HEADER));
        specs.put(
                "wechat",
                spec(
                        "wechat",
                        "PERSONAL",
                        "微信号",
                        "*微信号",
                        "微信昵称",
                        Set.of("*微信号"),
                        "*微信号",
                        "微信昵称",
                        "绑定手机号",
                        USAGE_USER_HEADER,
                        REMARK_HEADER));
        specs.put(
                "page",
                spec(
                        "page",
                        "PAGE",
                        "主页",
                        "主页 ID",
                        "*主页名称",
                        Set.of("*主页名称"),
                        "主页 ID",
                        "*主页名称",
                        USAGE_USER_HEADER,
                        REMARK_HEADER));
        specs.put(
                "computer",
                spec(
                        "computer",
                        "COMPUTER",
                        "电脑",
                        "*资产编号",
                        "电脑名称",
                        Set.of("*资产编号"),
                        "*资产编号",
                        "电脑名称",
                        "品牌",
                        "型号",
                        "序列号",
                        "操作系统",
                        "购买日期",
                        "存放位置",
                        USAGE_USER_HEADER,
                        REMARK_HEADER));
        specs.put(
                "mobile",
                spec(
                        "mobile",
                        "MOBILE",
                        "手机",
                        "*IMEI / 序列号",
                        "手机名称",
                        Set.of("*IMEI / 序列号"),
                        "*IMEI / 序列号",
                        "手机名称",
                        "品牌",
                        "型号",
                        "手机号",
                        "操作系统",
                        "购买日期",
                        USAGE_USER_HEADER,
                        REMARK_HEADER));
        specs.put(
                "static_ip",
                spec(
                        "static_ip",
                        "STATIC_IP",
                        "静态 IP",
                        "*IP 地址",
                        "IP名称",
                        Set.of("*IP 地址"),
                        "IP名称",
                        "*IP 地址",
                        "IP 国家",
                        USAGE_USER_HEADER,
                        REMARK_HEADER));
        specs.put(
                "email",
                spec(
                        "email",
                        "EMAIL",
                        "邮箱",
                        "*邮箱账号",
                        "邮箱名称",
                        Set.of("*邮箱账号", "*邮箱密码"),
                        "邮箱名称",
                        "*邮箱账号",
                        "*邮箱密码",
                        "2FA 密钥",
                        "邮箱登录网址",
                        USAGE_USER_HEADER,
                        REMARK_HEADER));
        return Map.copyOf(specs);
    }

    private static ImportSpec spec(
            String subtype,
            String assetType,
            String sheetName,
            String identifierHeader,
            String nameHeader,
            Set<String> requiredHeaders,
            String... headers) {
        return new ImportSpec(
                subtype,
                assetType,
                sheetName,
                identifierHeader,
                nameHeader,
                requiredHeaders,
                List.of(headers));
    }

    /** 资产类型对应的唯一 Excel 模板定义。 */
    public record ImportSpec(
            String subtype,
            String assetType,
            String sheetName,
            String identifierHeader,
            String nameHeader,
            Set<String> requiredHeaders,
            List<String> headers) {}

    /** 已按模板读取的一行原始数据。 */
    public record ParsedRow(int line, Map<String, String> values) {}

    /** 已读取的工作簿数据，用于导入和生成失败文件。 */
    public record ParsedWorkbook(ImportSpec spec, List<ParsedRow> rows) {}

    /** 一行导入失败的服务端处理结果。 */
    public record RowFailure(ParsedRow row, String message) {}
}
