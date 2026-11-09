package com.adpulse.main.deliveryreport;

import com.adpulse.main.deliveryreport.DeliveryReportTypes.*;
import com.adpulse.system.common.security.CurrentUser;
import com.adpulse.system.common.security.DeliveryReportAccess;
import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.core.type.TypeReference;
import com.fasterxml.jackson.databind.ObjectMapper;
import java.math.BigDecimal;
import java.time.LocalDate;
import java.util.*;
import org.springframework.security.core.context.SecurityContextHolder;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

/** 本人投放日报的归属匹配、平台合并和幂等保存，不进入审批。 */
@Service
public class DeliveryReportService {
    private final DeliveryReportMapper mapper;
    private final DeliveryReportQueryProvider provider;
    private final ObjectMapper json;

    public DeliveryReportService(
            DeliveryReportMapper mapper, DeliveryReportQueryProvider provider, ObjectMapper json) {
        this.mapper = mapper;
        this.provider = provider;
        this.json = json;
    }

    /** 只提供仍存在的项目和代理线，停投代理线仍可用于历史补录。 */
    public List<LineOption> options() {
        currentUser();
        return mapper.findLines();
    }

    /** 已保存的人工字段优先，实际消耗每次从平台读取；无平台数据时沿用老系统的零值口径。 */
    public Result query(LocalDate date) {
        CurrentUser user = currentUser();
        String englishName = englishName(user.userId());
        return merge(date, user, match(provider.query(date, englishName), mapper.findLines()));
    }

    /** 仅加载时间段内已填日期，保留逐条日报以保证汇总与展开口径一致。 */
    public PerformanceResult performance(LocalDate startDate, LocalDate endDate) {
        return performanceFor(startDate, endDate, currentUser());
    }

    private PerformanceResult performanceFor(
            LocalDate startDate, LocalDate endDate, CurrentUser user) {
        if (startDate == null || endDate == null || startDate.isAfter(endDate))
            throw new DeliveryReportException("请选择有效的开始日期和结束日期");
        String department =
                Objects.requireNonNullElse(mapper.findDepartmentName(user.userId()), "未设置");
        List<Result> days = new ArrayList<>();
        List<LocalDate> dates = mapper.findReportDates(user.userId(), startDate, endDate);
        if (!dates.isEmpty()) {
            String englishName = mapper.findReadEnglishName(user.userId());
            List<LineOption> lines = mapper.findLines();
            for (LocalDate date : dates) {
                Result result =
                        merge(
                                date,
                                user,
                                match(
                                        englishName == null || englishName.isBlank()
                                                ? List.of()
                                                : provider.query(date, englishName.trim()),
                                        lines));
                days.add(
                        new Result(
                                date,
                                result.reporterId(),
                                result.reporterName(),
                                0,
                                result.rows().stream().filter(Row::saved).toList(),
                                department));
            }
        }
        return new PerformanceResult(startDate, endDate, department, days);
    }

    /** 人员导航限定有效投放师角色，并叠加当前会话可查看的人员范围。 */
    public List<Reporter> reporters() {
        CurrentUser user = currentUser();
        return mapper.findOperatorReporters(
                DeliveryReportAccess.canReadAll(user) ? null : user.userId());
    }

    /** 列表兼容入口仍使用批量查询，不再逐人逐日遍历。 */
    public List<Result> read(LocalDate date, Long reporterId) {
        return performance(date, date, reporterId).days();
    }

    /** 分页只读取当前页日报及截图；筛选条件在数据库分页前生效。 */
    public ReadPage page(
            LocalDate startDate,
            LocalDate endDate,
            Long reporterId,
            int page,
            int pageSize,
            String reporter,
            String project,
            String line) {
        Long scope = readScope(reporterId);
        if (startDate == null || endDate == null || startDate.isAfter(endDate))
            throw new DeliveryReportException("请选择有效的开始日期和结束日期");
        if (page < 1 || pageSize < 1 || pageSize > 100)
            throw new DeliveryReportException("分页参数无效，每页最多100条");
        long total = mapper.countReadRecords(scope, startDate, endDate, reporter, project, line);
        if (total == 0) return new ReadPage(0, page, pageSize, List.of());
        List<DeliveryReportRecord> records =
                mapper.findReadRecords(
                        scope,
                        startDate,
                        endDate,
                        reporter,
                        project,
                        line,
                        pageSize,
                        (long) (page - 1) * pageSize);
        return new ReadPage(total, page, pageSize, batchRows(records, startDate, endDate));
    }

