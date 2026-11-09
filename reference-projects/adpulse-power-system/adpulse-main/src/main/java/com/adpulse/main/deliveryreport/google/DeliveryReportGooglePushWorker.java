package com.adpulse.main.deliveryreport.google;

import com.adpulse.main.deliveryreport.google.DeliveryReportGooglePushModels.Item;
import com.adpulse.main.google.client.GoogleProviderClient;
import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.core.type.TypeReference;
import com.fasterxml.jackson.databind.ObjectMapper;
import java.math.BigDecimal;
import java.util.*;
import java.util.stream.Collectors;
import lombok.extern.slf4j.Slf4j;
import org.springframework.scheduling.annotation.Scheduled;
import org.springframework.stereotype.Service;

/** 后台执行Google日报批次，以模板配置的联合唯一键实现新增或原行更新。 */
@Slf4j
@Service
public class DeliveryReportGooglePushWorker {
    private final DeliveryReportGooglePushMapper mapper;
    private final DeliveryReportGoogleServiceAccount serviceAccount;
    private final GoogleProviderClient provider;
    private final ObjectMapper json;

    public DeliveryReportGooglePushWorker(
            DeliveryReportGooglePushMapper mapper,
            DeliveryReportGoogleServiceAccount serviceAccount,
            GoogleProviderClient provider,
            ObjectMapper json) {
        this.mapper = mapper;
        this.serviceAccount = serviceAccount;
        this.provider = provider;
        this.json = json;
    }

    /** 周期领取待执行批次；单条失败会记录原因并继续处理同批次其他日报。 */
    @Scheduled(fixedDelayString = "${adpulse.google.delivery-push-worker-delay-ms:3000}")
    public void consumePendingBatches() {
        mapper.recoverStaleItems();
        mapper.recoverStaleBatches();
        for (Long batchId : mapper.findPendingBatchIds(5)) {
            if (mapper.claimBatch(batchId) != 1) continue;
            executeBatch(batchId);
        }
    }

    private void executeBatch(Long batchId) {
        String batchError = null;
        try {
            Map<Target, List<Item>> groups =
                    mapper.findItems(batchId).stream()
                            .filter(item -> item.getStatus() == 0)
                            .collect(
                                    Collectors.groupingBy(
                                            item ->
                                                    new Target(
                                                            item.getSpreadsheetId(),
                                                            item.getSheetId(),
                                                            item.getSheetTitle(),
                                                            item.getHeaderRow(),
                                                            item.getUniqueKeyColumns()),
                                            LinkedHashMap::new,
                                            Collectors.toList()));
            for (var entry : groups.entrySet())
                executeTarget(entry.getKey(), entry.getValue());
        } catch (RuntimeException exception) {
            batchError = safeError(exception);
            log.warn("投放日报Google批次执行中断: batchId={}, message={}", batchId, batchError);
        } finally {
            mapper.finishBatch(batchId, batchError);
        }
    }

    private void executeTarget(Target target, List<Item> items) {
        String accessToken;
        Target resolvedTarget;
        Map<List<String>, Integer> existingRows;
        List<String> headers;
        List<String> uniqueKeyColumns;
        try {
            accessToken = serviceAccount.accessToken();
            String currentSheetTitle =
                    provider.sheets(accessToken, target.spreadsheetId()).stream()
                            .filter(sheet -> target.sheetId().equals(sheet.id()))
                            .map(sheet -> sheet.title())
                            .findFirst()
                            .orElseThrow(() -> new IllegalStateException("目标Google页签不存在或无权访问"));
            resolvedTarget = target.withSheetTitle(currentSheetTitle);
            uniqueKeyColumns = stringList(resolvedTarget.uniqueKeyColumns());
            if (uniqueKeyColumns.isEmpty())
                throw new IllegalStateException("项目日报推送快照未配置唯一字段");
            headers = headers(accessToken, resolvedTarget);
            for (Item item : items) validateHeaders(item, headers);
            existingRows = existingRows(accessToken, resolvedTarget, uniqueKeyColumns);
        } catch (RuntimeException exception) {
            failAll(items, safeError(exception));
            return;
        }
        for (Item item : items) {
            if (mapper.claimItem(item.getId()) != 1) continue;
            try {
                Map<String, Object> values = values(item.getFieldValues());
                List<String> uniqueKey = uniqueKey(values, uniqueKeyColumns);
                Integer rowNumber = existingRows.get(uniqueKey);
                if (rowNumber == null) {
                    rowNumber =
                            provider.appendValues(
                                    accessToken,
                                    item.getSpreadsheetId(),
                                    resolvedTarget.sheetTitle(),
                                    appendRow(values));
                    existingRows.put(uniqueKey, rowNumber);
                } else {
                    provider.updateValues(
                            accessToken,
                            item.getSpreadsheetId(),
                            resolvedTarget.sheetTitle(),
                            rowNumber,
                            values);
                }
                if (rowNumber == resolvedTarget.headerRow() + 1)
                    provider.clearRowFormat(
                            accessToken,
                            item.getSpreadsheetId(),
                            resolvedTarget.sheetId(),
                            rowNumber);
                mapper.completeItem(item.getId(), rowNumber);
            } catch (RuntimeException exception) {
                mapper.failItem(item.getId(), safeError(exception));
            }
        }
    }

