package com.adpulse.main.deliveryreport.google;

import com.adpulse.main.deliveryreport.DeliveryReportException;
import com.adpulse.main.deliveryreport.DeliveryReportService;
import com.adpulse.main.deliveryreport.DeliveryReportTypes.Metrics;
import com.adpulse.main.deliveryreport.DeliveryReportTypes.PushSourceRow;
import com.adpulse.main.deliveryreport.google.DeliveryReportGooglePushDtos.*;
import com.adpulse.main.deliveryreport.google.DeliveryReportGooglePushModels.Batch;
import com.adpulse.main.deliveryreport.google.DeliveryReportGooglePushModels.Item;
import com.adpulse.main.deliveryreport.google.DeliveryReportGooglePushModels.Template;
import com.adpulse.main.google.client.GoogleProviderClient;
import com.adpulse.main.google.dto.GoogleDtos.DriveFile;
import com.adpulse.main.google.dto.GoogleDtos.SheetTab;
import com.adpulse.system.common.security.CurrentUser;
import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.core.type.TypeReference;
import com.fasterxml.jackson.databind.ObjectMapper;
import java.math.BigDecimal;
import java.net.URI;
import java.util.*;
import java.util.function.Function;
import java.util.function.Supplier;
import java.util.regex.Matcher;
import java.util.regex.Pattern;
import java.util.stream.Collectors;
import org.springframework.dao.DuplicateKeyException;
import org.springframework.security.core.context.SecurityContextHolder;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

/** 项目Google日报模板、可信预览和推送批次编排服务。 */
@Service
public class DeliveryReportGooglePushService {
    private static final Pattern SPREADSHEET_PATH =
            Pattern.compile("(?:/a/[^/]+)?/spreadsheets/d/([A-Za-z0-9_-]+)");
    private static final Pattern SHEET_GID = Pattern.compile("(?:^|[?&#])gid=(\\d+)(?:$|[&#])");
    private static final List<FieldDefinition> FIELD_DEFINITIONS =
            List.of(
                    new FieldDefinition("date", "日期", false, "date"),
                    new FieldDefinition("reporterName", "投手姓名", false, "string"),
                    new FieldDefinition("projectName", "项目", false, "string"),
                    new FieldDefinition("agencyLineName", "代理线", false, "string"),
                    new FieldDefinition("platform", "平台", false, "string"),
                    new FieldDefinition("actualSpend", "实际消耗", false, "number"),
                    new FieldDefinition("dailySpend", "日报消耗", false, "number"),
                    new FieldDefinition("impressions", "展示", false, "number"),
                    new FieldDefinition("clicks", "点击", false, "number"),
                    new FieldDefinition("installs", "账户内安装", false, "number"),
                    new FieldDefinition("registrations", "账户内注册", false, "number"),
                    new FieldDefinition("firstPurchases", "账户内首购", false, "number"),
                    new FieldDefinition("adjustmentAmount", "调整金额", false, "number"),
                    new FieldDefinition("secondaryDeduction", "二次核减", false, "number"),
                    new FieldDefinition("adjustmentType", "调整承担", false, "string"),
                    new FieldDefinition("returnSpend", "含回流消耗", false, "number"),
                    new FieldDefinition("returnIncrease", "回流增加额", false, "number"),
                    new FieldDefinition("remark", "备注", false, "string"));
    private static final Set<String> EDITABLE_FIELDS =
            FIELD_DEFINITIONS.stream()
                    .map(FieldDefinition::field)
                    .collect(Collectors.toUnmodifiableSet());

    private final DeliveryReportGooglePushMapper mapper;
    private final DeliveryReportGooglePushBatchStore batchStore;
    private final DeliveryReportService deliveryReportService;
    private final DeliveryReportGoogleServiceAccount serviceAccount;
    private final GoogleProviderClient googleProvider;
    private final ObjectMapper json;

    public DeliveryReportGooglePushService(
            DeliveryReportGooglePushMapper mapper,
            DeliveryReportGooglePushBatchStore batchStore,
            DeliveryReportService deliveryReportService,
            DeliveryReportGoogleServiceAccount serviceAccount,
            GoogleProviderClient googleProvider,
            ObjectMapper json) {
        this.mapper = mapper;
        this.batchStore = batchStore;
        this.deliveryReportService = deliveryReportService;
        this.serviceAccount = serviceAccount;
        this.googleProvider = googleProvider;
        this.json = json;
    }