    /** 统计独立于分页，不查询附件或账户来源集合。 */
    public ReadStats stats(
            LocalDate startDate,
            LocalDate endDate,
            Long reporterId,
            String reporter,
            String project,
            String line) {
        Long scope = readScope(reporterId);
        if (startDate == null || endDate == null || startDate.isAfter(endDate))
            throw new DeliveryReportException("请选择有效的开始日期和结束日期");

        List<DeliveryReportRecord> records =
                mapper.findReadRecords(scope, startDate, endDate, reporter, project, line, null, 0);
        Map<SpendKey, BigDecimal> spend = batchSpend(records, startDate, endDate);
        BigDecimal daily = BigDecimal.ZERO;
        BigDecimal actual = BigDecimal.ZERO;
        for (DeliveryReportRecord record : records) {
            daily = daily.add(readMetrics(record.getMetricsJson()).dailySpend());
            actual = actual.add(actualSpend(record, spend));
        }
        return new ReadStats(records.size(), daily.setScale(2), actual.setScale(2));
    }

    /** 按稳定ID重新加载可见日报，并合并当前平台消耗供Google预览和推送。 */
    public List<PushSourceRow> pushRows(List<Long> reportIds) {
        if (reportIds == null || reportIds.isEmpty() || reportIds.size() > 100)
            throw new DeliveryReportException("请选择1至100条已保存日报");
        List<Long> ids = reportIds.stream().distinct().toList();
        if (ids.size() != reportIds.size()) throw new DeliveryReportException("选择的日报记录存在重复");
        CurrentUser user = currentUser();
        Long scope = DeliveryReportAccess.canReadAll(user) ? null : user.userId();
        List<DeliveryReportRecord> records = mapper.findReadRecordsByIds(scope, ids);
        if (records.size() != ids.size())
            throw new DeliveryReportException("部分日报不存在或不在当前账号的查看范围内");
        LocalDate start =
                records.stream()
                        .map(DeliveryReportRecord::getReportDate)
                        .min(LocalDate::compareTo)
                        .orElseThrow();
        LocalDate end =
                records.stream()
                        .map(DeliveryReportRecord::getReportDate)
                        .max(LocalDate::compareTo)
                        .orElseThrow();
        Map<SpendKey, BigDecimal> spend = batchSpend(records, start, end);
        return records.stream()
                .map(
                        record ->
                                new PushSourceRow(
                                        record.getId().toString(),
                                        record.getReportDate(),
                                        record.getReporterName(),
                                        record.getDepartmentName(),
                                        record.getProjectId().toString(),
                                        record.getProjectName(),
                                        record.getAgencyLineName(),
                                        record.getPlatform(),
                                        actualSpend(record, spend),
                                        readMetrics(record.getMetricsJson()),
                                        readIds(record.getAccountIdsJson()),
                                        readIds(record.getCampaignIdsJson())))
                .toList();
    }

    /** 绩效按时间段一次读取已填记录，平台与截图均分批读取。 */
    public PerformanceResult performance(LocalDate startDate, LocalDate endDate, Long reporterId) {
        Long scope = readScope(reporterId);
        if (startDate == null || endDate == null || startDate.isAfter(endDate))
            throw new DeliveryReportException("请选择有效的开始日期和结束日期");
        var records = mapper.findReadRecords(scope, startDate, endDate, null, null, null, null, 0);
        return new PerformanceResult(
                startDate, endDate, "", batchRows(records, startDate, endDate));
    }

