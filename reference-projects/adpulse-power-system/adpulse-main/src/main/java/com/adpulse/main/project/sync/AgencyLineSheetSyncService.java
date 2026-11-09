package com.adpulse.main.project.sync;

import com.adpulse.main.deliveryreport.google.DeliveryReportGoogleServiceAccount;
import com.adpulse.main.google.client.GoogleProviderClient;
import com.adpulse.main.google.dto.GoogleDtos.SheetTab;
import com.adpulse.main.project.mapper.ProjectMapper;
import com.adpulse.main.project.model.Project;
import com.adpulse.main.project.service.ProjectService.ProjectException;
import com.adpulse.main.project.sync.AgencyLineSheetRowService.FieldValue;
import com.adpulse.main.project.sync.AgencyLineSheetRowService.SheetRow;
import com.adpulse.main.project.sync.AgencyLineSyncModels.Batch;
import com.adpulse.main.project.sync.AgencyLineSyncModels.Failure;
import com.adpulse.system.common.security.CurrentUser;
import java.net.URI;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Locale;
import java.util.Map;
import java.util.Objects;
import java.util.regex.Matcher;
import java.util.regex.Pattern;
import lombok.extern.slf4j.Slf4j;
import org.redisson.api.RLock;
import org.redisson.api.RedissonClient;
import org.springframework.scheduling.annotation.Scheduled;
import org.springframework.security.core.context.SecurityContextHolder;
import org.springframework.stereotype.Service;

/** 按项目代理线链接读取 Google Sheet，并逐行同步代理线主数据。 */
@Slf4j
@Service
public class AgencyLineSheetSyncService {
    private static final int MAX_DATA_ROWS = 1000;
    private static final String PROJECT_SYNC_LOCK_PREFIX =
            "adpulse:project:agency-line-sync:";
    private static final Pattern SPREADSHEET_PATH =
            Pattern.compile("/spreadsheets/d/([a-zA-Z0-9_-]+)");
    private static final Pattern SHEET_GID = Pattern.compile("(?:^|[?#&])gid=(\\d+)");

    private final AgencyLineSyncMapper mapper;
    private final ProjectMapper projectMapper;
    private final AgencyLineSheetRowService rowService;
    private final DeliveryReportGoogleServiceAccount serviceAccount;
    private final GoogleProviderClient googleProvider;
    private final RedissonClient redissonClient;

    public AgencyLineSheetSyncService(
            AgencyLineSyncMapper mapper,
            ProjectMapper projectMapper,
            AgencyLineSheetRowService rowService,
            DeliveryReportGoogleServiceAccount serviceAccount,
            GoogleProviderClient googleProvider,
            RedissonClient redissonClient) {
        this.mapper = mapper;
        this.projectMapper = projectMapper;
        this.rowService = rowService;
        this.serviceAccount = serviceAccount;
        this.googleProvider = googleProvider;
        this.redissonClient = redissonClient;
    }

    /** 每小时整点同步所有已配置链接且仍可修改的项目。 */
    @Scheduled(
            cron = "${adpulse.google.agency-line-sync-cron:0 0 * * * *}",
            zone = "Asia/Shanghai")
    public void synchronizeHourly() {
        for (Project project : mapper.findProjectsForAutomaticSync()) {
            try {
                synchronizeWithLock(project, "scheduled", null, "系统定时同步", false);
            } catch (RuntimeException exception) {
                log.error("项目代理线定时同步异常: projectId={}", project.getId(), exception);
            }
        }
    }

    /** 手动同步当前项目；同一项目已有运行中批次时拒绝重复触发。 */
    public AgencyLineSyncViews.Batch synchronizeManually(Long projectId) {
        Project project = requireProject(projectId);
        CurrentUser user = currentUser();
        Batch batch =
                synchronizeWithLock(
                        project, "manual", user.userId(), user.displayName(), true);
        return view(batch);
    }

    /** 分页查询当前项目同步历史。 */
    public AgencyLineSyncViews.Page<AgencyLineSyncViews.Batch> batches(
            Long projectId, int page, int pageSize) {
        requireProject(projectId);
        int safePage = Math.max(1, page);
        int safeSize = Math.min(100, Math.max(1, pageSize));
        List<AgencyLineSyncViews.Batch> items =
                mapper.findBatches(projectId, (safePage - 1) * safeSize, safeSize).stream()
                        .map(this::view)
                        .toList();
        return new AgencyLineSyncViews.Page<>(
                items, mapper.countBatches(projectId), safePage, safeSize);
    }