    /** 返回模板编辑器可选择的固定日报字段。 */
    public List<FieldDefinition> fields() {
        currentUser();
        return FIELD_DEFINITIONS;
    }

    /** 返回需要被授予目标Google表格编辑权限的服务账户。 */
    public ServiceAccountInfo serviceAccount() {
        currentUser();
        return new ServiceAccountInfo(serviceAccount.email());
    }

    /** 查询已共享给日报服务账户的Google Sheets文件。 */
    public List<DriveFile> files(String keyword) {
        currentUser();
        return googleAccess(
                () -> googleProvider.files(serviceAccount.accessToken(), keyword),
                "读取共享表格失败，请确认已将表格共享给日报服务账户");
    }

    /** 查询服务账户可访问Spreadsheet中的页签。 */
    public List<SheetTab> sheets(String fileId) {
        currentUser();
        return googleAccess(
                () -> googleProvider.sheets(serviceAccount.accessToken(), fileId),
                "读取Google页签失败，请确认服务账户有权访问该表格");
    }

    /** 根据项目日报链接定位服务账户可访问的Spreadsheet和Sheet。 */
    public ProjectTarget projectTarget(Long projectId) {
        currentUser();
        if (mapper.countActiveProject(projectId) != 1)
            throw new DeliveryReportException("所选项目不存在或已删除");
        String dailyReportUrl = mapper.findProjectDailyReportUrl(projectId);
        if (dailyReportUrl == null || dailyReportUrl.isBlank())
            throw new DeliveryReportException(
                    "该项目未配置客户日报链接，无法确定Google表格和目标页签");
        ParsedSheetLink link = parseSheetLink(dailyReportUrl);
        if (link.sheetId() == null)
            throw new DeliveryReportException("项目日报链接未指定目标页签，无法确定唯一写入目标");
        return googleAccess(
                () -> {
                    String accessToken = serviceAccount.accessToken();
                    DriveFile spreadsheet = googleProvider.file(accessToken, link.spreadsheetId());
                    List<SheetTab> targetSheets =
                            googleProvider.sheets(accessToken, link.spreadsheetId());
                    boolean sheetExists =
                            targetSheets.stream()
                                    .anyMatch(sheet -> link.sheetId().equals(sheet.id()));
                    if (!sheetExists)
                        throw new DeliveryReportException("项目日报链接指定的目标页签不存在");
                    return new ProjectTarget(
                            true,
                            dailyReportUrl,
                            spreadsheet,
                            targetSheets,
                            link.sheetId(),
                            "已根据项目日报链接确定Google表格和目标页签");
                },
                "无法通过项目日报链接访问Google表格，请确认已共享给日报服务账户");
    }

    /** 查询目标页签指定行的字段。 */
    public List<String> columns(String fileId, String sheetName, Integer headerRow) {
        currentUser();
        if (headerRow == null || headerRow < 1 || headerRow > 100)
            throw new DeliveryReportException("表头行必须在1到100之间");
        return googleAccess(
                () ->
                        googleProvider.columns(
                                serviceAccount.accessToken(), fileId, sheetName, headerRow),
                "读取Google表头失败，请确认服务账户有权访问该表格");
    }

    /** 查询全部项目Google日报模板。 */
    public List<TemplateView> templates() {
        currentUser();
        return mapper.findTemplates().stream().map(this::view).toList();
    }

    /** 创建一个项目唯一的Google日报模板。 */
    public String createTemplate(TemplateSave request) {
        CurrentUser user = currentUser();
        ProjectTarget target = projectTarget(request.projectId());
        List<FieldMapping> mappings = validateTemplate(null, request);
        Template template = model(null, request, mappings, target, user.userId());
        template.setCreatedBy(user.userId());
        try {
            mapper.insertTemplate(template);
        } catch (DuplicateKeyException exception) {
            throw new DeliveryReportException("该项目已经配置Google日报模板");
        }
        return template.getId().toString();
    }

    /** 更新模板时仍保持一个项目只能存在一个有效模板。 */
    public void updateTemplate(Long id, TemplateSave request) {
        CurrentUser user = currentUser();
        if (mapper.findTemplate(id) == null) throw new DeliveryReportException("项目日报模板不存在");
        ProjectTarget target = projectTarget(request.projectId());
        List<FieldMapping> mappings = validateTemplate(id, request);
        mapper.updateTemplate(model(id, request, mappings, target, user.userId()));
    }