    private Long readScope(Long reporterId) {
        CurrentUser user = currentUser();
        if (!DeliveryReportAccess.canReadAll(user)) {
            if (reporterId != null && !reporterId.equals(user.userId()))
                throw new DeliveryReportException("无权查看他人的日报或绩效数据");
            return user.userId();
        }
        if (reporterId != null && reporterId <= 0) throw new DeliveryReportException("投放师参数无效");
        return reporterId;
    }

    private record SpendKey(
            LocalDate date, String placer, String project, String line, String platform) {}

    private record DayKey(LocalDate date, Long reporter) {}

    private List<Result> batchRows(
            List<DeliveryReportRecord> records, LocalDate start, LocalDate end) {
        if (records.isEmpty()) return List.of();
        Map<SpendKey, BigDecimal> spend = batchSpend(records, start, end);
        Map<String, List<Attachment>> attachments = new HashMap<>();
        List<Long> ids = records.stream().map(DeliveryReportRecord::getId).toList();
        for (int i = 0; i < ids.size(); i += 500) {
            for (ReportAttachment file :
                    mapper.findReadAttachments(ids.subList(i, Math.min(i + 500, ids.size()))))
                attachments
                        .computeIfAbsent(file.reportId(), ignored -> new ArrayList<>())
                        .add(new Attachment(file.id(), file.name(), file.mimeType()));
        }
        Map<DayKey, Result> days = new LinkedHashMap<>();
        for (DeliveryReportRecord record : records) {
            var day =
                    days.computeIfAbsent(
                            new DayKey(record.getReportDate(), record.getReporterId()),
                            ignored ->
                                    new Result(
                                            record.getReportDate(),
                                            record.getReporterId().toString(),
                                            record.getReporterName(),
                                            0,
                                            new ArrayList<>(),
                                            record.getDepartmentName()));
            day.rows()
                    .add(
                            new Row(
                                    record.getId().toString(),
                                    record.getProjectId().toString(),
                                    record.getProjectName(),
                                    record.getAgencyLineId().toString(),
                                    record.getAgencyLineName(),
                                    record.getPlatform(),
                                    actualSpend(record, spend),
                                    readMetrics(record.getMetricsJson()),
                                    attachments.getOrDefault(record.getId().toString(), List.of()),
                                    List.of(),
                                    List.of(),
                                    true));
        }
        return new ArrayList<>(days.values());
    }

    private Map<SpendKey, BigDecimal> batchSpend(
            List<DeliveryReportRecord> records, LocalDate start, LocalDate end) {
        List<String> placers =
                records.stream()
                        .map(DeliveryReportRecord::getReporterEnglishName)
                        .filter(Objects::nonNull)
                        .map(String::trim)
                        .filter(value -> !value.isEmpty())
                        .distinct()
                        .toList();
        Map<SpendKey, BigDecimal> result = new HashMap<>();
        if (placers.isEmpty()) return result;
        // 名称匹配必须唯一，保留原有项目+代理线匹配约束。
        Map<NameKey, List<LineOption>> lines = new HashMap<>();
        for (LineOption line : mapper.findLines())
            lines.computeIfAbsent(
                            new NameKey(line.projectName(), line.agencyLineName()),
                            ignored -> new ArrayList<>())
                    .add(line);
        for (int i = 0; i < placers.size(); i += 200) {
            for (SpendRow row :
                    provider.querySpend(
                            start, end, placers.subList(i, Math.min(i + 200, placers.size())))) {
                List<LineOption> matches =
                        lines.getOrDefault(
                                new NameKey(row.projectName(), row.agencyLineName()), List.of());
                if (matches.size() != 1) continue;
                LineOption line = matches.getFirst();
                var key =
                        new SpendKey(
                                row.date(),
                                row.placerId(),
                                line.projectId(),
                                line.agencyLineId(),
                                row.platform());
                if (result.putIfAbsent(
                                key, row.actualSpend().setScale(2, java.math.RoundingMode.HALF_UP))
                        != null) throw new DeliveryReportException("平台聚合数据重复，请检查数据口径");
            }
        }
        return result;
    }