    private Map<List<String>, Integer> existingRows(
            String accessToken, Target target, List<String> uniqueKeyColumns) {
        List<List<Object>> rows =
                provider.rawValues(accessToken, target.spreadsheetId(), target.sheetTitle());
        Map<List<String>, Integer> result = new HashMap<>();
        for (int index = 0; index < rows.size(); index++) {
            if (index + 1 <= target.headerRow()) continue;
            List<String> uniqueKey = uniqueKey(rows.get(index), uniqueKeyColumns);
            if (uniqueKey.isEmpty()) continue;
            if (result.putIfAbsent(uniqueKey, index + 1) != null)
                throw new IllegalStateException(
                        "目标表格存在重复的联合唯一值：" + String.join(" / ", uniqueKey));
        }
        return result;
    }

    private List<String> uniqueKey(
            Map<String, Object> values, List<String> uniqueKeyColumns) {
        List<String> result = new ArrayList<>();
        for (String column : uniqueKeyColumns) {
            Object value = values.get(column);
            String part = normalizeKeyPart(value);
            if (part.isEmpty()) throw new IllegalStateException("待推送数据的唯一字段不能为空");
            result.add(part);
        }
        return List.copyOf(result);
    }

    private List<String> uniqueKey(List<Object> row, List<String> uniqueKeyColumns) {
        List<String> result = new ArrayList<>();
        for (String column : uniqueKeyColumns) {
            int index = columnIndex(column) - 1;
            String part = normalizeKeyPart(index < row.size() ? row.get(index) : null);
            if (part.isEmpty()) return List.of();
            result.add(part);
        }
        return List.copyOf(result);
    }

    private String normalizeKeyPart(Object value) {
        if (value == null) return "";
        if (value instanceof Number number)
            return new BigDecimal(number.toString()).stripTrailingZeros().toPlainString();
        return value.toString().trim();
    }

    private List<String> headers(String accessToken, Target target) {
        String range =
                quoteSheet(target.sheetTitle())
                        + "!"
                        + target.headerRow()
                        + ":"
                        + target.headerRow();
        List<List<String>> rows =
                provider.valuesRange(accessToken, target.spreadsheetId(), range);
        return rows.isEmpty() ? List.of() : rows.getFirst();
    }

    private void validateHeaders(Item item, List<String> headers) {
        Map<String, Object> expected = values(item.getTargetHeaders());
        for (var entry : expected.entrySet()) {
            int index = columnIndex(entry.getKey()) - 1;
            String actual = index < headers.size() ? headers.get(index).trim() : "";
            if (!String.valueOf(entry.getValue()).trim().equals(actual))
                throw new IllegalStateException(
                        "目标表格列已变化，请重新保存项目日报模板："
                                + entry.getKey()
                                + "列应为“"
                                + entry.getValue()
                                + "”");
        }
    }

    private List<Object> appendRow(Map<String, Object> values) {
        int lastIndex =
                values.keySet().stream().mapToInt(this::columnIndex).max().orElseThrow();
        List<Object> row = new ArrayList<>(Collections.nCopies(lastIndex, ""));
        values.forEach((column, value) -> row.set(columnIndex(column) - 1, value));
        return row;
    }

    private void failAll(List<Item> items, String message) {
        for (Item item : items) {
            if (mapper.claimItem(item.getId()) == 1) mapper.failItem(item.getId(), message);
        }
    }

    private Map<String, Object> values(String value) {
        try {
            return json.readValue(value, new TypeReference<LinkedHashMap<String, Object>>() {});
        } catch (JsonProcessingException exception) {
            throw new IllegalStateException("Google日报推送快照读取失败", exception);
        }
    }

    private List<String> stringList(String value) {
        try {
            return json.readValue(value, new TypeReference<List<String>>() {});
        } catch (JsonProcessingException exception) {
            throw new IllegalStateException("Google日报唯一字段快照读取失败", exception);
        }
    }

    private int columnIndex(String column) {
        int result = 0;
        for (int index = 0; index < column.length(); index++)
            result = result * 26 + column.charAt(index) - 'A' + 1;
        return result;
    }

    private String quoteSheet(String sheetName) {
        return "'" + sheetName.replace("'", "''") + "'";
    }

    private String safeError(Throwable exception) {
        String message = exception.getMessage();
        if (message == null || message.isBlank()) message = "Google日报写入失败";
        return message.length() > 1000 ? message.substring(0, 1000) : message;
    }

    private record Target(
            String spreadsheetId,
            String sheetId,
            String sheetTitle,
            Integer headerRow,
            String uniqueKeyColumns) {
        private Target withSheetTitle(String currentSheetTitle) {
            return new Target(
                    spreadsheetId,
                    sheetId,
                    currentSheetTitle,
                    headerRow,
                    uniqueKeyColumns);
        }
    }
}