    /** 软删除项目Google日报模板，历史推送快照不受影响。 */
    public void deleteTemplate(Long id) {
        CurrentUser user = currentUser();
        if (mapper.deleteTemplate(id, System.currentTimeMillis(), user.userId()) != 1)
            throw new DeliveryReportException("项目日报模板不存在");
    }

    /** 按项目分组生成只读预览，任何项目缺少有效模板都会整体阻止推送。 */
    public Preview preview(ReportSelection request) {
        List<PushSourceRow> rows = deliveryReportService.pushRows(request.reportIds());
        Map<Long, Template> templates = requiredTemplates(rows);
        return preview(rows, templates);
    }

    /** 将预览所依据的服务端数据固化为可恢复推送批次。 */
    public PushBatchView createBatch(ReportSelection request) {
        CurrentUser user = currentUser();
        serviceAccount.accessToken();
        List<PushSourceRow> rows = deliveryReportService.pushRows(request.reportIds());
        Map<Long, Template> templates = requiredTemplates(rows);
        List<Item> items = new ArrayList<>();
        Map<String, Set<List<String>>> uniqueKeysByTarget = new HashMap<>();
        for (PushSourceRow row : rows) {
            Template template = templates.get(Long.valueOf(row.projectId()));
            List<FieldMapping> mappings = mappings(template);
            Map<String, Object> source = sourceValues(row);
            Map<String, Object> target = new LinkedHashMap<>();
            Map<String, String> targetHeaders = new LinkedHashMap<>();
            for (FieldMapping mapping : mappings) {
                Object value = source.get(mapping.systemField());
                requireValue(mapping, value, row.reportId());
                target.put(mapping.targetColumn(), Objects.requireNonNullElse(value, ""));
                targetHeaders.put(mapping.targetColumn(), mapping.targetHeader());
            }
            List<String> uniqueKey = uniqueKey(mappings, source, row.reportId());
            if (!uniqueKeysByTarget
                    .computeIfAbsent(uniqueTarget(template, mappings), ignored -> new HashSet<>())
                    .add(uniqueKey))
                throw new DeliveryReportException(
                        "所选日报按模板“" + template.getTemplateName() + "”的唯一字段产生重复值");
            Item item = new Item();
            item.setReportId(Long.valueOf(row.reportId()));
            item.setProjectId(Long.valueOf(row.projectId()));
            item.setTemplateId(template.getId());
            item.setSpreadsheetId(template.getSpreadsheetId());
            item.setSheetId(template.getSheetId());
            item.setSheetTitle(template.getSheetTitle());
            item.setHeaderRow(template.getHeaderRow());
            item.setFieldValues(write(target));
            item.setTargetHeaders(write(targetHeaders));
            item.setUniqueKeyColumns(
                    write(
                            mappings.stream()
                                    .filter(FieldMapping::uniqueKey)
                                    .sorted(Comparator.comparing(FieldMapping::targetColumn))
                                    .map(FieldMapping::targetColumn)
                                    .toList()));
            item.setReportIdColumn(null);
            items.add(item);
        }
        return batch(batchStore.create(user.userId(), items));
    }

    /** 查询当前用户发起的推送批次及逐条结果。 */
    public PushBatchView batch(Long id) {
        Batch batch = mapper.findBatchForUser(id, currentUser().userId());
        if (batch == null) throw new DeliveryReportException("推送批次不存在");
        return batchView(batch, mapper.findItems(id));
    }

    /** 查询当前用户最近二十个推送批次，明细在打开单个批次时按需加载。 */
    public List<PushBatchView> recentBatches() {
        return mapper.findBatchesForUser(currentUser().userId(), 20).stream()
                .map(batch -> batchView(batch, List.of()))
                .toList();
    }

    /** 将部分失败或全部失败的明细重新放回待执行队列。 */
    @Transactional
    public PushBatchView retry(Long id) {
        Long userId = currentUser().userId();
        Batch batch = mapper.findBatchForUser(id, userId);
        if (batch == null) throw new DeliveryReportException("推送批次不存在");
        if (batch.getStatus() != 3 && batch.getStatus() != 4)
            throw new DeliveryReportException("只有失败或部分失败的批次可以重试");
        if (mapper.resetBatchForRetry(id, userId) != 1)
            throw new DeliveryReportException("推送批次状态已变化，请刷新后重试");
        mapper.retryFailedItems(id);
        return batch(id);
    }