    private BigDecimal actualSpend(DeliveryReportRecord record, Map<SpendKey, BigDecimal> spend) {
        return spend.getOrDefault(
                new SpendKey(
                        record.getReportDate(),
                        Objects.requireNonNullElse(record.getReporterEnglishName(), "").trim(),
                        record.getProjectId().toString(),
                        record.getAgencyLineId().toString(),
                        record.getPlatform()),
                new BigDecimal("0.00"));
    }

    /** 以用户行锁串行化本人保存，唯一键保证重复点击不会新增重复日报。 */
    @Transactional
    public Result save(SaveRequest request) {
        CurrentUser user = currentUser();
        if (mapper.lockReporter(user.userId()) == null)
            throw new DeliveryReportException("当前账号不可用");
        String englishName = englishName(user.userId());
        List<LineOption> lines = mapper.findLines();
        Matched matched = match(provider.query(request.date(), englishName), lines);
        Set<Key> keys = new HashSet<>();
        for (SaveRow row : request.rows()) {
            Key key =
                    new Key(
                            row.projectId().toString(),
                            row.agencyLineId().toString(),
                            row.platform().trim().toLowerCase(Locale.ROOT));
            if (!keys.add(key)) throw new DeliveryReportException("同一日期、项目、代理线和平台只能保存一条日报");
            LineOption line =
                    lines.stream()
                            .filter(
                                    item ->
                                            item.projectId().equals(key.projectId())
                                                    && item.agencyLineId().equals(key.lineId()))
                            .findFirst()
                            .orElseThrow(
                                    () -> new DeliveryReportException("项目或代理线不存在，或代理线不属于所选项目"));
            validateImages(user.userId(), row.attachmentIds());
            PlatformRow platform = matched.platforms().get(key);
            DeliveryReportRecord record = new DeliveryReportRecord();
            record.setReportDate(request.date());
            record.setReporterId(user.userId());
            record.setReporterEnglishName(englishName);
            record.setProjectId(row.projectId());
            record.setProjectName(line.projectName());
            record.setAgencyLineId(row.agencyLineId());
            record.setAgencyLineName(line.agencyLineName());
            record.setPlatform(key.platform());
            record.setMetricsJson(write(row.metrics()));
            // 无新平台数据时保留已有来源集合，不把临时缺数误当成来源被删除。
            record.setAccountIdsJson(platform == null ? null : write(platform.accountIds()));
            record.setCampaignIdsJson(platform == null ? null : write(platform.campaignIds()));
            mapper.upsert(record);
            mapper.clearAttachments(record.getId());
            for (int i = 0; i < row.attachmentIds().size(); i++)
                mapper.insertAttachment(record.getId(), row.attachmentIds().get(i), i);
        }
        return merge(request.date(), user, matched);
    }

    private void validateImages(Long userId, List<Long> ids) {
        if (ids.size() > 5 || new HashSet<>(ids).size() != ids.size())
            throw new DeliveryReportException("每条日报最多关联5张不重复截图");
        if (!ids.isEmpty() && mapper.lockOwnedImages(userId, ids).size() != ids.size())
            throw new DeliveryReportException("截图不存在、不是受支持的图片，或不属于当前账号");
    }

