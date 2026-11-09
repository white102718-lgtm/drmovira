package com.adpulse.system.asset.service;

import com.adpulse.system.asset.mapper.DynamicAssetFlowMapper;
import com.adpulse.system.common.exception.BusinessException;
import com.adpulse.system.common.security.SecurityContextHelper;
import com.adpulse.system.file.storage.FileStorage;
import com.fasterxml.jackson.core.type.TypeReference;
import com.fasterxml.jackson.databind.ObjectMapper;
import java.awt.image.BufferedImage;
import java.io.ByteArrayInputStream;
import java.io.ByteArrayOutputStream;
import java.io.IOException;
import java.io.InputStream;
import java.math.BigDecimal;
import java.time.LocalDateTime;
import java.time.format.DateTimeFormatter;
import java.util.ArrayList;
import java.util.Collection;
import java.util.LinkedHashMap;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Locale;
import java.util.Map;
import java.util.Objects;
import java.util.Set;
import java.util.function.Function;
import java.util.stream.Collectors;
import javax.imageio.ImageIO;
import org.apache.poi.ss.usermodel.BorderStyle;
import org.apache.poi.ss.usermodel.Cell;
import org.apache.poi.ss.usermodel.CellStyle;
import org.apache.poi.ss.usermodel.ClientAnchor;
import org.apache.poi.ss.usermodel.FillPatternType;
import org.apache.poi.ss.usermodel.Font;
import org.apache.poi.ss.usermodel.HorizontalAlignment;
import org.apache.poi.ss.usermodel.IndexedColors;
import org.apache.poi.ss.usermodel.Row;
import org.apache.poi.ss.usermodel.Sheet;
import org.apache.poi.ss.usermodel.VerticalAlignment;
import org.apache.poi.ss.usermodel.Workbook;
import org.apache.poi.util.IOUtils;
import org.apache.poi.util.Units;
import org.apache.poi.xssf.usermodel.XSSFClientAnchor;
import org.apache.poi.xssf.usermodel.XSSFDrawing;
import org.apache.poi.xssf.usermodel.XSSFWorkbook;
import org.springframework.core.io.Resource;
import org.springframework.stereotype.Service;

/** 审批中心批量导出；权限校验、动态办理结果和凭证图片在服务端一次性完成。 */
@Service
public class AssetApprovalExportService {
    static final long MAX_IMAGE_BYTES = 50L * 1024 * 1024;
    private static final DateTimeFormatter DATE_TIME_FORMATTER =
            DateTimeFormatter.ofPattern("yyyy-MM-dd HH:mm:ss");
    private static final List<String> FIXED_HEADERS =
            List.of(
                    "序号", "申请单 ID", "申请单号", "申请类型", "标题", "数量", "状态", "申请人", "所属部门", "项目/渠道",
                    "当前审批人", "申请原因", "创建时间", "更新时间", "办理状态", "办理人", "办理时间", "办理备注", "已分配资产");

    private final DynamicAssetFlowMapper flowMapper;
    private final FileStorage fileStorage;
    private final ObjectMapper objectMapper;

    public AssetApprovalExportService(
            DynamicAssetFlowMapper flowMapper, FileStorage fileStorage, ObjectMapper objectMapper) {
        this.flowMapper = flowMapper;
        this.fileStorage = fileStorage;
        this.objectMapper = objectMapper;
    }

    /** 导出当前用户明确选择且有权查看的审批单。 */
    public byte[] export(List<Long> requestedIds) {
        List<Long> applicationIds = distinctIds(requestedIds);
        Map<String, Object> exportQuery = new LinkedHashMap<>();
        exportQuery.put("applicationIds", applicationIds);
        exportQuery.put("userId", SecurityContextHelper.currentUserId());
        List<Map<String, Object>> visibleRows =
                flowMapper.findVisibleApprovalExportRows(exportQuery);
        Map<Long, Map<String, Object>> rowsById =
                visibleRows.stream()
                        .collect(
                                Collectors.toMap(
                                        row -> number(row.get("id")),
                                        Function.identity(),
                                        (left, right) -> left,
                                        LinkedHashMap::new));
        if (rowsById.size() != applicationIds.size()) {
            throw BusinessException.validation("部分审批单不存在或当前用户无权导出，请刷新后重试");
        }
        List<Map<String, Object>> rows = applicationIds.stream().map(rowsById::get).toList();

        Map<Long, Map<String, Object>> completedLogs = latestCompletedLogs(applicationIds);
        Map<Long, List<Map<String, Object>>> assets = allocatedAssets(applicationIds);
        List<DynamicField> dynamicFields = collectDynamicFields(rows);
        Set<Long> imageFileIds = collectImageFileIds(rows, completedLogs);
        Map<Long, ExportImage> images = loadImages(imageFileIds);

        try {
            return writeWorkbook(rows, completedLogs, assets, dynamicFields, images);
        } catch (IOException exception) {
            throw new IllegalStateException("审批记录导出失败", exception);
        }
    }

