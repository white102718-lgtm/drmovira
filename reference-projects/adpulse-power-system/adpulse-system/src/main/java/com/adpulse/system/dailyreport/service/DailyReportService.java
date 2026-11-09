package com.adpulse.system.dailyreport.service;

import com.adpulse.system.common.api.ApiCode;
import com.adpulse.system.common.exception.BusinessException;
import com.adpulse.system.common.security.CurrentUser;
import com.adpulse.system.common.security.SecurityContextHelper;
import com.adpulse.system.dailyreport.mapper.DailyReportMapper;
import com.adpulse.system.dailyreport.model.DailyReportRule;
import com.adpulse.system.dailyreport.model.DailyReportSubmission;
import com.adpulse.system.notification.dto.NotificationMessage;
import com.adpulse.system.notification.service.SiteNotificationPublisher;
import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.node.ArrayNode;
import com.fasterxml.jackson.databind.node.ObjectNode;
import java.math.BigDecimal;
import java.time.LocalDate;
import java.time.LocalTime;
import java.time.YearMonth;
import java.time.ZoneId;
import java.time.ZonedDateTime;
import java.time.format.DateTimeParseException;
import java.time.temporal.IsoFields;
import java.time.temporal.TemporalAdjusters;
import java.util.ArrayList;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Set;
import java.util.regex.Pattern;
import org.springframework.dao.DuplicateKeyException;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

/** 日报规则、提交、范围校验与服务端提醒。所有决定权限和时间的值均在此二次校验。 */
@Service
public class DailyReportService {
    private static final Pattern RULE_KEY_PATTERN = Pattern.compile("[A-Za-z0-9_-]{1,64}");

    private static final String MATERIAL_DESIGNER_MONTHLY_REPORT_RULE_KEY =
            "material-designer-daily-report";

    /** 固定汇报使用前端业务表单，管理员只能调整允许开放的规则项，不能删除配置入口。 */
    private static final Set<String> FIXED_REPORT_RULE_KEYS =
            Set.of("delivery-daily-report", MATERIAL_DESIGNER_MONTHLY_REPORT_RULE_KEY);

    private static final Set<String> PERIODS = Set.of("每天", "每周", "每双周", "每月", "不重复");
    private final DailyReportMapper mapper;
    private final ObjectMapper objectMapper;
    private final FeishuDailyReportNotifier feishuNotifier;
    private final SiteNotificationPublisher siteNotificationPublisher;

    public DailyReportService(
            DailyReportMapper mapper,
            ObjectMapper objectMapper,
            FeishuDailyReportNotifier feishuNotifier,
            SiteNotificationPublisher siteNotificationPublisher) {
        this.mapper = mapper;
        this.objectMapper = objectMapper;
        this.feishuNotifier = feishuNotifier;
        this.siteNotificationPublisher = siteNotificationPublisher;
    }

    public List<JsonNode> listManagedRules() {
        CurrentUser user = SecurityContextHelper.currentUser();
        return mapper.findActiveRules().stream()
                .filter(rule -> canManage(rule, user))
                .<JsonNode>map(this::ruleConfig)
                .toList();
    }

    public List<JsonNode> listAvailableRules() {
        CurrentUser user = SecurityContextHelper.currentUser();
        return mapper.findActiveRules().stream()
                .filter(rule -> canWrite(ruleConfig(rule), user))
                .<JsonNode>map(this::ruleConfig)
                .toList();
    }

    /**
     * The report-type navigation must be visible to every configured participant, not only writers.
     * Submission remains guarded by {@link #canWrite(JsonNode, CurrentUser)}.
     */
    public List<JsonNode> listVisibleRules() {
        CurrentUser user = SecurityContextHelper.currentUser();
        return mapper.findActiveRules().stream()
                .filter(rule -> canAccess(ruleConfig(rule), user))
                .<JsonNode>map(rule -> visibleRuleView(ruleConfig(rule), user))
                .toList();
    }

