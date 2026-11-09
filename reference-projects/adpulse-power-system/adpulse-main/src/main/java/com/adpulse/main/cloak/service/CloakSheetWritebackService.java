package com.adpulse.main.cloak.service;

import com.adpulse.main.cloak.dto.CloakViews;
import com.adpulse.main.cloak.mapper.CloakMapper;
import com.adpulse.main.cloak.model.CloakBatch;
import com.adpulse.main.cloak.model.CloakRecord;
import com.adpulse.main.deliveryreport.google.DeliveryReportGoogleServiceAccount;
import com.adpulse.main.google.client.GoogleProviderClient;
import com.adpulse.main.google.dto.GoogleDtos.SheetTab;
import com.adpulse.main.project.mapper.ProjectMapper;
import com.adpulse.main.project.model.Project;
import com.adpulse.system.common.security.CurrentUser;
import java.net.URI;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Locale;
import java.util.Map;
import java.util.Objects;
import java.util.Set;
import java.util.regex.Matcher;
import java.util.regex.Pattern;
import org.springframework.security.core.context.SecurityContextHolder;
import org.springframework.stereotype.Service;

/** 将已创建斗篷逐条回写到项目配置的代理线Google Sheet。 */
@Service
public class CloakSheetWritebackService {
    private static final Pattern SPREADSHEET_PATH =
            Pattern.compile("/spreadsheets/d/([a-zA-Z0-9_-]+)");
    private static final Pattern SHEET_GID = Pattern.compile("(?:^|[?#&])gid=(\\d+)");
    private static final List<String> AGENCY_LINE_HEADERS =
            List.of("代理线", "渠道号", "渠道名称");
    private static final String DELIVERY_URL_HEADER = "投放链接";
    private static final String CLOAK_URL_HEADER = "斗篷链接";

    private final CloakMapper cloakMapper;
    private final ProjectMapper projectMapper;
    private final CloakPersistenceService persistenceService;
    private final DeliveryReportGoogleServiceAccount serviceAccount;
    private final GoogleProviderClient googleProvider;

    public CloakSheetWritebackService(
            CloakMapper cloakMapper,
            ProjectMapper projectMapper,
            CloakPersistenceService persistenceService,
            DeliveryReportGoogleServiceAccount serviceAccount,
            GoogleProviderClient googleProvider) {
        this.cloakMapper = cloakMapper;
        this.projectMapper = projectMapper;
        this.persistenceService = persistenceService;
        this.serviceAccount = serviceAccount;
        this.googleProvider = googleProvider;
    }

    /** 回写一个成功批次；每条Google写入和本地结果相互隔离。 */
    public CloakViews.SheetWritebackResult writeback(Long batchId) {
        CurrentUser operator = currentUser();
        CloakBatch batch = cloakMapper.findSuccessfulBatchById(batchId);
        if (batch == null) {
            throw new CloakService.CloakException("斗篷批次不存在或尚未创建成功");
        }
        List<CloakRecord> records = cloakMapper.findRecordsByBatchId(batchId);
        if (records.isEmpty()) {
            throw new CloakService.CloakException("斗篷批次没有可回写的有效记录");
        }

        WritebackSummary summary = writeback(records, operator);
        return new CloakViews.SheetWritebackResult(
                batchId.toString(),
                summary.totalCount(),
                summary.successCount(),
                summary.failures().size(),
                summary.failures());
    }

    /** 回写管理列表选中的记录；支持记录来自不同项目和创建批次。 */
    public CloakViews.RecordSheetWritebackResult writebackRecords(List<Long> recordIds) {
        CurrentUser operator = currentUser();
        List<Long> distinctIds = recordIds.stream().distinct().toList();
        List<CloakRecord> records = cloakMapper.findRecordsByIds(distinctIds);
        if (records.size() != distinctIds.size()) {
            throw new CloakService.CloakException("部分斗篷记录不存在或已删除，请刷新后重试");
        }
        WritebackSummary summary = writeback(records, operator);
        return new CloakViews.RecordSheetWritebackResult(
                summary.totalCount(),
                summary.successCount(),
                summary.failures().size(),
                summary.failures());
    }