    /** 分页查询一个项目同步批次的失败行。 */
    public AgencyLineSyncViews.Page<AgencyLineSyncViews.Failure> failures(
            Long projectId, Long batchId, int page, int pageSize) {
        requireProject(projectId);
        if (mapper.findBatch(projectId, batchId) == null) {
            throw new ProjectException("代理线同步记录不存在");
        }
        int safePage = Math.max(1, page);
        int safeSize = Math.min(100, Math.max(1, pageSize));
        List<AgencyLineSyncViews.Failure> items =
                mapper.findFailures(batchId, (safePage - 1) * safeSize, safeSize).stream()
                        .map(this::view)
                        .toList();
        return new AgencyLineSyncViews.Page<>(
                items, mapper.countFailures(batchId), safePage, safeSize);
    }

    private Batch synchronizeProject(
            Project project, String triggerType, Long operatorId, String operatorName) {
        String link = trimToNull(project.getAgencyLineUrl());
        if (link == null) throw new ProjectException("项目尚未配置代理线链接");

        Batch batch = new Batch();
        batch.setProjectId(project.getId());
        batch.setTriggerType(triggerType);
        batch.setStatus("running");
        batch.setLinkSnapshot(link);
        batch.setTriggeredBy(operatorId);
        batch.setTriggeredByName(
                operatorName == null || operatorName.isBlank() ? "系统定时同步" : operatorName);
        mapper.insertBatch(batch);

        try {
            if (List.of("ended", "archived").contains(project.getStatus())) {
                throw new ProjectException("结束或归档项目不允许同步代理线");
            }
            ParsedSheetLink parsed = parseSheetLink(link);
            batch.setSpreadsheetId(parsed.spreadsheetId());
            batch.setSheetGid(parsed.gid());
            String accessToken = serviceAccount.accessToken();
            googleProvider.file(accessToken, parsed.spreadsheetId());
            SheetTab sheet =
                    googleProvider.sheets(accessToken, parsed.spreadsheetId()).stream()
                            .filter(item -> parsed.gid().equals(item.id()))
                            .findFirst()
                            .orElseThrow(() -> new ProjectException("链接指定的Google Sheet页签不存在或无权访问"));
            batch.setSheetTitle(sheet.title());
            List<List<String>> rows =
                    googleProvider.values(accessToken, parsed.spreadsheetId(), sheet.title());
            synchronizeRows(batch, project.getId(), rows, operatorId, operatorName);
        } catch (RuntimeException exception) {
            batch.setStatus("failed");
            batch.setErrorMessage(safeError(exception));
        }
        if (mapper.finishBatch(batch) != 1) {
            throw new IllegalStateException("代理线同步批次状态已变化");
        }
        return mapper.findBatch(project.getId(), batch.getId());
    }

    private Batch synchronizeWithLock(
            Project project,
            String triggerType,
            Long operatorId,
            String operatorName,
            boolean failWhenBusy) {
        RLock lock;
        boolean acquired;
        try {
            lock = redissonClient.getLock(PROJECT_SYNC_LOCK_PREFIX + project.getId());
            acquired = lock.tryLock();
        } catch (RuntimeException exception) {
            log.error("项目代理线同步锁获取失败: projectId={}", project.getId(), exception);
            throw new ProjectException("代理线同步锁服务暂不可用，请稍后重试");
        }
        if (!acquired) {
            if (failWhenBusy) {
                throw new ProjectException("当前项目已有代理线同步任务正在执行");
            }
            log.info("项目代理线定时同步已跳过，其他实例正在执行: projectId={}", project.getId());
            return null;
        }
        try {
            int interruptedBatches = mapper.failRunningBatches(project.getId());
            if (interruptedBatches > 0) {
                log.warn(
                        "已结束项目遗留的代理线同步批次: projectId={}, count={}",
                        project.getId(),
                        interruptedBatches);
            }
            return synchronizeProject(project, triggerType, operatorId, operatorName);
        } finally {
            releaseLock(lock, project.getId());
        }
    }