    @Transactional
    public JsonNode saveRule(String ruleKey, JsonNode payload) {
        CurrentUser user = SecurityContextHelper.currentUser();
        DailyReportRule existing = mapper.findRuleByKey(ruleKey);
        if (existing != null) ensureCanManage(existing, user);
        ObjectNode config = validateAndNormalizeRule(ruleKey, payload);
        DailyReportRule rule = new DailyReportRule();
        rule.setRuleKey(ruleKey);
        rule.setName(config.path("name").asText());
        rule.setConfigJson(writeJson(config));
        rule.setReminderEnabled(config.path("reminderEnabled").asBoolean(false));
        rule.setStatus(true);
        rule.setUpdatedBy(user.userId());
        if (existing == null) {
            rule.setCreatedBy(user.userId());
            mapper.insertRule(rule);
        } else {
            mapper.updateRule(rule);
        }
        return config;
    }

    @Transactional
    public void deleteRule(String ruleKey) {
        if (!RULE_KEY_PATTERN.matcher(ruleKey).matches())
            throw BusinessException.validation("日报规则标识不正确");
        DailyReportRule existing = mapper.findRuleByKey(ruleKey);
        if (existing == null) throw BusinessException.notFound("日报规则");
        CurrentUser user = SecurityContextHelper.currentUser();
        ensureCanManage(existing, user);
        if (FIXED_REPORT_RULE_KEYS.contains(ruleKey)) {
            throw BusinessException.conflict("投放日报和素材师月报为固定配置，不允许删除");
        }
        if (mapper.deleteRule(ruleKey, user.userId()) != 1) {
            throw BusinessException.notFound("日报规则");
        }
    }

    @Transactional
    public JsonNode submit(JsonNode payload) {
        String ruleKey = text(payload, "ruleId");
        DailyReportRule rule = mapper.findRuleByKey(ruleKey);
        if (rule == null) throw BusinessException.notFound("日报规则");
        CurrentUser user = SecurityContextHelper.currentUser();
        ObjectNode config = ruleConfig(rule);
        if (!canWrite(config, user)) {
            throw new BusinessException(ApiCode.ACCESS_DENIED, "您不在此日报的填写人员范围内");
        }
        JsonNode fields = payload.path("fields");
        if (!fields.isObject()) throw BusinessException.validation("日报字段格式不正确");
        validateRequiredFields(config.path("fields"), fields);
        JsonNode attachments = payload.path("attachments");
        if (!attachments.isMissingNode() && !attachments.isObject()) {
            throw BusinessException.validation("日报附件格式不正确");
        }
        List<Long> fileIds = attachmentIds(attachments);
        if (!fileIds.isEmpty()
                && mapper.findOwnedFileIds(fileIds, user.userId()).size() != fileIds.size()) {
            throw BusinessException.conflict("附件不存在、已删除或不属于当前账号");
        }
        String userName = mapper.findActiveUserName(user.userId());
        if (userName == null) throw BusinessException.notFound("提交账号");
        LocalDate reportDate = submissionReportDate(ruleKey, config, fields);
        DailyReportSubmission submission = new DailyReportSubmission();
        submission.setRuleId(rule.getId());
        submission.setReportDate(reportDate);
        submission.setPeriodKey(reportingPeriodStart(config, reportDate));
        submission.setFieldValuesJson(writeJson(fields));
        submission.setAttachmentsJson(attachments.isMissingNode() ? "{}" : writeJson(attachments));
        submission.setRuleSnapshotJson(writeJson(snapshot(config)));
        submission.setSubmittedById(user.userId());
        submission.setSubmittedByName(userName);
        try {
            mapper.insertSubmission(submission);
        } catch (DuplicateKeyException exception) {
            throw BusinessException.conflict("当前填写周期内已提交日报，请编辑原日报后重新提交");
        }
        if (!fileIds.isEmpty())
            mapper.insertFileBindings(submission.getId(), fileIds, user.userId());
        notifyRecipients(config, submission, user.userId());
        DailyReportSubmission persisted = mapper.findSubmissionById(submission.getId());
        if (persisted == null) throw BusinessException.notFound("日报提交记录");
        return submissionView(persisted);
    }