    private WritebackSummary writeback(List<CloakRecord> records, CurrentUser operator) {
        List<CloakViews.SheetWritebackFailure> failures = new ArrayList<>();
        int existingSuccesses =
                (int) records.stream().filter(this::writebackSucceeded).count();
        List<CloakRecord> pendingRecords =
                records.stream().filter(record -> !writebackSucceeded(record)).toList();
        if (pendingRecords.isEmpty()) {
            return new WritebackSummary(records.size(), existingSuccesses, List.of());
        }

        Map<Long, List<CloakRecord>> recordsByProject = new LinkedHashMap<>();
        for (CloakRecord record : pendingRecords) {
            recordsByProject
                    .computeIfAbsent(record.getProjectId(), ignored -> new ArrayList<>())
                    .add(record);
        }

        int successCount = existingSuccesses;
        for (var projectEntry : recordsByProject.entrySet()) {
            SheetContext context;
            try {
                context = sheetContext(projectEntry.getKey());
            } catch (RuntimeException exception) {
                String message = safeError(exception);
                for (CloakRecord record : projectEntry.getValue()) {
                    markFailure(record, message, operator.userId(), failures);
                }
                continue;
            }

            Set<Integer> occupiedRows = new LinkedHashSet<>();
            records.stream()
                    .filter(record -> projectEntry.getKey().equals(record.getProjectId()))
                    .filter(this::writebackSucceeded)
                    .map(CloakRecord::getSheetRowNumber)
                    .filter(Objects::nonNull)
                    .forEach(occupiedRows::add);
            for (CloakRecord record : projectEntry.getValue()) {
                try {
                    int rowNumber = context.headers().findUniqueRow(context.rows(), record);
                    if (!occupiedRows.add(rowNumber)) {
                        throw new CloakService.CloakException("同一表格行匹配到多条斗篷记录，无法安全回写");
                    }
                    googleProvider.updateValues(
                            context.accessToken(),
                            context.spreadsheetId(),
                            context.sheetTitle(),
                            rowNumber,
                            Map.of(context.headers().cloakColumn(), record.getPromotionUrl()));
                    persistenceService.markSheetWriteback(
                            record.getId(), true, "回写成功", rowNumber, operator.userId());
                    successCount++;
                } catch (RuntimeException exception) {
                    markFailure(record, safeError(exception), operator.userId(), failures);
                }
            }
        }
        return new WritebackSummary(records.size(), successCount, List.copyOf(failures));
    }

    private boolean writebackSucceeded(CloakRecord record) {
        return Integer.valueOf(1).equals(record.getSheetWritebackStatus());
    }

    private SheetContext sheetContext(Long projectId) {
        Project project = projectMapper.findProject(projectId);
        if (project == null) throw new CloakService.CloakException("项目不存在或已被删除");
        ParsedSheetLink link = parseSheetLink(project.getAgencyLineUrl());
        String accessToken = serviceAccount.accessToken();
        SheetTab sheet =
                googleProvider.sheets(accessToken, link.spreadsheetId()).stream()
                        .filter(item -> link.gid().equals(item.id()))
                        .findFirst()
                        .orElseThrow(
                                () ->
                                        new CloakService.CloakException(
                                                "代理线链接指定的Google Sheet页签不存在或无权访问"));
        List<List<String>> rows =
                googleProvider.values(accessToken, link.spreadsheetId(), sheet.title());
        if (rows.isEmpty()) {
            throw new CloakService.CloakException("代理线Google Sheet缺少第一行表头");
        }
        return new SheetContext(
                accessToken,
                link.spreadsheetId(),
                sheet.title(),
                HeaderMapping.from(rows.getFirst()),
                rows);
    }

    private ParsedSheetLink parseSheetLink(String value) {
        if (value == null || value.isBlank()) {
            throw new CloakService.CloakException("项目尚未配置代理线链接");
        }
        try {
            URI uri = URI.create(value.trim());
            if (!"docs.google.com".equalsIgnoreCase(uri.getHost())) {
                throw new CloakService.CloakException("项目代理线链接不是有效的Google Sheets链接");
            }
            Matcher spreadsheet = SPREADSHEET_PATH.matcher(uri.getPath());
            if (!spreadsheet.find()) {
                throw new CloakService.CloakException("项目代理线链接中缺少Spreadsheet ID");
            }
            String queryAndFragment =
                    "?"
                            + Objects.requireNonNullElse(uri.getRawQuery(), "")
                            + "#"
                            + Objects.requireNonNullElse(uri.getRawFragment(), "");
            Matcher gid = SHEET_GID.matcher(queryAndFragment);
            if (!gid.find()) {
                throw new CloakService.CloakException("项目代理线链接必须明确包含gid");
            }
            return new ParsedSheetLink(spreadsheet.group(1), gid.group(1));
        } catch (IllegalArgumentException exception) {
            throw new CloakService.CloakException("项目代理线链接格式不正确");
        }
    }

