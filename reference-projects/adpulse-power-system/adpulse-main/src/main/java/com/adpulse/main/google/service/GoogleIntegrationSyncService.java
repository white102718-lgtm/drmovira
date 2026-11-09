package com.adpulse.main.google.service;

import com.adpulse.main.google.client.GoogleProviderClient;
import com.adpulse.main.google.mapper.GoogleIntegrationMapper;
import com.adpulse.main.google.model.GoogleModels.Mapping;
import com.adpulse.main.google.model.GoogleModels.SyncData;
import com.adpulse.main.google.model.GoogleModels.SyncJob;
import com.fasterxml.jackson.core.type.TypeReference;
import com.fasterxml.jackson.databind.ObjectMapper;
import java.math.BigDecimal;
import java.time.LocalDate;
import java.time.LocalDateTime;
import java.time.LocalTime;
import java.time.ZoneId;
import java.time.format.DateTimeFormatter;
import java.util.HashMap;
import java.util.List;
import java.util.Locale;
import java.util.Map;
import lombok.extern.slf4j.Slf4j;
import org.springframework.scheduling.annotation.Scheduled;
import org.springframework.stereotype.Service;

/** Google Sheets同步队列消费与自动调度服务。 */
@Slf4j
@Service
public class GoogleIntegrationSyncService {
    private static final ZoneId BUSINESS_ZONE = ZoneId.of("Asia/Shanghai");
    private static final DateTimeFormatter TIME_FORMAT = DateTimeFormatter.ofPattern("HH:mm");
    private final GoogleIntegrationMapper mapper;
    private final GoogleIntegrationService integrationService;
    private final GoogleProviderClient provider;
    private final ObjectMapper objectMapper;

    public GoogleIntegrationSyncService(
            GoogleIntegrationMapper mapper,
            GoogleIntegrationService integrationService,
            GoogleProviderClient provider,
            ObjectMapper objectMapper) {
        this.mapper = mapper;
        this.integrationService = integrationService;
        this.provider = provider;
        this.objectMapper = objectMapper;
    }

    /** 周期消费等待执行的Google映射同步任务。 */
    @Scheduled(fixedDelayString = "${adpulse.google.sync-worker-delay-ms:5000}")
    public void consumePendingJobs() {
        for (SyncJob job : mapper.findPendingSyncJobs(10)) {
            if (mapper.claimSyncJob(job.getId()) != 1) continue;
            try {
                execute(job);
                mapper.completeSyncJob(job.getId());
            } catch (Exception exception) {
                String message = safeError(exception);
                mapper.failSyncJob(job.getId(), message);
                log.error(
                        "Google映射同步失败: jobId={}, mappingId={}",
                        job.getId(),
                        job.getBusinessId(),
                        exception);
            }
        }
    }

    /** 每分钟检查到期的自动同步配置并写入任务队列。 */
    @Scheduled(cron = "0 * * * * *", zone = "Asia/Shanghai")
    public void scheduleDueMappings() {
        LocalDateTime now = LocalDateTime.now(BUSINESS_ZONE);
        for (Mapping mapping : mapper.findAutoSyncMappings()) {
            if (!isDue(mapping, now)) continue;
            String businessId = mapping.getId().toString();
            if (mapper.countActiveSyncJobs(businessId) == 0)
                mapper.insertSyncJob(businessId, mapping.getUpdatedBy(), false);
        }
    }

    private void execute(SyncJob job) throws Exception {
        Long mappingId = Long.valueOf(job.getBusinessId());
        Mapping mapping = mapper.findMapping(mappingId);
        if (mapping == null || mapping.getEnableFlag() != 1)
            throw new IllegalStateException("映射配置不存在或已停用");
        if (mapping.getSyncDirection() == null || mapping.getSyncDirection() != 1)
            throw new IllegalStateException("当前Google授权仅支持从Sheets读取到系统");
        boolean fullSync = fullSync(job.getRequestPayload());
        String accessToken = integrationService.accessTokenForSync(mapping);
        List<String> sheets =
                objectMapper.readValue(mapping.getSheetNames(), new TypeReference<>() {});
        Map<String, List<FieldMapping>> mappings =
                objectMapper.readValue(mapping.getFieldMappings(), new TypeReference<>() {});
        DateRange range = fullSync ? DateRange.unbounded() : dateRange(mapping);
        int synchronizedRows = 0;
        for (String sheet : sheets) {
            synchronizedRows +=
                    syncSheet(
                            mapping,
                            sheet,
                            mappings.getOrDefault(sheet, List.of()),
                            accessToken,
                            range);
        }
        mapper.updateMappingLastSyncTime(mappingId);
        log.info(
                "Google映射{}同步完成: mappingId={}, rows={}",
                fullSync ? "全量" : "定时",
                mappingId,
                synchronizedRows);
    }

    private int syncSheet(
            Mapping mapping,
            String sheet,
            List<FieldMapping> fieldMappings,
            String accessToken,
            DateRange range) {
        Map<String, Integer> columns = new HashMap<>();
        for (FieldMapping field : fieldMappings) {
            Integer index = columnIndex(field.sheetColumn());
            if (field.systemField() != null && index != null)
                columns.put(field.systemField(), index);
        }
        List<List<String>> rows = provider.values(accessToken, mapping.getSpreadsheetId(), sheet);
        int count = 0;
        for (int index = 1; index < rows.size(); index++) {
            List<String> row = rows.get(index);
            LocalDate date = parseDate(cell(row, columns.get("startDate")));
            if (date == null || !range.contains(date)) continue;
            SyncData data = buildData(mapping.getId(), row, columns, date);
            if (data.getTaskName().isBlank()
                    || "#VALUE!".equals(data.getTaskName())
                    || data.getSubtaskName().isBlank()
                    || data.getSpendAmount() == null) continue;
            mapper.upsertSyncData(data);
            count++;
        }
        return count;
    }