    private List<Long> distinctIds(List<Long> ids) {
        if (ids == null || ids.isEmpty()) throw BusinessException.validation("请选择要导出的审批单");
        LinkedHashSet<Long> distinct = new LinkedHashSet<>();
        for (Long id : ids) {
            if (id == null || id <= 0) throw BusinessException.validation("审批单 ID 无效");
            distinct.add(id);
        }
        if (distinct.size() > 100) throw BusinessException.validation("单次最多导出 100 条审批单");
        return List.copyOf(distinct);
    }

    private Map<Long, Map<String, Object>> latestCompletedLogs(List<Long> applicationIds) {
        Map<Long, Map<String, Object>> result = new LinkedHashMap<>();
        for (Map<String, Object> log :
                flowMapper.findApprovalLogsByApplicationIds(applicationIds)) {
            if (!"COMPLETED".equals(text(log.get("action")))) continue;
            Map<String, Object> copy = new LinkedHashMap<>(log);
            copy.put("actionData", objectMap(log.get("actionData")));
            result.put(number(log.get("applicationId")), copy);
        }
        return result;
    }

    private Map<Long, List<Map<String, Object>>> allocatedAssets(List<Long> applicationIds) {
        return flowMapper.findAllocatedAssetsByApplicationIds(applicationIds).stream()
                .collect(
                        Collectors.groupingBy(
                                row -> number(row.get("applicationId")),
                                LinkedHashMap::new,
                                Collectors.toList()));
    }

    private List<DynamicField> collectDynamicFields(List<Map<String, Object>> rows) {
        LinkedHashMap<String, DynamicField> fields = new LinkedHashMap<>();
        for (Map<String, Object> row : rows) {
            for (Map<String, Object> field : handlerFields(row)) {
                String key = text(field.get("key")).trim();
                String label = text(field.get("label")).trim();
                String type = text(field.get("type")).trim();
                if (key.isEmpty() || label.isEmpty() || "section".equals(type)) continue;
                fields.putIfAbsent(key, new DynamicField(key, label, type));
            }
        }
        Map<String, Long> labelCounts =
                fields.values().stream()
                        .collect(Collectors.groupingBy(DynamicField::label, Collectors.counting()));
        return fields.values().stream()
                .map(
                        field ->
                                labelCounts.getOrDefault(field.label(), 0L) > 1
                                        ? field.withHeader(field.label() + "（" + field.key() + "）")
                                        : field.withHeader(field.label()))
                .toList();
    }

    private List<Map<String, Object>> handlerFields(Map<String, Object> row) {
        List<Map<String, Object>> nodes = objectList(row.get("nodes"));
        if (nodes.isEmpty()) return List.of();
        Map<String, Object> handlerAction =
                objectMap(nodes.get(nodes.size() - 1).get("handlerAction"));
        return objectList(handlerAction.get("formSchema"));
    }

    private Set<Long> collectImageFileIds(
            List<Map<String, Object>> rows, Map<Long, Map<String, Object>> completedLogs) {
        LinkedHashSet<Long> ids = new LinkedHashSet<>();
        for (Map<String, Object> row : rows) {
            Map<String, Object> log = completedLogs.get(number(row.get("id")));
            if (log == null) continue;
            Map<String, Object> actionData = objectMap(log.get("actionData"));
            Set<String> declaredImageKeys =
                    handlerFields(row).stream()
                            .filter(field -> "image-upload".equals(text(field.get("type"))))
                            .map(field -> text(field.get("key")))
                            .collect(Collectors.toSet());
            for (String key : declaredImageKeys) ids.addAll(longList(actionData.get(key)));
        }
        return ids;
    }