    private Preview preview(List<PushSourceRow> rows, Map<Long, Template> templates) {
        Map<Long, List<PushSourceRow>> grouped =
                rows.stream()
                        .collect(
                                Collectors.groupingBy(
                                        row -> Long.valueOf(row.projectId()), LinkedHashMap::new, Collectors.toList()));
        List<PreviewGroup> groups = new ArrayList<>();
        Map<String, Set<List<String>>> uniqueKeysByTarget = new HashMap<>();
        for (var entry : grouped.entrySet()) {
            Template template = templates.get(entry.getKey());
            List<FieldMapping> mappings = mappings(template);
            List<PreviewRow> previewRows = new ArrayList<>();
            Set<List<String>> uniqueKeys =
                    uniqueKeysByTarget.computeIfAbsent(
                            uniqueTarget(template, mappings), ignored -> new HashSet<>());
            for (PushSourceRow row : entry.getValue()) {
                Map<String, Object> source = sourceValues(row);
                Map<String, Object> values = new LinkedHashMap<>();
                for (FieldMapping mapping : mappings) {
                    Object value = source.get(mapping.systemField());
                    requireValue(mapping, value, row.reportId());
                    values.put(mapping.systemField(), Objects.requireNonNullElse(value, ""));
                }
                if (!uniqueKeys.add(uniqueKey(mappings, source, row.reportId())))
                    throw new DeliveryReportException(
                            "所选日报按模板“" + template.getTemplateName() + "”的唯一字段产生重复值");
                previewRows.add(new PreviewRow(row.reportId(), values));
            }
            groups.add(
                    new PreviewGroup(
                            entry.getKey().toString(),
                            entry.getValue().getFirst().projectName(),
                            template.getId().toString(),
                            template.getTemplateName(),
                            template.getSpreadsheetName(),
                            template.getSheetTitle(),
                            mappings,
                            previewRows));
        }
        return new Preview(rows.size(), groups);
    }

    private Map<Long, Template> requiredTemplates(List<PushSourceRow> rows) {
        Map<Long, Template> templates =
                mapper.findTemplates().stream()
                        .collect(Collectors.toMap(Template::getProjectId, Function.identity()));
        Map<Long, Boolean> available = new HashMap<>();
        List<String> missing = new ArrayList<>();
        for (PushSourceRow row : rows) {
            Long projectId = Long.valueOf(row.projectId());
            boolean ready =
                    available.computeIfAbsent(
                            projectId,
                            ignored -> {
                                Template template = templates.get(projectId);
                                return template != null && template.getEnableFlag() == 1;
                            });
            if (!ready) missing.add(row.projectName());
        }
        if (!missing.isEmpty())
            throw new DeliveryReportException(
                    "以下项目未配置有效的Google日报模板："
                            + String.join("、", missing.stream().distinct().toList()));
        return templates;
    }

    private List<FieldMapping> validateTemplate(Long id, TemplateSave request) {
        if (mapper.countActiveProject(request.projectId()) != 1)
            throw new DeliveryReportException("所选项目不存在或已删除");
        Template sameProject = mapper.findTemplateByProject(request.projectId());
        if (sameProject != null && !sameProject.getId().equals(id))
            throw new DeliveryReportException("该项目已经配置Google日报模板");
        Set<String> fields = new HashSet<>();
        Set<String> columns = new HashSet<>();
        List<FieldMapping> normalized = new ArrayList<>();
        for (FieldMapping mapping : request.fieldMappings()) {
            FieldDefinition definition =
                    FIELD_DEFINITIONS.stream()
                            .filter(field -> field.field().equals(mapping.systemField()))
                            .findFirst()
                            .orElse(null);
            if (!EDITABLE_FIELDS.contains(mapping.systemField()) || definition == null)
                throw new DeliveryReportException("存在不支持的日报映射字段");
            if (!fields.add(mapping.systemField()))
                throw new DeliveryReportException("同一个日报字段不能重复映射");
            if (!columns.add(mapping.targetColumn()))
                throw new DeliveryReportException("同一个Google列不能映射多个日报字段");
            if (columnIndex(mapping.targetColumn()) > 702)
                throw new DeliveryReportException("目标列不能超过ZZ列");
            normalized.add(
                    new FieldMapping(
                            mapping.systemField(),
                            mapping.targetColumn(),
                            mapping.targetHeader(),
                            false,
                            mapping.uniqueKey()));
        }
        if (normalized.isEmpty()) throw new DeliveryReportException("请至少配置一个日报字段映射");
        if (normalized.stream().noneMatch(FieldMapping::uniqueKey))
            throw new DeliveryReportException("请至少选择一个字段作为唯一值");
        return normalized;
    }