    /** 更新原日报并重新提交。记录归属以提交人 ID 判断，拥有查看权限的其他成员不得编辑。 */
    @Transactional
    public JsonNode resubmit(String submissionId, JsonNode payload) {
        Long id = parseSubmissionId(submissionId);
        CurrentUser user = SecurityContextHelper.currentUser();
        DailyReportSubmission submission = mapper.findSubmissionById(id);
        if (submission == null) throw BusinessException.notFound("日报提交记录");
        if (!user.userId().equals(submission.getSubmittedById())) {
            throw new BusinessException(ApiCode.ACCESS_DENIED, "仅日报提交人可以编辑自己的日报");
        }
        ObjectNode snapshot = readObject(submission.getRuleSnapshotJson());
        JsonNode fields = payload.path("fields");
        if (!fields.isObject()) throw BusinessException.validation("日报字段格式不正确");
        validateRequiredFields(snapshot.path("fields"), fields);
        JsonNode attachments = payload.path("attachments");
        if (!attachments.isMissingNode() && !attachments.isObject()) {
            throw BusinessException.validation("日报附件格式不正确");
        }
        List<Long> fileIds = attachmentIds(attachments);
        if (!fileIds.isEmpty()
                && mapper.findOwnedFileIds(fileIds, user.userId()).size() != fileIds.size()) {
            throw BusinessException.conflict("附件不存在、已删除或不属于当前账号");
        }
        submission.setFieldValuesJson(writeJson(fields));
        submission.setAttachmentsJson(attachments.isMissingNode() ? "{}" : writeJson(attachments));
        if (mapper.updateSubmission(submission) != 1) {
            throw new BusinessException(ApiCode.ACCESS_DENIED, "仅日报提交人可以编辑自己的日报");
        }
        mapper.deactivateFileBindings(submission.getId());
        if (!fileIds.isEmpty())
            mapper.insertFileBindings(submission.getId(), fileIds, user.userId());
        DailyReportSubmission persisted = mapper.findSubmissionById(submission.getId());
        if (persisted == null) throw BusinessException.notFound("日报提交记录");
        notifyRecipients(snapshot, persisted, user.userId());
        return submissionView(persisted);
    }

    public List<JsonNode> listSubmissions() {
        CurrentUser user = SecurityContextHelper.currentUser();
        List<JsonNode> results = new ArrayList<>();
        for (DailyReportSubmission submission : mapper.findSubmissions()) {
            ObjectNode snapshot = readObject(submission.getRuleSnapshotJson());
            if (submission.getSubmittedById().equals(user.userId())
                    || canView(snapshot, user.userId())) {
                results.add(submissionView(submission));
            }
        }
        return results;
    }

    /** 每分钟由调度器调用；按规则时区确定日期和提醒时刻，并以日志唯一键避免重复提醒。 */
    @Transactional
    public void dispatchDueReminders() {
        for (DailyReportRule rule : mapper.findActiveRules()) {
            ObjectNode config = ruleConfig(rule);
            if (!config.path("reminderEnabled").asBoolean(false)) continue;
            ZoneId zone;
            try {
                zone = zone(config);
            } catch (BusinessException exception) {
                continue;
            }
            ZonedDateTime now = ZonedDateTime.now(zone);
            String reminderTime = schedule(config).path("reminderTime").asText("");
            if (!isTime(reminderTime)
                    || !now.toLocalTime()
                            .withSecond(0)
                            .withNano(0)
                            .equals(LocalTime.parse(reminderTime))) continue;
            LocalDate reportDate = now.toLocalDate();
            if (!isSubmissionDate(config, reportDate)) continue;
            for (Long userId : targetUsers(config.path("personnel").path("writers"))) {
                if (mapper.countSubmissions(
                                rule.getId(), userId, reportingPeriodStart(config, reportDate))
                        > 0) continue;
                if (mapper.insertReminderLog(rule.getId(), userId, reportDate, reminderTime) == 1) {
                    siteNotificationPublisher.publish(
                            userId,
                            new NotificationMessage(
                                    "日报待提交提醒",
                                    String.format(
                                            "%s 将于 %s 截止，请及时提交。",
                                            config.path("name").asText("日报"),
                                            deadlineLabel(config)),
                                    "/workbench/daily-reports",
                                    "DAILY_REPORT_REMINDER",
                                    rule.getId()));
                }
            }
        }
    }