    private Map<Long, ExportImage> loadImages(Set<Long> fileIds) {
        if (fileIds.isEmpty()) return Map.of();
        List<Map<String, Object>> metadata =
                flowMapper.findApprovalExportFiles(new ArrayList<>(fileIds));
        Map<Long, Map<String, Object>> metadataById =
                metadata.stream()
                        .collect(
                                Collectors.toMap(
                                        row -> number(row.get("id")), Function.identity()));
        if (metadataById.size() != fileIds.size()) {
            throw BusinessException.validation("办理结果中的图片不存在或已损坏，请重新上传后再导出");
        }
        long totalBytes = metadata.stream().mapToLong(row -> number(row.get("fileSize"))).sum();
        if (totalBytes > MAX_IMAGE_BYTES) {
            throw BusinessException.validation("图片总量超过 50MB，请拆分选择后导出");
        }

        Map<Long, ExportImage> result = new LinkedHashMap<>();
        for (Long fileId : fileIds) {
            Map<String, Object> file = metadataById.get(fileId);
            Resource resource =
                    fileStorage.load(text(file.get("bucketName")), text(file.get("objectKey")));
            try (InputStream input = resource.getInputStream()) {
                byte[] bytes = IOUtils.toByteArray(input);
                result.put(
                        fileId,
                        normalizeImage(
                                fileId,
                                text(file.get("originalName")),
                                text(file.get("mimeType")),
                                bytes));
            } catch (IOException exception) {
                throw BusinessException.validation("办理结果图片读取失败：" + text(file.get("originalName")));
            }
        }
        return result;
    }

    private ExportImage normalizeImage(Long fileId, String name, String mimeType, byte[] source) {
        try {
            BufferedImage image = ImageIO.read(new ByteArrayInputStream(source));
            if (image == null) throw BusinessException.validation("不支持的办理结果图片格式：" + name);
            String normalizedMimeType = mimeType.toLowerCase(Locale.ROOT);
            boolean jpeg = normalizedMimeType.equals("image/jpeg");
            boolean png = normalizedMimeType.equals("image/png");
            if (jpeg || png) {
                return new ExportImage(
                        fileId,
                        name,
                        source,
                        jpeg ? Workbook.PICTURE_TYPE_JPEG : Workbook.PICTURE_TYPE_PNG,
                        image.getWidth(),
                        image.getHeight());
            }
            ByteArrayOutputStream output = new ByteArrayOutputStream();
            if (!ImageIO.write(image, "png", output)) {
                throw BusinessException.validation("不支持的办理结果图片格式：" + name);
            }
            return new ExportImage(
                    fileId,
                    name,
                    output.toByteArray(),
                    Workbook.PICTURE_TYPE_PNG,
                    image.getWidth(),
                    image.getHeight());
        } catch (IOException exception) {
            throw BusinessException.validation("办理结果图片已损坏：" + name);
        }
    }

    private byte[] writeWorkbook(
            List<Map<String, Object>> rows,
            Map<Long, Map<String, Object>> completedLogs,
            Map<Long, List<Map<String, Object>>> allocatedAssets,
            List<DynamicField> dynamicFields,
            Map<Long, ExportImage> images)
            throws IOException {
        try (XSSFWorkbook workbook = new XSSFWorkbook();
                ByteArrayOutputStream output = new ByteArrayOutputStream()) {
            Sheet sheet = workbook.createSheet("审批记录");
            CellStyle headerStyle = headerStyle(workbook);
            CellStyle bodyStyle = bodyStyle(workbook);
            List<String> headers = new ArrayList<>(FIXED_HEADERS);
            headers.addAll(dynamicFields.stream().map(DynamicField::header).toList());
            writeHeader(sheet, headers, headerStyle);

            Map<Long, Integer> pictureIndexes = new LinkedHashMap<>();
            images.forEach(
                    (id, image) ->
                            pictureIndexes.put(
                                    id, workbook.addPicture(image.bytes(), image.pictureType())));
            XSSFDrawing drawing = (XSSFDrawing) sheet.createDrawingPatriarch();

            for (int index = 0; index < rows.size(); index++) {
                Map<String, Object> application = rows.get(index);
                long applicationId = number(application.get("id"));
                Map<String, Object> completed = completedLogs.get(applicationId);
                Map<String, Object> actionData =
                        completed == null ? Map.of() : objectMap(completed.get("actionData"));
                Row row = sheet.createRow(index + 1);
                List<Object> fixedValues =
                        fixedValues(
                                index + 1,
                                application,
                                completed,
                                actionData,
                                allocatedAssets.getOrDefault(applicationId, List.of()));
                for (int column = 0; column < fixedValues.size(); column++) {
                    writeCell(row, column, fixedValues.get(column), bodyStyle);
                }
                for (int fieldIndex = 0; fieldIndex < dynamicFields.size(); fieldIndex++) {
                    DynamicField field = dynamicFields.get(fieldIndex);
                    int column = FIXED_HEADERS.size() + fieldIndex;
                    if ("image-upload".equals(field.type())) {
                        List<Long> ids = longList(actionData.get(field.key()));
                        writeImageCell(
                                sheet,
                                row,
                                column,
                                ids,
                                images,
                                pictureIndexes,
                                drawing,
                                bodyStyle);
                    } else {
                        writeCell(row, column, formatValue(actionData.get(field.key())), bodyStyle);
                    }
                }
            }

            sheet.createFreezePane(0, 1);
            sheet.setAutoFilter(
                    new org.apache.poi.ss.util.CellRangeAddress(0, 0, 0, headers.size() - 1));
            for (int column = 0; column < headers.size(); column++) {
                boolean imageColumn =
                        column >= FIXED_HEADERS.size()
                                && "image-upload"
                                        .equals(
                                                dynamicFields
                                                        .get(column - FIXED_HEADERS.size())
                                                        .type());
                sheet.setColumnWidth(column, (imageColumn ? 34 : 20) * 256);
            }
            workbook.write(output);
            return output.toByteArray();
        }
    }