    private Template model(
            Long id,
            TemplateSave request,
            List<FieldMapping> mappings,
            ProjectTarget target,
            Long actorId) {
        SheetTab sheet =
                target.sheets().stream()
                        .filter(item -> target.sheetId().equals(item.id()))
                        .findFirst()
                        .orElseThrow(
                                () ->
                                        new DeliveryReportException(
                                                "项目日报链接指定的目标页签不存在"));
        Template template = new Template();
        template.setId(id);
        template.setProjectId(request.projectId());
        template.setTemplateName(request.templateName().trim());
        template.setSpreadsheetId(target.spreadsheet().id());
        template.setSpreadsheetName(target.spreadsheet().name());
        template.setSheetId(sheet.id());
        template.setSheetTitle(sheet.title());
        template.setHeaderRow(request.headerRow());
        template.setFieldMappings(write(normalizeMappings(mappings)));
        template.setEnableFlag(request.enableFlag());
        template.setUpdatedBy(actorId);
        return template;
    }

    private TemplateView view(Template template) {
        return new TemplateView(
                template.getId().toString(),
                template.getProjectId().toString(),
                template.getProjectName(),
                template.getTemplateName(),
                template.getSpreadsheetId(),
                template.getSpreadsheetName(),
                template.getSheetId(),
                template.getSheetTitle(),
                template.getHeaderRow(),
                mappings(template),
                template.getEnableFlag(),
                template.getUpdatedAt());
    }

    private PushBatchView batchView(Batch batch, List<Item> items) {
        return new PushBatchView(
                batch.getId().toString(),
                batch.getStatus(),
                batch.getTotalCount(),
                batch.getSuccessCount(),
                batch.getFailedCount(),
                batch.getErrorMessage(),
                batch.getStartedAt(),
                batch.getFinishedAt(),
                batch.getCreatedAt(),
                items.stream()
                        .map(
                                item ->
                                        new PushItemView(
                                                item.getId().toString(),
                                                item.getReportId().toString(),
                                                item.getProjectId().toString(),
                                                item.getStatus(),
                                                item.getTargetRow(),
                                                item.getAttemptCount(),
                                                item.getErrorMessage()))
                        .toList());
    }

    private Map<String, Object> sourceValues(PushSourceRow row) {
        Metrics metrics = row.metrics();
        Map<String, Object> values = new LinkedHashMap<>();
        values.put("reportId", row.reportId());
        values.put("date", row.date().toString());
        values.put("projectName", row.projectName());
        values.put("reporterName", row.reporterName());
        values.put("departmentName", row.departmentName());
        values.put("agencyLineName", row.agencyLineName());
        values.put("platform", row.platform());
        values.put("actualSpend", row.actualSpend());
        values.put("dailySpend", metrics.dailySpend());
        values.put("impressions", metrics.impressions());
        values.put("clicks", metrics.clicks());
        values.put("installs", metrics.installs());
        values.put("registrations", metrics.registrations());
        values.put("firstPurchases", metrics.firstPurchases());
        values.put("adjustmentAmount", metrics.adjustmentAmount());
        values.put("secondaryDeduction", metrics.secondaryDeduction());
        values.put("adjustmentType", metrics.adjustmentType());
        values.put("returnSpend", row.actualSpend().subtract(metrics.adjustmentAmount()));
        values.put("returnIncrease", row.actualSpend().subtract(metrics.dailySpend()));
        values.put("remark", metrics.remark());
        values.put("accountIds", String.join(",", row.accountIds()));
        values.put("campaignIds", String.join(",", row.campaignIds()));
        return values;
    }

    private void requireValue(FieldMapping mapping, Object value, String reportId) {
        if (mapping.uniqueKey() && (value == null || value.toString().isBlank()))
            throw new DeliveryReportException(
                    "日报" + reportId + "的唯一字段“" + mapping.targetHeader() + "”为空");
    }

