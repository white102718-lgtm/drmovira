package com.adpulse.main.adaccountasset;

import com.adpulse.main.adaccountasset.AdAccountAssetRequests.ImportItem;
import com.adpulse.main.adaccountasset.AdAccountAssetService.AdAccountAssetException;
import java.io.ByteArrayInputStream;
import java.io.ByteArrayOutputStream;
import java.io.StringReader;
import java.nio.ByteBuffer;
import java.nio.charset.CharacterCodingException;
import java.nio.charset.Charset;
import java.nio.charset.CodingErrorAction;
import java.nio.charset.StandardCharsets;
import java.util.ArrayList;
import java.util.HashMap;
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

/** 广告账户 xlsx、xls 与 csv 导入文件的服务端编解码器。 */
@Component
public class AdAccountImportCodec {
    private static final int MAX_ROWS = 5000;
    private static final List<String> REQUIRED_HEADERS =
            List.of(
                    "*账户ID", "账户名称", "账户类型", "账户属性", "所属渠道", "管理BM", "管理BM ID", "备份BM", "备份BM ID",
                    "时区", "卡台", "卡号", "备注");
    private static final List<String> OPTIONAL_HEADERS = List.of("渠道 ID", "使用人");
    private static final Map<String, String> HEADER_ALIASES = headerAliases();

    /** 按扩展名解析广告账户导入文件，保留原始列以生成失败工作簿。 */
    public ParsedFile read(byte[] content, String fileName) {
        String extension = extension(fileName);
        if ("csv".equals(extension)) return readCsv(content);
        if (!Set.of("xls", "xlsx").contains(extension)) {
            throw new AdAccountAssetException("仅支持 .xlsx、.xls 或 .csv 文件");
        }
        return readExcel(content);
    }

    /** 将失败行写入标准 xlsx，避免 CSV 丢失失败原因或破坏中文编码。 */
    public byte[] writeFailures(ParsedFile parsed, List<RowFailure> failures) {
        if (failures.isEmpty()) return new byte[0];
        try (Workbook workbook = new XSSFWorkbook();
                ByteArrayOutputStream output = new ByteArrayOutputStream()) {
            Sheet sheet = workbook.createSheet("广告账户导入失败数据");
            List<String> headers = new ArrayList<>(parsed.sourceHeaders());
            headers.add("失败原因");
            writeRow(sheet.createRow(0), headers);
            int rowIndex = 1;
            for (RowFailure failure : failures) {
                List<String> values = new ArrayList<>(failure.row().sourceValues());
                while (values.size() < parsed.sourceHeaders().size()) values.add("");
                values.add(failure.message());
                writeRow(sheet.createRow(rowIndex++), values);
            }
            for (int index = 0; index < headers.size(); index++) {
                sheet.setColumnWidth(index, 6000);
            }
            workbook.write(output);
            return output.toByteArray();
        } catch (Exception exception) {
            throw new AdAccountAssetException("生成失败数据文件失败");
        }
    }

    private ParsedFile readExcel(byte[] content) {
        try (Workbook workbook = WorkbookFactory.create(new ByteArrayInputStream(content))) {
            if (workbook.getNumberOfSheets() == 0) {
                throw new AdAccountAssetException("文件中没有可读取的工作表");
            }
            Sheet sheet = workbook.getSheetAt(0);
            DataFormatter formatter = new DataFormatter();
            List<String> sourceHeaders = excelHeader(sheet, formatter);
            HeaderResolution resolution = resolveHeaders(sourceHeaders);
            List<ParsedRow> rows = new ArrayList<>();
            for (int index = 1; index <= sheet.getLastRowNum(); index++) {
                List<String> sourceValues =
                        excelValues(sheet.getRow(index), sourceHeaders.size(), formatter);
                addRow(rows, index + 1, sourceValues, resolution);
            }
            validateRows(rows);
            return new ParsedFile(sourceHeaders, rows);
        } catch (AdAccountAssetException exception) {
            throw exception;
        } catch (Exception exception) {
            throw new AdAccountAssetException("无法读取 Excel 文件，请使用下载的广告账户模板");
        }
    }

    private ParsedFile readCsv(byte[] content) {
        try (CSVParser parser = CSVFormat.DEFAULT.parse(new StringReader(decodeCsv(content)))) {
            List<CSVRecord> records = parser.getRecords();
            if (records.isEmpty()) throw new AdAccountAssetException("文件中没有表头");
            List<String> sourceHeaders = csvValues(records.getFirst());
            HeaderResolution resolution = resolveHeaders(sourceHeaders);
            List<ParsedRow> rows = new ArrayList<>();
            for (int index = 1; index < records.size(); index++) {
                addRow(rows, index + 1, csvValues(records.get(index)), resolution);
            }
            validateRows(rows);
            return new ParsedFile(sourceHeaders, rows);
        } catch (AdAccountAssetException exception) {
            throw exception;
        } catch (Exception exception) {
            throw new AdAccountAssetException("无法读取 CSV 文件，请使用下载的广告账户模板");
        }
    }

    private static void addRow(
            List<ParsedRow> rows,
            int line,
            List<String> sourceValues,
            HeaderResolution resolution) {
        if (sourceValues.stream().allMatch(String::isBlank)) return;
        Map<String, String> values = new LinkedHashMap<>();
        for (Map.Entry<String, Integer> entry : resolution.standardIndexes().entrySet()) {
            int index = entry.getValue();
            values.put(
                    entry.getKey(),
                    index < sourceValues.size() ? sourceValues.get(index).trim() : "");
        }
        rows.add(new ParsedRow(line, sourceValues, toImportItem(line, values)));
    }