    private void releaseLock(RLock lock, Long projectId) {
        try {
            if (lock.isHeldByCurrentThread()) {
                lock.unlock();
            }
        } catch (RuntimeException exception) {
            log.error("项目代理线同步锁释放失败: projectId={}", projectId, exception);
        }
    }

    private void synchronizeRows(
            Batch batch,
            Long projectId,
            List<List<String>> rows,
            Long operatorId,
            String operatorName) {
        if (rows.isEmpty()) throw new ProjectException("Google Sheet缺少第一行表头");
        HeaderMapping headers = HeaderMapping.from(rows.getFirst());
        int meaningfulRows = 0;
        int successRows = 0;
        int failedRows = 0;
        for (int index = 1; index < rows.size(); index++) {
            ParsedRow parsed = headers.read(rows.get(index));
            if (!parsed.meaningful()) continue;
            meaningfulRows++;
            int sheetRowNumber = index + 1;
            if (meaningfulRows > MAX_DATA_ROWS) {
                recordFailure(batch.getId(), sheetRowNumber, parsed.name(), "单次同步最多处理1000条非空数据");
                failedRows++;
                break;
            }
            try {
                rowService.synchronize(
                        projectId,
                        batch.getId(),
                        sheetRowNumber,
                        parsed.input(),
                        operatorId,
                        operatorName);
                successRows++;
            } catch (RuntimeException exception) {
                recordFailure(
                        batch.getId(), sheetRowNumber, parsed.name(), safeError(exception));
                failedRows++;
            }
        }
        batch.setTotalRows(meaningfulRows);
        batch.setSuccessRows(successRows);
        batch.setFailedRows(failedRows);
        batch.setStatus(
                failedRows == 0 ? "success" : successRows == 0 ? "failed" : "partial");
    }

    private void recordFailure(Long batchId, int rowNumber, String lineName, String reason) {
        Failure failure = new Failure();
        failure.setBatchId(batchId);
        failure.setSheetRowNumber(rowNumber);
        failure.setAgencyLineName(trimToLength(trimToNull(lineName), 80));
        failure.setFailureReason(trimToLength(reason, 1000));
        mapper.insertFailure(failure);
    }

    private ParsedSheetLink parseSheetLink(String value) {
        try {
            URI uri = URI.create(value.trim());
            if (!"docs.google.com".equalsIgnoreCase(uri.getHost())) {
                throw new ProjectException("代理线链接不是有效的Google Sheets链接");
            }
            Matcher spreadsheet = SPREADSHEET_PATH.matcher(uri.getPath());
            if (!spreadsheet.find()) throw new ProjectException("代理线链接中缺少Spreadsheet ID");
            String queryAndFragment =
                    "?"
                            + Objects.requireNonNullElse(uri.getRawQuery(), "")
                            + "#"
                            + Objects.requireNonNullElse(uri.getRawFragment(), "");
            Matcher gid = SHEET_GID.matcher(queryAndFragment);
            if (!gid.find()) throw new ProjectException("代理线链接必须明确包含gid");
            return new ParsedSheetLink(spreadsheet.group(1), gid.group(1));
        } catch (IllegalArgumentException exception) {
            throw new ProjectException("代理线链接格式不正确");
        }
    }

    private Project requireProject(Long projectId) {
        Project project = projectMapper.findProject(projectId);
        if (project == null) throw new ProjectException("项目不存在或已被删除");
        return project;
    }

    private CurrentUser currentUser() {
        var authentication = SecurityContextHolder.getContext().getAuthentication();
        if (authentication == null || !(authentication.getPrincipal() instanceof CurrentUser user)) {
            throw new ProjectException("当前会话未认证");
        }
        return user;
    }

    private AgencyLineSyncViews.Batch view(Batch batch) {
        return new AgencyLineSyncViews.Batch(
                batch.getId().toString(),
                batch.getProjectId().toString(),
                batch.getTriggerType(),
                batch.getStatus(),
                batch.getLinkSnapshot(),
                batch.getSheetTitle(),
                batch.getTotalRows(),
                batch.getSuccessRows(),
                batch.getFailedRows(),
                batch.getErrorMessage(),
                batch.getTriggeredBy() == null ? null : batch.getTriggeredBy().toString(),
                batch.getTriggeredByName(),
                batch.getStartedAt(),
                batch.getFinishedAt());
    }