    private void markFailure(
            CloakRecord record,
            String message,
            Long operatorId,
            List<CloakViews.SheetWritebackFailure> failures) {
        persistenceService.markSheetWriteback(record.getId(), false, message, null, operatorId);
        failures.add(
                new CloakViews.SheetWritebackFailure(
                        record.getId().toString(), record.getAgencyLineName(), message));
    }

    private CurrentUser currentUser() {
        var authentication = SecurityContextHolder.getContext().getAuthentication();
        if (authentication == null || !(authentication.getPrincipal() instanceof CurrentUser user)) {
            throw new CloakService.CloakException("当前会话未认证");
        }
        return user;
    }

    private String safeError(Throwable exception) {
        String message = exception.getMessage();
        if (message == null || message.isBlank()) {
            message = "表格回写失败，请检查链接、权限和表格内容";
        }
        message = message.trim();
        return message.length() <= 1000 ? message : message.substring(0, 1000);
    }

    private static String normalizeHeader(String value) {
        return value == null
                ? ""
                : value.trim().toLowerCase(Locale.ROOT).replaceAll("[\\s_-]+", "");
    }

    private static String cell(List<String> row, int index) {
        return index < row.size() && row.get(index) != null ? row.get(index).trim() : "";
    }

    private static String columnName(int zeroBasedIndex) {
        StringBuilder result = new StringBuilder();
        int value = zeroBasedIndex + 1;
        while (value > 0) {
            value--;
            result.append((char) ('A' + value % 26));
            value /= 26;
        }
        return result.reverse().toString();
    }

    private record ParsedSheetLink(String spreadsheetId, String gid) {}

    private record WritebackSummary(
            int totalCount,
            int successCount,
            List<CloakViews.SheetWritebackFailure> failures) {}

    private record SheetContext(
            String accessToken,
            String spreadsheetId,
            String sheetTitle,
            HeaderMapping headers,
            List<List<String>> rows) {}

    private record HeaderMapping(int nameIndex, int deliveryUrlIndex, int cloakUrlIndex) {
        private static HeaderMapping from(List<String> headers) {
            Map<String, Integer> indexes = new LinkedHashMap<>();
            for (int index = 0; index < headers.size(); index++) {
                indexes.putIfAbsent(normalizeHeader(headers.get(index)), index);
            }
            Integer nameIndex =
                    AGENCY_LINE_HEADERS.stream()
                            .map(CloakSheetWritebackService::normalizeHeader)
                            .map(indexes::get)
                            .filter(Objects::nonNull)
                            .findFirst()
                            .orElse(null);
            if (nameIndex == null) {
                throw new CloakService.CloakException("第一行表头缺少代理线、渠道号或渠道名称");
            }
            Integer deliveryUrlIndex = indexes.get(normalizeHeader(DELIVERY_URL_HEADER));
            if (deliveryUrlIndex == null) {
                throw new CloakService.CloakException("第一行表头缺少投放链接");
            }
            Integer cloakUrlIndex = indexes.get(normalizeHeader(CLOAK_URL_HEADER));
            if (cloakUrlIndex == null) {
                throw new CloakService.CloakException("第一行表头缺少斗篷链接");
            }
            return new HeaderMapping(nameIndex, deliveryUrlIndex, cloakUrlIndex);
        }

        private int findUniqueRow(List<List<String>> rows, CloakRecord record) {
            List<Integer> matches = new ArrayList<>();
            for (int index = 1; index < rows.size(); index++) {
                List<String> row = rows.get(index);
                if (record.getAgencyLineName().equals(cell(row, nameIndex))
                        && record.getReallyUrl().equals(cell(row, deliveryUrlIndex))) {
                    matches.add(index + 1);
                }
            }
            if (matches.isEmpty()) {
                throw new CloakService.CloakException("未找到代理线名称和投放链接对应的表格行");
            }
            if (matches.size() > 1) {
                throw new CloakService.CloakException("代理线名称和投放链接匹配到多行，无法安全回写");
            }
            return matches.getFirst();
        }

        private String cloakColumn() {
            return columnName(cloakUrlIndex);
        }
    }
}