    private ObjectNode validateAndNormalizeRule(String ruleKey, JsonNode payload) {
        if (!RULE_KEY_PATTERN.matcher(ruleKey).matches())
            throw BusinessException.validation("日报规则标识不正确");
        if (!payload.isObject()) throw BusinessException.validation("日报规则格式不正确");
        ObjectNode config = ((ObjectNode) payload).deepCopy();
        config.put("id", ruleKey);
        normalizeFixedReportDefinition(ruleKey, config);
        String name = text(config, "name");
        if (name == null || name.length() > 100)
            throw BusinessException.validation("请填写不超过100字的日报名称");
        if (!config.path("fields").isArray()) throw BusinessException.validation("日报字段不能为空");
        if (FIXED_REPORT_RULE_KEYS.contains(ruleKey)) {
            // 业务表单由前端固定维护，服务端只保存人员、周期和提醒等通用规则。
            config.putArray("fields");
        }
        if (!config.path("personnel").isObject()) throw BusinessException.validation("请配置日报人员范围");
        ObjectNode personnel = (ObjectNode) config.path("personnel");
        personnel.remove("allowCustomCc");
        validateRequiredMembers(config.path("personnel").path("writers"), "填写人员");
        validateRequiredMembers(config.path("personnel").path("reporters"), "汇报对象");
        validateMembers(config.path("personnel").path("cc"), "抄送对象");
        JsonNode viewers = config.path("personnel").path("viewers");
        if (!"custom".equals(config.path("personnel").path("viewerScope").asText())) {
            throw BusinessException.validation("查看范围请按角色、部门或人员选择");
        }
        validateMembers(viewers, "查看人员");
        ObjectNode schedule = schedule(config);
        String period = config.path("period").asText();
        if (!PERIODS.contains(period)) throw BusinessException.validation("填写周期不正确");
        String timezone = schedule.path("timezone").asText("Asia/Shanghai");
        try {
            ZoneId.of(timezone);
        } catch (Exception exception) {
            throw BusinessException.validation("时区必须是 IANA 标准时区");
        }
        schedule.put("timezone", timezone);
        normalizeTime(schedule, "startTime", "00:00");
        normalizeTime(schedule, "deadlineTime", "23:00");
        normalizeTime(schedule, "reminderTime", "19:00");
        ArrayNode days = schedule.withArray("submissionDays");
        if ("每天".equals(period) || "不重复".equals(period)) {
            days.removeAll();
            schedule.remove("submissionDayOfMonth");
            return config;
        }
        if ("每月".equals(period)) {
            int dayOfMonth = schedule.path("submissionDayOfMonth").asInt(1);
            if (dayOfMonth < 1 || dayOfMonth > 28) {
                throw BusinessException.validation("每月提交日必须在 1 至 28 日之间");
            }
            days.removeAll();
            schedule.put("submissionDayOfMonth", dayOfMonth);
            return config;
        }
        Set<Integer> uniqueDays = new LinkedHashSet<>();
        for (JsonNode day : days) {
            int value = day.asInt(0);
            if (value < 1 || value > 7) throw BusinessException.validation("提交日期必须是周一至周日");
            uniqueDays.add(value);
        }
        if (uniqueDays.isEmpty()) uniqueDays.add(1);
        if (uniqueDays.size() > 1) {
            throw BusinessException.validation("每周或双周规则只能选择一个提交日");
        }
        days.removeAll();
        uniqueDays.forEach(days::add);
        return config;
    }