    private Result merge(LocalDate date, CurrentUser user, Matched matched) {
        Map<Key, Row> rows = new LinkedHashMap<>();
        for (var entry : matched.platforms().entrySet()) {
            Key key = entry.getKey();
            PlatformRow platform = entry.getValue();
            LineOption line = matched.lines().get(key);
            Metrics metrics =
                    new Metrics(
                            platform.actualSpend(),
                            platform.impressions(),
                            platform.clicks(),
                            platform.installs(),
                            platform.registrations(),
                            platform.firstPurchases(),
                            BigDecimal.ZERO,
                            BigDecimal.ZERO,
                            "未设置",
                            "");
            rows.put(
                    key,
                    new Row(
                            null,
                            key.projectId(),
                            line.projectName(),
                            key.lineId(),
                            line.agencyLineName(),
                            key.platform(),
                            platform.actualSpend(),
                            metrics,
                            List.of(),
                            platform.accountIds(),
                            platform.campaignIds(),
                            false));
        }
        for (DeliveryReportRecord record : mapper.findRecords(user.userId(), date)) {
            Key key =
                    new Key(
                            record.getProjectId().toString(),
                            record.getAgencyLineId().toString(),
                            record.getPlatform());
            PlatformRow platform = matched.platforms().get(key);
            rows.put(
                    key,
                    new Row(
                            record.getId().toString(),
                            key.projectId(),
                            record.getProjectName(),
                            key.lineId(),
                            record.getAgencyLineName(),
                            key.platform(),
                            platform == null ? new BigDecimal("0.00") : platform.actualSpend(),
                            readMetrics(record.getMetricsJson()),
                            mapper.findAttachments(record.getId()),
                            platform == null
                                    ? readIds(record.getAccountIdsJson())
                                    : platform.accountIds(),
                            platform == null
                                    ? readIds(record.getCampaignIdsJson())
                                    : platform.campaignIds(),
                            true));
        }
        return new Result(
                date,
                user.userId().toString(),
                user.displayName(),
                matched.unmatched(),
                new ArrayList<>(rows.values()));
    }

    private Matched match(List<PlatformRow> platforms, List<LineOption> lines) {
        Map<NameKey, List<LineOption>> byName = new HashMap<>();
        for (LineOption line : lines)
            byName.computeIfAbsent(
                            new NameKey(line.projectName(), line.agencyLineName()),
                            ignored -> new ArrayList<>())
                    .add(line);
        Map<Key, PlatformRow> result = new LinkedHashMap<>();
        Map<Key, LineOption> resolved = new HashMap<>();
        int unmatched = 0;
        for (PlatformRow row : platforms) {
            if (row.platform() == null || row.platform().isBlank()) {
                unmatched++;
                continue;
            }
            List<LineOption> candidates =
                    byName.getOrDefault(
                            new NameKey(row.projectName(), row.agencyLineName()), List.of());
            if (candidates.size() != 1) {
                unmatched++;
                continue;
            }
            LineOption line = candidates.getFirst();
            Key key = new Key(line.projectId(), line.agencyLineId(), row.platform());
            if (result.putIfAbsent(key, row) != null)
                throw new DeliveryReportException("平台聚合数据重复，请检查数据口径");
            resolved.put(key, line);
        }
        return new Matched(result, resolved, unmatched);
    }

    private String englishName(Long userId) {
        String name = mapper.findEnglishName(userId);
        if (name == null || name.isBlank())
            throw new DeliveryReportException("请先在个人资料中设置英文名称，再查询投放日报");
        return name.trim();
    }

    private CurrentUser currentUser() {
        var auth = SecurityContextHolder.getContext().getAuthentication();
        if (auth == null || !(auth.getPrincipal() instanceof CurrentUser user))
            throw new DeliveryReportException("当前会话未认证");
        return user;
    }

    private String write(Object value) {
        try {
            return json.writeValueAsString(value);
        } catch (JsonProcessingException e) {
            throw new IllegalStateException("日报序列化失败", e);
        }
    }

    private Metrics readMetrics(String value) {
        try {
            return json.readValue(value, Metrics.class);
        } catch (JsonProcessingException e) {
            throw new IllegalStateException("日报指标读取失败", e);
        }
    }

    private List<String> readIds(String value) {
        try {
            return json.readValue(value, new TypeReference<List<String>>() {});
        } catch (JsonProcessingException e) {
            throw new IllegalStateException("日报来源读取失败", e);
        }
    }

    private record Key(String projectId, String lineId, String platform) {}

    private record NameKey(String projectName, String lineName) {}

    private record Matched(
            Map<Key, PlatformRow> platforms, Map<Key, LineOption> lines, int unmatched) {}
}