    private List<Object> fixedValues(
            int sequence,
            Map<String, Object> application,
            Map<String, Object> completed,
            Map<String, Object> actionData,
            List<Map<String, Object>> currentAssets) {
        return List.of(
                sequence,
                text(application.get("id")),
                text(application.get("applicationNo")),
                text(application.get("applicationTypeName")),
                text(application.get("title")),
                number(application.get("quantity")),
                statusLabel(text(application.get("status"))),
                text(application.get("requesterName")),
                text(application.get("departmentName")),
                text(application.get("projectName")),
                text(application.get("approverName")),
                text(application.get("reason")),
                formatDate(application.get("createdAt")),
                formatDate(application.get("updatedAt")),
                processingStatus(application, completed),
                completed == null ? "" : text(completed.get("actorName")),
                completed == null ? "" : formatDate(completed.get("createdAt")),
                completed == null ? "" : text(completed.get("remark")),
                allocatedAssetText(actionData, currentAssets));
    }

    private String processingStatus(
            Map<String, Object> application, Map<String, Object> completed) {
        if (completed != null) return "办理完成";
        if ("PROCESSING".equals(text(application.get("status")))) return "待办理";
        return handlerFields(application).isEmpty() ? "未配置" : "未开始";
    }

    private String allocatedAssetText(
            Map<String, Object> actionData, List<Map<String, Object>> currentAssets) {
        List<Map<String, Object>> snapshots = objectList(actionData.get("_allocatedAssets"));
        List<Map<String, Object>> assets = snapshots.isEmpty() ? currentAssets : snapshots;
        return assets.stream()
                .map(
                        asset -> {
                            String name = firstText(asset, "assetName", "name");
                            String code = firstText(asset, "assetCode", "id");
                            String type = text(asset.get("assetType"));
                            String owner = firstText(asset, "channelName", "projectName");
                            List<String> details =
                                    List.of(code, type, owner).stream()
                                            .filter(value -> !value.isBlank())
                                            .toList();
                            return details.isEmpty()
                                    ? name
                                    : name + "（" + String.join("，", details) + "）";
                        })
                .filter(value -> !value.isBlank())
                .collect(Collectors.joining("\n"));
    }

    private void writeHeader(Sheet sheet, List<String> headers, CellStyle style) {
        Row header = sheet.createRow(0);
        header.setHeightInPoints(30);
        for (int index = 0; index < headers.size(); index++) {
            writeCell(header, index, headers.get(index), style);
        }
    }

    private void writeCell(Row row, int column, Object value, CellStyle style) {
        Cell cell = row.createCell(column);
        cell.setCellStyle(style);
        if (value instanceof Number number) cell.setCellValue(number.doubleValue());
        else cell.setCellValue(text(value));
    }

    private void writeImageCell(
            Sheet sheet,
            Row row,
            int column,
            List<Long> imageIds,
            Map<Long, ExportImage> images,
            Map<Long, Integer> pictureIndexes,
            XSSFDrawing drawing,
            CellStyle style) {
        Cell cell = row.createCell(column);
        cell.setCellStyle(style);
        if (imageIds.isEmpty()) return;
        row.setHeightInPoints(Math.max(row.getHeightInPoints(), 92));
        sheet.setColumnWidth(column, 34 * 256);
        int slotWidth = 82;
        int maxHeight = 112;
        for (int index = 0; index < imageIds.size(); index++) {
            ExportImage image = images.get(imageIds.get(index));
            Integer pictureIndex = pictureIndexes.get(imageIds.get(index));
            if (image == null || pictureIndex == null) continue;
            double scale =
                    Math.min((slotWidth - 8d) / image.width(), maxHeight / (double) image.height());
            int width = Math.max(1, (int) Math.round(image.width() * scale));
            int height = Math.max(1, (int) Math.round(image.height() * scale));
            int x = index * slotWidth + Math.max(4, (slotWidth - width) / 2);
            int y = Math.max(3, (maxHeight - height) / 2);
            XSSFClientAnchor anchor = new XSSFClientAnchor();
            anchor.setAnchorType(ClientAnchor.AnchorType.MOVE_AND_RESIZE);
            anchor.setCol1(column);
            anchor.setCol2(column);
            anchor.setRow1(row.getRowNum());
            anchor.setRow2(row.getRowNum());
            anchor.setDx1(Units.pixelToEMU(x));
            anchor.setDx2(Units.pixelToEMU(x + width));
            anchor.setDy1(Units.pixelToEMU(y));
            anchor.setDy2(Units.pixelToEMU(y + height));
            drawing.createPicture(anchor, pictureIndex);
        }
    }