    private void validateRequiredFields(JsonNode definitions, JsonNode values) {
        for (JsonNode field : definitions) {
            if (!field.path("required").asBoolean(false)) continue;
            JsonNode value = values.path(field.path("id").asText());
            if (value.isMissingNode()
                    || value.isNull()
                    || (value.isTextual() && value.asText().isBlank())
                    || (value.isArray() && value.isEmpty())) {
                throw BusinessException.validation("请填写" + field.path("label").asText("必填字段"));
            }
        }
    }

    /** 日报必须配置填写人员和汇报对象；抄送与查看范围仅扩展可见性，允许为空。 */
    private void validateRequiredMembers(JsonNode members, String label) {
        if (!members.isArray() || members.isEmpty()) {
            throw BusinessException.validation("请按角色、部门或人员选择至少一名" + label);
        }
        validateMembers(members, label);
    }

    /** 校验人员范围仅引用当前系统中的有效用户和部门，防止保存后无法真正授权。 */
    private void validateMembers(JsonNode members, String label) {
        if (!members.isArray()) throw BusinessException.validation(label + "格式不正确");
        Set<Long> userIds = new LinkedHashSet<>();
        Set<Long> departmentIds = new LinkedHashSet<>();
        Set<Long> roleIds = new LinkedHashSet<>();
        String memberType = null;
        for (JsonNode member : members) {
            String id = member.path("id").asText();
            String currentType = id.substring(0, id.indexOf(':') + 1);
            if (memberType != null && !memberType.equals(currentType)) {
                throw BusinessException.validation(label + "只能按角色、部门或人员三选一");
            }
            memberType = currentType;
            if (id.startsWith("user:")) userIds.add(parseMemberId(id));
            else if (id.startsWith("department:")) departmentIds.add(parseMemberId(id));
            else if (id.startsWith("role:")) roleIds.add(parseMemberId(id));
            else throw BusinessException.validation(label + "包含无效成员");
        }
        if (!userIds.isEmpty()
                && mapper.findActiveUserIds(List.copyOf(userIds)).size() != userIds.size()) {
            throw BusinessException.validation(label + "包含不存在或已停用的系统用户");
        }
        if (!departmentIds.isEmpty()
                && mapper.findActiveDepartmentIds(List.copyOf(departmentIds)).size()
                        != departmentIds.size()) {
            throw BusinessException.validation(label + "包含不存在或已停用的系统部门，请重新选择");
        }
        if (!roleIds.isEmpty()
                && mapper.findActiveRoleIds(List.copyOf(roleIds)).size() != roleIds.size()) {
            throw BusinessException.validation(label + "包含不存在或已停用的系统角色，请重新选择");
        }
    }

    /** 日报填写权限只由规则人员范围决定；系统管理员的规则管理权限不能扩大为代填权限。 */
    private boolean canWrite(JsonNode config, CurrentUser user) {
        return targetUsers(config.path("personnel").path("writers")).contains(user.userId());
    }

    private boolean canAccess(JsonNode config, CurrentUser user) {
        return canWrite(config, user) || canView(config, user.userId());
    }

    private boolean canView(JsonNode config, Long userId) {
        JsonNode personnel = config.path("personnel");
        return targetUsers(personnel.path("viewers")).contains(userId)
                || targetUsers(personnel.path("reporters")).contains(userId)
                || targetUsers(personnel.path("cc")).contains(userId);
    }

    /** 判断当前用户是否拥有规则所有权或系统管理员身份。 */
    private boolean canManage(DailyReportRule rule, CurrentUser user) {
        return user.userId().equals(rule.getCreatedBy()) || isSystemAdmin(user);
    }