    private SyncData buildData(
            Long mappingId, List<String> row, Map<String, Integer> columns, LocalDate date) {
        SyncData data = new SyncData();
        data.setMappingId(mappingId);
        data.setStartDate(date);
        data.setTaskName(text(cell(row, columns.get("taskName"))));
        data.setSubtaskName(text(cell(row, columns.get("subtaskName"))));
        data.setSpendAmount(decimal(cell(row, columns.get("spendAmount"))));
        data.setReturnAmount(decimal(cell(row, columns.get("returnAmount"))));
        data.setImpressions(integer(cell(row, columns.get("impressions"))));
        data.setClicks(integer(cell(row, columns.get("clicks"))));
        data.setRegistrations(integer(cell(row, columns.get("registrations"))));
        data.setPurchases(integer(cell(row, columns.get("purchases"))));
        data.setSubscriptions(integer(cell(row, columns.get("subscriptions"))));
        data.setMediaPlacement(media(cell(row, columns.get("mediaPlacement"))));
        return data;
    }

    private DateRange dateRange(Mapping mapping) throws Exception {
        LocalDate today = LocalDate.now(BUSINESS_ZONE);
        Map<String, Object> config =
                objectMapper.readValue(mapping.getDateRangeConfig(), new TypeReference<>() {});
        return switch (mapping.getDateRangeType() == null ? 3 : mapping.getDateRangeType()) {
            case 1 ->
                    new DateRange(
                            parseDate(String.valueOf(config.get("startDate"))),
                            parseDate(String.valueOf(config.get("endDate"))));
            case 2 -> {
                int days = config.get("days") instanceof Number number ? number.intValue() : 30;
                yield new DateRange(today.minusDays(days), today);
            }
            default -> new DateRange(today.withDayOfMonth(1), today);
        };
    }

    private boolean isDue(Mapping mapping, LocalDateTime now) {
        LocalDateTime last = mapping.getLastSyncTime();
        if (mapping.getSyncFrequency() == 3)
            return now.getMinute() == 0
                    && (last == null
                            || last.toLocalDate().isBefore(now.toLocalDate())
                            || last.getHour() < now.getHour());
        if (mapping.getSyncFrequency() != 2 || mapping.getSyncTime() == null) return false;
        LocalTime configured;
        try {
            configured = LocalTime.parse(mapping.getSyncTime().substring(0, 5), TIME_FORMAT);
        } catch (RuntimeException exception) {
            log.warn(
                    "Google映射同步时间无效: mappingId={}, syncTime={}",
                    mapping.getId(),
                    mapping.getSyncTime());
            return false;
        }
        return now.getHour() == configured.getHour()
                && now.getMinute() == configured.getMinute()
                && (last == null || last.toLocalDate().isBefore(now.toLocalDate()));
    }

    private boolean fullSync(String payload) {
        if (payload == null || payload.isBlank()) return true;
        try {
            return objectMapper.readTree(payload).path("fullSync").asBoolean(true);
        } catch (Exception exception) {
            return true;
        }
    }

    private Integer columnIndex(String column) {
        if (column == null || column.isBlank()) return null;
        int result = 0;
        for (char value : column.trim().toUpperCase(Locale.ROOT).toCharArray()) {
            if (value < 'A' || value > 'Z') return null;
            result = result * 26 + value - 'A' + 1;
        }
        return result - 1;
    }

    private String cell(List<String> row, Integer index) {
        return index == null || index < 0 || index >= row.size() ? null : row.get(index);
    }

    private LocalDate parseDate(String value) {
        if (value == null || value.isBlank() || "null".equals(value)) return null;
        try {
            String[] parts = value.trim().replace('/', '-').split("-");
            return LocalDate.of(
                    Integer.parseInt(parts[0]),
                    Integer.parseInt(parts[1]),
                    Integer.parseInt(parts[2]));
        } catch (RuntimeException exception) {
            return null;
        }
    }

    private BigDecimal decimal(String value) {
        if (value == null || value.isBlank()) return null;
        try {
            String normalized = value.replaceAll("[^0-9.-]", "");
            return normalized.isBlank() ? null : new BigDecimal(normalized);
        } catch (NumberFormatException exception) {
            return null;
        }
    }

    private Long integer(String value) {
        BigDecimal number = decimal(value);
        return number == null ? null : number.longValue();
    }

    private String text(String value) {
        return value == null ? "" : value.trim();
    }

    private String media(String value) {
        String media = text(value);
        return switch (media.toUpperCase(Locale.ROOT)) {
            case "GG", "GOOGLE" -> "Google";
            case "TT", "TIKTOK" -> "TikTok";
            case "KW", "KWAI" -> "Kwai";
            case "FB", "FACEBOOK外包" -> "Facebook外包";
            default -> media.isBlank() ? "Google" : media;
        };
    }

    private String safeError(Exception exception) {
        String message = exception.getMessage();
        if (message == null || message.isBlank()) message = exception.getClass().getSimpleName();
        return message.length() > 1000 ? message.substring(0, 1000) : message;
    }

    private record FieldMapping(String systemField, String sheetColumn, String sheetColumnName) {}

    private record DateRange(LocalDate start, LocalDate end) {
        private static DateRange unbounded() {
            return new DateRange(null, null);
        }

        private boolean contains(LocalDate date) {
            return (start == null || !date.isBefore(start)) && (end == null || !date.isAfter(end));
        }
    }
}