    private CellStyle headerStyle(Workbook workbook) {
        CellStyle style = workbook.createCellStyle();
        style.setFillForegroundColor(IndexedColors.GREY_25_PERCENT.getIndex());
        style.setFillPattern(FillPatternType.SOLID_FOREGROUND);
        style.setAlignment(HorizontalAlignment.CENTER);
        style.setVerticalAlignment(VerticalAlignment.CENTER);
        style.setBorderBottom(BorderStyle.THIN);
        Font font = workbook.createFont();
        font.setBold(true);
        style.setFont(font);
        return style;
    }

    private CellStyle bodyStyle(Workbook workbook) {
        CellStyle style = workbook.createCellStyle();
        style.setVerticalAlignment(VerticalAlignment.CENTER);
        style.setWrapText(true);
        style.setBorderBottom(BorderStyle.HAIR);
        return style;
    }

    private String statusLabel(String status) {
        return switch (status) {
            case "PENDING" -> "待审批";
            case "PROCESSING" -> "待办理";
            case "APPROVED" -> "已完成";
            case "REJECTED" -> "已拒绝";
            default -> status;
        };
    }

    private String formatValue(Object value) {
        if (value == null) return "";
        if (value instanceof Boolean bool) return bool ? "是" : "否";
        if (value instanceof Collection<?> collection) {
            return collection.stream().map(this::text).collect(Collectors.joining("、"));
        }
        if (value instanceof Number number) {
            return new BigDecimal(number.toString()).stripTrailingZeros().toPlainString();
        }
        return text(value);
    }

    private String formatDate(Object value) {
        if (value instanceof LocalDateTime dateTime) return DATE_TIME_FORMATTER.format(dateTime);
        return text(value);
    }

    private String firstText(Map<String, Object> value, String... keys) {
        for (String key : keys) {
            String candidate = text(value.get(key)).trim();
            if (!candidate.isEmpty()) return candidate;
        }
        return "";
    }

    private Map<String, Object> objectMap(Object value) {
        if (value instanceof Map<?, ?> map) {
            Map<String, Object> result = new LinkedHashMap<>();
            map.forEach((key, item) -> result.put(text(key), item));
            return result;
        }
        String json = text(value).trim();
        if (json.isEmpty()) return new LinkedHashMap<>();
        try {
            return objectMapper.readValue(json, new TypeReference<>() {});
        } catch (IOException exception) {
            throw BusinessException.validation("审批办理结果数据格式异常");
        }
    }

    private List<Map<String, Object>> objectList(Object value) {
        if (value instanceof List<?> list) {
            return list.stream().filter(Map.class::isInstance).map(this::objectMap).toList();
        }
        String json = text(value).trim();
        if (json.isEmpty()) return List.of();
        try {
            List<Object> values = objectMapper.readValue(json, new TypeReference<>() {});
            return values.stream().filter(Map.class::isInstance).map(this::objectMap).toList();
        } catch (IOException exception) {
            throw BusinessException.validation("审批流程配置数据格式异常");
        }
    }

    private List<Long> longList(Object value) {
        if (!(value instanceof Collection<?> collection)) return List.of();
        List<Long> result = new ArrayList<>();
        for (Object item : collection) {
            long id = number(item);
            if (id > 0) result.add(id);
        }
        return result;
    }

    private long number(Object value) {
        if (value instanceof Number number) return number.longValue();
        try {
            return Long.parseLong(text(value));
        } catch (NumberFormatException exception) {
            return 0;
        }
    }

    private String text(Object value) {
        return Objects.toString(value, "");
    }

    private record DynamicField(String key, String label, String type, String header) {
        private DynamicField(String key, String label, String type) {
            this(key, label, type, label);
        }

        private DynamicField withHeader(String value) {
            return new DynamicField(key, label, type, value);
        }
    }

    private record ExportImage(
            long id, String name, byte[] bytes, int pictureType, int width, int height) {}
}