    private AgencyLineSyncViews.Failure view(Failure failure) {
        return new AgencyLineSyncViews.Failure(
                failure.getId().toString(),
                failure.getSheetRowNumber(),
                failure.getAgencyLineName(),
                failure.getFailureReason(),
                failure.getCreatedAt());
    }

    private String safeError(Throwable exception) {
        String message = trimToNull(exception.getMessage());
        return trimToLength(message == null ? "同步失败，请检查链接、权限和表格内容" : message, 1000);
    }

    private String trimToLength(String value, int maxLength) {
        return value == null || value.length() <= maxLength ? value : value.substring(0, maxLength);
    }

    private String trimToNull(String value) {
        return value == null || value.isBlank() ? null : value.trim();
    }

    private record ParsedSheetLink(String spreadsheetId, String gid) {}

    private record ParsedRow(boolean meaningful, String name, SheetRow input) {}

    private enum Field {
        NAME(List.of("代理线", "渠道号", "渠道名称", "name", "agent_line")),
        PLATFORM(List.of("投放平台", "platform", "media_platform")),
        TYPE(List.of("类型", "type")),
        PIXEL_NAME(List.of("像素名称", "pixel_name", "pixelName")),
        PIXEL_ID(List.of("像素id", "pixel_id", "pixelId")),
        TOKEN(List.of("token")),
        TEST_CODE(List.of("测试代码", "test_code", "testCode")),
        DELIVERY_URL(List.of("投放链接", "package_url", "deliveryUrl")),
        OPTIMIZER_NAME(List.of("投手", "优化师", "投放师", "optimizer", "optimizerName")),
        CLOAK_URL(List.of("斗篷链接", "cloak_url", "cloakUrl"));

        private final List<String> aliases;

        Field(List<String> aliases) {
            this.aliases = aliases;
        }
    }

    private static final class HeaderMapping {
        private final Map<Field, Integer> indexes;

        private HeaderMapping(Map<Field, Integer> indexes) {
            this.indexes = indexes;
        }

        private static HeaderMapping from(List<String> headers) {
            Map<String, Integer> headerIndexes = new LinkedHashMap<>();
            for (int index = 0; index < headers.size(); index++) {
                headerIndexes.putIfAbsent(normalizeHeader(headers.get(index)), index);
            }
            Map<Field, Integer> indexes = new LinkedHashMap<>();
            for (Field field : Field.values()) {
                for (String alias : field.aliases) {
                    Integer index = headerIndexes.get(normalizeHeader(alias));
                    if (index != null) {
                        indexes.put(field, index);
                        break;
                    }
                }
            }
            if (!indexes.containsKey(Field.NAME)) {
                throw new ProjectException("第一行表头缺少代理线、渠道号或渠道名称");
            }
            return new HeaderMapping(indexes);
        }

        private ParsedRow read(List<String> row) {
            boolean meaningful =
                    indexes.values().stream().map(index -> cell(row, index)).anyMatch(value -> !value.isBlank());
            String name = value(row, Field.NAME);
            SheetRow input =
                    new SheetRow(
                            name,
                            value(row, Field.PLATFORM),
                            field(row, Field.TYPE),
                            field(row, Field.PIXEL_NAME),
                            field(row, Field.PIXEL_ID),
                            field(row, Field.TOKEN),
                            field(row, Field.TEST_CODE),
                            field(row, Field.DELIVERY_URL),
                            field(row, Field.OPTIMIZER_NAME),
                            field(row, Field.CLOAK_URL));
            return new ParsedRow(meaningful, name, input);
        }

        private String value(List<String> row, Field field) {
            Integer index = indexes.get(field);
            return index == null ? "" : cell(row, index);
        }

        private FieldValue field(List<String> row, Field field) {
            Integer index = indexes.get(field);
            return index == null ? FieldValue.absent() : new FieldValue(true, cell(row, index));
        }

        private static String cell(List<String> row, int index) {
            return index < row.size() && row.get(index) != null ? row.get(index).trim() : "";
        }

        private static String normalizeHeader(String value) {
            return value == null
                    ? ""
                    : value.trim()
                            .toLowerCase(Locale.ROOT)
                            .replaceAll("[\\s_-]+", "");
        }
    }
}