    /** 阻止非创建人、非系统管理员修改或删除已有规则。 */
    private void ensureCanManage(DailyReportRule rule, CurrentUser user) {
        if (!canManage(rule, user)) {
            throw new BusinessException(ApiCode.ACCESS_DENIED, "仅规则创建人或系统管理员可以管理此规则");
        }
    }

    private boolean isSystemAdmin(CurrentUser user) {
        return user.getAuthorities().stream()
                .anyMatch(authority -> "ROLE_ADMIN".equals(authority.getAuthority()));
    }

    private List<Long> targetUsers(JsonNode members) {
        Set<Long> userIds = new LinkedHashSet<>();
        List<Long> departmentIds = new ArrayList<>();
        List<Long> roleIds = new ArrayList<>();
        if (!members.isArray()) return List.of();
        for (JsonNode member : members) {
            String id = member.path("id").asText();
            if (id.startsWith("user:")) userIds.add(parseMemberId(id));
            if (id.startsWith("department:")) departmentIds.add(parseMemberId(id));
            if (id.startsWith("role:")) roleIds.add(parseMemberId(id));
        }
        if (!departmentIds.isEmpty())
            userIds.addAll(mapper.findActiveUserIdsByDepartments(departmentIds));
        if (!roleIds.isEmpty()) userIds.addAll(mapper.findActiveUserIdsByRoles(roleIds));
        return List.copyOf(userIds);
    }

    private long parseMemberId(String id) {
        try {
            String rawId = id.substring(id.indexOf(':') + 1);
            if (!rawId.matches("[1-9][0-9]*")) throw new NumberFormatException(rawId);
            return Long.parseLong(rawId);
        } catch (RuntimeException exception) {
            throw BusinessException.validation("人员范围标识不正确");
        }
    }

    private List<Long> attachmentIds(JsonNode attachments) {
        if (!attachments.isObject()) return List.of();
        Set<Long> result = new LinkedHashSet<>();
        attachments.forEach(
                entry -> {
                    if (!entry.isArray()) throw BusinessException.validation("附件字段格式不正确");
                    for (JsonNode file : entry) {
                        long id = file.path("id").asLong(0);
                        if (id <= 0) throw BusinessException.validation("附件ID不正确");
                        result.add(id);
                    }
                });
        if (result.size() > 10) throw BusinessException.validation("每条日报最多上传10个附件");
        return List.copyOf(result);
    }

    private void notifyRecipients(
            JsonNode config, DailyReportSubmission submission, Long submitterId) {
        Set<Long> recipients = new LinkedHashSet<>();
        recipients.addAll(targetUsers(config.path("personnel").path("reporters")));
        recipients.addAll(targetUsers(config.path("personnel").path("cc")));
        recipients.remove(submitterId);
        String content =
                submission.getSubmittedByName() + " 已提交「" + config.path("name").asText("日报") + "」。";
        for (Long recipient : recipients) {
            siteNotificationPublisher.publish(
                    recipient,
                    new NotificationMessage(
                            "收到日报提交",
                            content,
                            "/workbench/daily-reports",
                            "DAILY_REPORT_REMINDER",
                            submission.getId()));
        }
        feishuNotifier.notifyRecipients(List.copyOf(recipients), "【测试提醒】" + content);
    }

    private boolean isSubmissionDate(JsonNode config, LocalDate date) {
        String period = config.path("period").asText();
        if ("每天".equals(period)) return true;
        if ("不重复".equals(period)) return false;
        ObjectNode schedule = schedule(config);
        if ("每月".equals(period)) {
            int dayOfMonth = schedule.path("submissionDayOfMonth").asInt(0);
            if (dayOfMonth >= 1 && dayOfMonth <= 28) return date.getDayOfMonth() == dayOfMonth;
            return isLegacyMonthlySubmissionDate(schedule.withArray("submissionDays"), date);
        }
        ArrayNode days = schedule.withArray("submissionDays");
        boolean selected = false;
        for (JsonNode day : days)
            if (day.asInt() == date.getDayOfWeek().getValue()) selected = true;
        if (!selected) return false;
        if ("每双周".equals(period))
            return date.getLong(java.time.temporal.IsoFields.WEEK_OF_WEEK_BASED_YEAR) % 2 == 0;
        return true;
    }