    private List<String> uniqueKey(
            List<FieldMapping> mappings, Map<String, Object> source, String reportId) {
        List<FieldMapping> uniqueMappings =
                mappings.stream()
                        .filter(FieldMapping::uniqueKey)
                        .sorted(Comparator.comparing(FieldMapping::targetColumn))
                        .toList();
        if (uniqueMappings.isEmpty()) throw new DeliveryReportException("项目日报模板未配置唯一字段");
        return uniqueMappings.stream()
                .map(
                        mapping -> {
                            Object value = source.get(mapping.systemField());
                            requireValue(mapping, value, reportId);
                            return normalizeKeyPart(value);
                        })
                .toList();
    }

    private String normalizeKeyPart(Object value) {
        if (value instanceof Number number)
            return new BigDecimal(number.toString()).stripTrailingZeros().toPlainString();
        return value.toString().trim();
    }

    private String uniqueTarget(Template template, List<FieldMapping> mappings) {
        return template.getSpreadsheetId()
                + "\u0000"
                + template.getSheetId()
                + "\u0000"
                + mappings.stream()
                        .filter(FieldMapping::uniqueKey)
                        .sorted(Comparator.comparing(FieldMapping::targetColumn))
                        .map(FieldMapping::targetColumn)
                        .collect(Collectors.joining(","));
    }

    private ParsedSheetLink parseSheetLink(String value) {
        try {
            URI uri = URI.create(value.trim());
            if (!("https".equalsIgnoreCase(uri.getScheme())
                            || "http".equalsIgnoreCase(uri.getScheme()))
                    || !"docs.google.com".equalsIgnoreCase(uri.getHost()))
                throw new DeliveryReportException("项目日报链接不是有效的Google Sheets链接");
            Matcher spreadsheet = SPREADSHEET_PATH.matcher(uri.getPath());
            if (!spreadsheet.find())
                throw new DeliveryReportException("项目日报链接中缺少Spreadsheet ID");
            String queryAndFragment =
                    "?"
                            + Objects.requireNonNullElse(uri.getRawQuery(), "")
                            + "#"
                            + Objects.requireNonNullElse(uri.getRawFragment(), "");
            Matcher gid = SHEET_GID.matcher(queryAndFragment);
            return new ParsedSheetLink(
                    spreadsheet.group(1), gid.find() ? gid.group(1) : null);
        } catch (IllegalArgumentException exception) {
            throw new DeliveryReportException("项目日报链接格式不正确", exception);
        }
    }

    private List<FieldMapping> mappings(Template template) {
        try {
            List<FieldMapping> stored =
                    json.readValue(template.getFieldMappings(), new TypeReference<>() {});
            return normalizeMappings(stored).stream()
                    .filter(mapping -> EDITABLE_FIELDS.contains(mapping.systemField()))
                    .toList();
        } catch (JsonProcessingException exception) {
            throw new IllegalStateException("项目日报模板映射读取失败", exception);
        }
    }

    private List<FieldMapping> normalizeMappings(List<FieldMapping> mappings) {
        boolean useLegacyReportId =
                mappings.stream().noneMatch(FieldMapping::uniqueKey)
                        && mappings.stream()
                                .anyMatch(mapping -> "reportId".equals(mapping.systemField()));
        return mappings.stream()
                .map(
                        mapping ->
                                new FieldMapping(
                                        mapping.systemField(),
                                        mapping.targetColumn(),
                                        mapping.targetHeader(),
                                        false,
                                        mapping.uniqueKey()
                                                || (useLegacyReportId
                                                        && "reportId".equals(
                                                                mapping.systemField()))))
                .toList();
    }

    private String write(Object value) {
        try {
            return json.writeValueAsString(value);
        } catch (JsonProcessingException exception) {
            throw new IllegalStateException("Google日报推送数据序列化失败", exception);
        }
    }

    private int columnIndex(String column) {
        int result = 0;
        for (int index = 0; index < column.length(); index++)
            result = result * 26 + column.charAt(index) - 'A' + 1;
        return result;
    }

    private <T> T googleAccess(Supplier<T> action, String message) {
        try {
            return action.get();
        } catch (DeliveryReportException exception) {
            throw exception;
        } catch (RuntimeException exception) {
            throw new DeliveryReportException(message, exception);
        }
    }

    private CurrentUser currentUser() {
        var auth = SecurityContextHolder.getContext().getAuthentication();
        if (auth == null || !(auth.getPrincipal() instanceof CurrentUser user))
            throw new DeliveryReportException("当前会话未认证");
        return user;
    }

    private record ParsedSheetLink(String spreadsheetId, String sheetId) {}
}