    private static ImportItem toImportItem(int line, Map<String, String> values) {
        return new ImportItem(
                line,
                values.get("*账户ID"),
                values.get("账户名称"),
                values.get("账户类型"),
                values.get("账户属性"),
                values.get("渠道 ID"),
                values.get("所属渠道"),
                values.get("管理BM"),
                values.get("管理BM ID"),
                values.get("备份BM"),
                values.get("备份BM ID"),
                values.get("时区"),
                values.get("卡台"),
                values.get("卡号"),
                values.get("备注"),
                values.containsKey("使用人") ? values.get("使用人") : null);
    }

    private static HeaderResolution resolveHeaders(List<String> sourceHeaders) {
        if (sourceHeaders.isEmpty()) throw new AdAccountAssetException("文件中没有表头");
        Map<String, Integer> indexes = new LinkedHashMap<>();
        Set<String> actualHeaders = new HashSet<>();
        for (int index = 0; index < sourceHeaders.size(); index++) {
            String actual = sourceHeaders.get(index).trim();
            if (actual.isBlank()) continue;
            if (!actualHeaders.add(actual)) {
                throw new AdAccountAssetException("表头重复：" + actual);
            }
            String standard = HEADER_ALIASES.getOrDefault(actual, actual);
            if (!REQUIRED_HEADERS.contains(standard) && !OPTIONAL_HEADERS.contains(standard))
                continue;
            if (indexes.putIfAbsent(standard, index) != null) {
                throw new AdAccountAssetException(
                        "表头重复：" + standard.replaceFirst("^\\*", "") + "（别名不能同时存在）");
            }
        }
        for (String required : REQUIRED_HEADERS) {
            if (!indexes.containsKey(required)) {
                throw new AdAccountAssetException("缺少表头：" + required);
            }
        }
        return new HeaderResolution(indexes);
    }

    private static List<String> excelHeader(Sheet sheet, DataFormatter formatter) {
        Row row = sheet.getRow(0);
        if (row == null) throw new AdAccountAssetException("文件中没有表头");
        return excelValues(row, Math.max(row.getLastCellNum(), 0), formatter);
    }

    private static List<String> excelValues(Row row, int size, DataFormatter formatter) {
        List<String> values = new ArrayList<>();
        for (int index = 0; index < size; index++) {
            values.add(
                    row == null || row.getCell(index) == null
                            ? ""
                            : formatter.formatCellValue(row.getCell(index)).trim());
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
            return stripBom(decode(content, StandardCharsets.UTF_8));
        } catch (CharacterCodingException exception) {
            return stripBom(decode(content, Charset.forName("GB18030")));
        }
    }

    private static String decode(byte[] content, Charset charset) throws CharacterCodingException {
        return charset.newDecoder()
                .onMalformedInput(CodingErrorAction.REPORT)
                .onUnmappableCharacter(CodingErrorAction.REPORT)
                .decode(ByteBuffer.wrap(content))
                .toString();
    }

    private static String stripBom(String value) {
        return value != null && value.startsWith("\uFEFF") ? value.substring(1) : value;
    }

    private static String extension(String fileName) {
        if (fileName == null) return "";
        int index = fileName.lastIndexOf('.');
        return index < 0 ? "" : fileName.substring(index + 1).trim().toLowerCase();
    }

    private static void validateRows(List<ParsedRow> rows) {
        if (rows.isEmpty()) throw new AdAccountAssetException("文件中没有可导入的数据");
        if (rows.size() > MAX_ROWS) {
            throw new AdAccountAssetException("单次最多导入 " + MAX_ROWS + " 条广告账户");
        }
    }

    private static void writeRow(Row row, List<String> values) {
        for (int index = 0; index < values.size(); index++) {
            row.createCell(index).setCellValue(values.get(index));
        }
    }

    private static Map<String, String> headerAliases() {
        Map<String, String> aliases = new HashMap<>();
        aliases.put("账户ID", "*账户ID");
        aliases.put("账户 ID", "*账户ID");
        aliases.put("渠道名称", "所属渠道");
        aliases.put("管理 BM", "管理BM");
        aliases.put("BMID", "管理BM ID");
        aliases.put("BM ID", "管理BM ID");
        aliases.put("管理 BM ID", "管理BM ID");
        aliases.put("备份 BM", "备份BM");
        aliases.put("备份管理BM", "备份BM");
        aliases.put("备份管理 BM", "备份BM");
        aliases.put("备份 BM ID", "备份BM ID");
        aliases.put("备份管理BM ID", "备份BM ID");
        aliases.put("备份管理 BM ID", "备份BM ID");
        return Map.copyOf(aliases);
    }

    /** 已解析文件及其原始表头。 */
    public record ParsedFile(List<String> sourceHeaders, List<ParsedRow> rows) {}

    /** 已解析的单行数据，同时保留生成失败文件所需的原始值。 */
    public record ParsedRow(int line, List<String> sourceValues, ImportItem item) {}

    /** 单行失败结果。 */
    public record RowFailure(ParsedRow row, String message) {}

    private record HeaderResolution(Map<String, Integer> standardIndexes) {}
}