    /** 同一规则周期使用稳定的起始日期作为唯一键，避免按提交当天重复填写周报、双周报或月报。 */
    private LocalDate reportingPeriodStart(JsonNode config, LocalDate date) {
        LocalDate weekStart =
                date.with(TemporalAdjusters.previousOrSame(java.time.DayOfWeek.MONDAY));
        return switch (config.path("period").asText()) {
            case "每周" -> weekStart;
            case "每双周" ->
                    date.getLong(IsoFields.WEEK_OF_WEEK_BASED_YEAR) % 2 == 0
                            ? weekStart
                            : weekStart.minusWeeks(1);
            case "每月" -> date.withDayOfMonth(1);
            case "不重复" -> LocalDate.of(1970, 1, 1);
            default -> date;
        };
    }

    /** 素材师月报按用户选择的结算月份落账，确保“同一素材师、同一结算月一条”的唯一性。 其他日报仍按规则时区的当前日期确定填写周期。 */
    private LocalDate submissionReportDate(String ruleKey, JsonNode config, JsonNode fields) {
        if (!MATERIAL_DESIGNER_MONTHLY_REPORT_RULE_KEY.equals(ruleKey)) {
            return ZonedDateTime.now(zone(config)).toLocalDate();
        }

        String settlementMonth = text(fields, "settlementMonth");
        String commissionRate = text(fields, "commissionRate");
        requireMaterialSettlementSelection(fields, "pitcherIds", "投放师");
        requireMaterialSettlementSelection(fields, "projectIds", "项目");
        requireMaterialSettlementSelection(fields, "taskLineIds", "任务线");
        if (settlementMonth == null) throw BusinessException.validation("请选择结算月份");
        if (commissionRate == null) throw BusinessException.validation("请选择提成比例");
        try {
            BigDecimal rate = new BigDecimal(commissionRate);
            if (rate.compareTo(BigDecimal.ZERO) <= 0
                    || rate.compareTo(BigDecimal.valueOf(100)) > 0) {
                throw BusinessException.validation("提成比例必须大于0且不超过100");
            }
        } catch (NumberFormatException exception) {
            throw BusinessException.validation("提成比例格式不正确");
        }
        try {
            return YearMonth.parse(settlementMonth).atDay(1);
        } catch (DateTimeParseException exception) {
            throw BusinessException.validation("结算月份格式必须为yyyy-MM");
        }
    }

    private void requireMaterialSettlementSelection(JsonNode fields, String key, String label) {
        String value = text(fields, key);
        if (value == null
                || List.of(value.split(",", -1)).stream()
                        .map(String::trim)
                        .anyMatch(String::isEmpty)) {
            throw BusinessException.validation("请至少选择" + label);
        }
    }

    /** 兼容尚未重新保存的旧月报规则，避免迁移期间丢失原有提醒。 */
    private boolean isLegacyMonthlySubmissionDate(ArrayNode days, LocalDate date) {
        if (date.getDayOfMonth() > 7) return false;
        for (JsonNode day : days) {
            if (day.asInt() == date.getDayOfWeek().getValue()) return true;
        }
        return false;
    }

    private ObjectNode schedule(JsonNode config) {
        if (!config.path("schedule").isObject() && config instanceof ObjectNode objectNode)
            objectNode.set("schedule", objectMapper.createObjectNode());
        return (ObjectNode) config.path("schedule");
    }

    private ZoneId zone(JsonNode config) {
        try {
            return ZoneId.of(schedule(config).path("timezone").asText("Asia/Shanghai"));
        } catch (Exception exception) {
            throw BusinessException.validation("日报规则时区不正确");
        }
    }

    private void normalizeTime(ObjectNode schedule, String key, String fallback) {
        String value = schedule.path(key).asText(fallback);
        if (!isTime(value)) throw BusinessException.validation(key + "必须为HH:mm");
        schedule.put(key, value);
    }

    private boolean isTime(String value) {
        try {
            LocalTime.parse(value);
            return value.matches("[0-2][0-9]:[0-5][0-9]") && LocalTime.parse(value).getHour() < 24;
        } catch (RuntimeException exception) {
            return false;
        }
    }

    private String deadlineLabel(JsonNode config) {
        return schedule(config).path("deadlineTime").asText("23:00")
                + "（"
                + schedule(config).path("timezone").asText("Asia/Shanghai")
                + "）";
    }

    private Long parseSubmissionId(String value) {
        try {
            long id = Long.parseLong(value);
            if (id <= 0) throw new NumberFormatException(value);
            return id;
        } catch (NumberFormatException exception) {
            throw BusinessException.validation("日报提交记录标识不正确");
        }
    }

    private ObjectNode snapshot(JsonNode config) {
        ObjectNode result = config.deepCopy();
        result.remove("notificationChannels");
        return result;
    }

    private ObjectNode ruleConfig(DailyReportRule rule) {
        ObjectNode config = readObject(rule.getConfigJson());
        String ruleKey = rule.getRuleKey() == null ? config.path("id").asText() : rule.getRuleKey();
        normalizeFixedReportDefinition(ruleKey, config);
        return config;
    }

    /** 素材师月报沿用历史日报规则 ID；服务端强制月度语义，避免旧客户端恢复为日周期。 */
    private void normalizeFixedReportDefinition(String ruleKey, ObjectNode config) {
        if (!MATERIAL_DESIGNER_MONTHLY_REPORT_RULE_KEY.equals(ruleKey)) return;

        config.put("name", "素材师月报");
        config.put("period", "每月");
        ObjectNode reportSchedule = schedule(config);
        int submissionDayOfMonth = reportSchedule.path("submissionDayOfMonth").asInt(1);
        if (submissionDayOfMonth < 1 || submissionDayOfMonth > 28) submissionDayOfMonth = 1;
        reportSchedule.putArray("submissionDays");
        reportSchedule.put("submissionDayOfMonth", submissionDayOfMonth);
    }

    private ObjectNode visibleRuleView(ObjectNode config, CurrentUser user) {
        ObjectNode result = config.deepCopy();
        result.put("canWrite", canWrite(config, user));
        return result;
    }

    private ObjectNode submissionView(DailyReportSubmission submission) {
        ObjectNode result = objectMapper.createObjectNode();
        ObjectNode snapshot = readObject(submission.getRuleSnapshotJson());
        result.put("id", submission.getId().toString());
        result.put("ruleId", snapshot.path("id").asText());
        result.put("author", submission.getSubmittedByName());
        result.put("authorId", submission.getSubmittedById().toString());
        result.put("createdAt", submission.getCreatedAt().toString());
        result.set("fields", readObject(submission.getFieldValuesJson()));
        result.set("attachments", readObject(submission.getAttachmentsJson()));
        result.set("ruleSnapshot", snapshot);
        return result;
    }

    private ObjectNode readObject(String json) {
        try {
            JsonNode parsed = objectMapper.readTree(json == null ? "{}" : json);
            return parsed.isObject() ? (ObjectNode) parsed : objectMapper.createObjectNode();
        } catch (JsonProcessingException exception) {
            throw new IllegalStateException("日报数据无法解析", exception);
        }
    }

    private String writeJson(JsonNode value) {
        try {
            return objectMapper.writeValueAsString(value);
        } catch (JsonProcessingException exception) {
            throw new IllegalStateException("日报数据无法写入", exception);
        }
    }

    private String text(JsonNode node, String key) {
        String value = node.path(key).asText("").trim();
        return value.isEmpty() ? null : value;
    }
}
