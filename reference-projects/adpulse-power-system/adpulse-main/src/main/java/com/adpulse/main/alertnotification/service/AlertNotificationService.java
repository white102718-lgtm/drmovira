package com.adpulse.main.alertnotification.service;

import com.adpulse.main.alertnotification.dto.AlertRequests.ConfigSave;
import com.adpulse.main.alertnotification.dto.AlertRequests.RecipientSave;
import com.adpulse.main.alertnotification.dto.AlertRequests.TestDelivery;
import com.adpulse.main.alertnotification.dto.AlertViews.Settings;
import com.adpulse.main.alertnotification.dto.AlertViews.TestDeliveryResult;
import com.adpulse.main.alertnotification.mapper.AlertNotificationMapper;
import com.adpulse.main.alertnotification.model.AlertModels.Config;
import com.adpulse.main.alertnotification.model.AlertModels.Recipient;
import com.adpulse.main.alertnotification.mongo.AlertMongoEventProvider;
import com.adpulse.main.alertnotification.mongo.AlertMongoEventProvider.BanEvent;
import com.adpulse.main.alertnotification.mongo.AlertMongoEventProvider.ChangeEvent;
import java.math.BigDecimal;
import java.time.LocalDate;
import java.time.LocalDateTime;
import java.time.LocalTime;
import java.time.ZoneId;
import java.time.format.DateTimeFormatter;
import java.time.temporal.ChronoUnit;
import java.util.Comparator;
import java.util.HashSet;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Set;
import java.util.stream.Collectors;
import org.springframework.dao.DataIntegrityViolationException;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

/** 管理全局预警配置，并评估封号、限额变化和账户消耗规则。 */
@Service
public class AlertNotificationService {
    private static final ZoneId BEIJING = ZoneId.of("Asia/Shanghai");
    private static final int DEFAULT_LIMIT_POLL_INTERVAL_MINUTES = 15;
    private static final Set<Integer> LIMIT_POLL_INTERVALS = Set.of(5, 10, 15, 30, 60);
    private static final DateTimeFormatter HOUR_KEY = DateTimeFormatter.ofPattern("yyyyMMddHH");
    private static final DateTimeFormatter DATE_KEY = DateTimeFormatter.ofPattern("yyyyMMdd");
    private static final DateTimeFormatter DISPLAY_DATE = DateTimeFormatter.ofPattern("yyyy-MM-dd");
    private static final DateTimeFormatter DISPLAY_TIME =
            DateTimeFormatter.ofPattern("yyyy-MM-dd HH:mm");
    private final AlertNotificationMapper mapper;
    private final AlertMongoEventProvider mongoEvents;
    private final AlertFeishuSender feishuSender;

    public AlertNotificationService(
            AlertNotificationMapper mapper,
            AlertMongoEventProvider mongoEvents,
            AlertFeishuSender feishuSender) {
        this.mapper = mapper;
        this.mongoEvents = mongoEvents;
        this.feishuSender = feishuSender;
    }

    public Settings settings() {
        return new Settings(mapper.findConfig(), mapper.findRecipients());
    }

    @Transactional
    public Settings save(ConfigSave request, Long userId) {
        validate(request, true);
        Config current = mapper.findConfig();
        int interval = limitPollInterval(request.limitPollIntervalMinutes());
        boolean currentlyEnabled = isLimitChangeEnabled(current);
        boolean newlyEnabled =
                Boolean.TRUE.equals(request.enabled()) && request.limitChangeEnabled();
        LocalDateTime enabledAt =
                !newlyEnabled
                        ? null
                        : currentlyEnabled && current.limitChangeEnabledAt != null
                                ? current.limitChangeEnabledAt
                                : LocalDateTime.now(BEIJING);
        mapper.updateConfig(request, interval, enabledAt, userId);
        mapper.deleteRecipients();
        request.recipients().stream()
                .map(this::normalizedRecipient)
                .distinct()
                .forEach(mapper::insertRecipient);
        return settings();
    }

    /** 向页面当前填写的收件目标发送测试文本，不生成正式提醒或投递记录。 */
    public TestDeliveryResult testDelivery(TestDelivery request) {
        validateRecipients(request.recipients(), true);
        int successCount = 0;
        int failedCount = 0;
        String content =
                "AdPulse 预警通知测试\n发送时间："
                        + DISPLAY_TIME.format(LocalDateTime.now(BEIJING))
                        + "\n如果你收到此消息，说明飞书通知配置正常。";
        for (RecipientSave target : request.recipients()) {
            AlertFeishuSender.DeliveryResult result =
                    feishuSender.send(recipient(normalizedRecipient(target)), content);
            if (result.success()) {
                successCount++;
            } else {
                failedCount++;
            }
        }
        return new TestDeliveryResult(successCount, failedCount);
    }

    /** 按配置的自然分钟边界扫描最近一个时间窗口内的限额变化事件。 */
    public void evaluateLimitChanges() {
        evaluateLimitChanges(LocalDateTime.now(BEIJING));
    }

    void evaluateLimitChanges(LocalDateTime now) {
        Config config = mapper.findConfig();
        if (!isLimitChangeEnabled(config)) return;

        int interval = limitPollInterval(config.limitPollIntervalMinutes);
        LocalDateTime windowEnd = now.truncatedTo(ChronoUnit.MINUTES);
        if (windowEnd.getMinute() % interval != 0) return;

        LocalDateTime windowStart = windowEnd.minusMinutes(interval);
        if (config.limitChangeEnabledAt != null
                && config.limitChangeEnabledAt.isAfter(windowStart)) {
            windowStart = config.limitChangeEnabledAt;
        }
        if (!windowStart.isBefore(windowEnd)) return;
        evaluateLimitChanges(windowStart, windowEnd, mapper.findRecipients());
    }

    /** 每小时整点统计上一个完整自然小时；只有该小时出现封户时才发送提醒。 */
    public void evaluateHourlyBan() {
        evaluateHourlyBan(LocalDateTime.now(BEIJING));
    }

    void evaluateHourlyBan(LocalDateTime now) {
        Config config = mapper.findConfig();
        if (config == null
                || !Boolean.TRUE.equals(config.enabled)
                || !Boolean.TRUE.equals(config.banEnabled)) return;

        LocalDateTime windowEnd = now.truncatedTo(ChronoUnit.HOURS);
        LocalDateTime windowStart = windowEnd.minusHours(1);
        List<BanEvent> recentEvents = distinctBanAccounts(banEvents(windowStart, windowEnd));
        if (recentEvents.isEmpty()) return;

        String content =
                "统计时段："
                        + DISPLAY_TIME.format(windowStart)
                        + " - "
                        + DISPLAY_TIME.format(windowEnd)
                        + "\n最近一小时封户："
                        + recentEvents.size()
                        + " 户\n封户广告户：\n"
                        + eventLines(recentEvents);
        BanEvent latestEvent = recentEvents.getLast();
        createAndDeliver(
                "BAN_THRESHOLD",
                "BAN_HOURLY:" + HOUR_KEY.format(windowEnd),
                "广告户封户小时提醒",
                content,
                null,
                null,
                BigDecimal.valueOf(recentEvents.size()),
                BigDecimal.ONE,
                null,
                latestEvent.id(),
                windowEnd,
                mapper.findRecipients());
    }

    /** 北京时间 10:00 汇总当天零点至 10:00 的封号广告户。 */
    public void evaluateMorningBanSummary() {
        evaluateMorningBanSummary(LocalDateTime.now(BEIJING));
    }

    void evaluateMorningBanSummary(LocalDateTime now) {
        LocalDate reportDate = now.toLocalDate();
        evaluateDailyBanSummary(reportDate, reportDate.atTime(10, 0), "1000", false);
    }

    /** 北京时间 18:30 汇总当天零点至 18:30 的封号广告户。 */
    public void evaluateEveningBanSummary() {
        evaluateEveningBanSummary(LocalDateTime.now(BEIJING));
    }

    void evaluateEveningBanSummary(LocalDateTime now) {
        LocalDate reportDate = now.toLocalDate();
        evaluateDailyBanSummary(reportDate, reportDate.atTime(18, 30), "1830", false);
    }

    /** 次日零点汇总前一完整自然日，固定使用零点边界，避免读入第二天事件。 */
    public void evaluatePreviousDayBanSummary() {
        evaluatePreviousDayBanSummary(LocalDateTime.now(BEIJING));
    }

    void evaluatePreviousDayBanSummary(LocalDateTime now) {
        LocalDate reportDate = now.toLocalDate().minusDays(1);
        evaluateDailyBanSummary(reportDate, reportDate.plusDays(1).atStartOfDay(), "2400", true);
    }

    private void evaluateDailyBanSummary(
            LocalDate reportDate, LocalDateTime windowEnd, String summarySlot, boolean endOfDay) {
        Config config = mapper.findConfig();
        if (config == null
                || !Boolean.TRUE.equals(config.enabled)
                || !Boolean.TRUE.equals(config.banEnabled)) return;

        LocalDateTime windowStart = reportDate.atStartOfDay();
        List<BanEvent> events = distinctBanAccounts(banEvents(windowStart, windowEnd));
        if (events.isEmpty()) return;

        String title =
                endOfDay ? "广告户封户当日汇总提醒（24:00）" : "广告户封户汇总提醒（" + slotDisplay(summarySlot) + "）";
        String content =
                (endOfDay ? "汇总日期：" + DISPLAY_DATE.format(reportDate) + "\n" : "")
                        + "汇总时段："
                        + DISPLAY_TIME.format(windowStart)
                        + " - "
                        + DISPLAY_TIME.format(windowEnd)
                        + (endOfDay ? "\n全天封户：" : "\n累计封户：")
                        + events.size()
                        + " 户\n封户广告户：\n"
                        + eventLines(events);
        BanEvent latestEvent = events.getLast();
        createAndDeliver(
                "BAN_THRESHOLD",
                "BAN_SUMMARY:" + DATE_KEY.format(reportDate) + ":" + summarySlot,
                title,
                content,
                null,
                null,
                BigDecimal.valueOf(events.size()),
                BigDecimal.ONE,
                null,
                latestEvent.id(),
                windowEnd,
                mapper.findRecipients());
    }

    private List<BanEvent> banEvents(LocalDateTime startInclusive, LocalDateTime endExclusive) {
        return mongoEvents.banEventsBetween(
                startInclusive.atZone(BEIJING).toInstant(),
                endExclusive.atZone(BEIJING).toInstant());
    }

    /** 同一窗口内按广告户 ID 去重并保留最后一次封号；缺少 ID 时按事件分别保留。 */
    private List<BanEvent> distinctBanAccounts(List<BanEvent> events) {
        LinkedHashMap<String, BanEvent> latestByAccount = new LinkedHashMap<>();
        for (BanEvent event : events) {
            latestByAccount.put(banAccountKey(event), event);
        }
        return latestByAccount.values().stream()
                .sorted(
                        Comparator.comparing(BanEvent::detectedAt)
                                .thenComparing(
                                        BanEvent::id, Comparator.nullsFirst(String::compareTo)))
                .toList();
    }

    private String banAccountKey(BanEvent event) {
        String accountId = event.accountId();
        return accountId == null || accountId.isBlank()
                ? "EVENT:" + value(event.id(), "UNKNOWN")
                : "ACCOUNT:" + accountId.trim();
    }

    private String slotDisplay(String summarySlot) {
        return switch (summarySlot) {
            case "1000" -> LocalTime.of(10, 0).toString();
            case "1830" -> LocalTime.of(18, 30).toString();
            default -> summarySlot;
        };
    }

    private String eventLines(List<BanEvent> events) {
        if (events.isEmpty()) return "无";
        return events.stream()
                .map(
                        event ->
                                "- "
                                        + value(event.accountName(), "未命名")
                                        + "（"
                                        + value(event.accountId(), "未知ID")
                                        + "，封户时间："
                                        + DISPLAY_TIME.format(event.detectedAt())
                                        + "）")
                .collect(Collectors.joining("\n"));
    }

    private void evaluateLimitChanges(
            LocalDateTime windowStart, LocalDateTime windowEnd, List<Recipient> recipients) {
        LocalDateTime pageDetectedAt = null;
        String pageEventId = null;
        while (true) {
            List<ChangeEvent> events =
                    mongoEvents.limitEventsBetween(
                            windowStart, windowEnd, pageDetectedAt, pageEventId, 500);
            if (events.isEmpty()) return;
            for (ChangeEvent event : events) {
                deliverLimitChange(event, recipients);
            }
            if (events.size() < 500) return;
            ChangeEvent lastEvent = events.getLast();
            pageDetectedAt = lastEvent.detectedAt();
            pageEventId = lastEvent.id();
        }
    }

    private void deliverLimitChange(ChangeEvent event, List<Recipient> recipients) {
        String content =
                "广告户："
                        + value(event.accountName(), "未命名")
                        + "（"
                        + event.accountId()
                        + "）\n变化类型："
                        + changeText(event.changeType())
                        + "\n原限额："
                        + amount(event.previousValue())
                        + "\n新限额："
                        + amount(event.currentValue());
        createAndDeliver(
                "LIMIT_CHANGE",
                "LIMIT_CHANGE:" + event.id(),
                "广告户限额变化通知",
                content,
                event.accountId(),
                event.accountName(),
                event.currentValue(),
                event.previousValue(),
                event.currency(),
                event.id(),
                event.detectedAt(),
                recipients);
    }

    private void createAndDeliver(
            String type,
            String dedupeKey,
            String title,
            String content,
            String accountId,
            String accountName,
            BigDecimal triggerValue,
            BigDecimal thresholdValue,
            String currency,
            String sourceEventId,
            LocalDateTime occurredAt,
            List<Recipient> recipients) {
        int inserted =
                mapper.insertNotification(
                        type,
                        dedupeKey,
                        title,
                        content,
                        accountId,
                        accountName,
                        triggerValue,
                        thresholdValue,
                        currency,
                        sourceEventId,
                        occurredAt);
        if (inserted != 1) return;
        Long notificationId = mapper.findNotificationIdByDedupeKey(dedupeKey);
        for (Recipient recipient : recipients) {
            AlertFeishuSender.DeliveryResult result =
                    feishuSender.send(recipient, title + "\n" + content);
            mapper.insertDelivery(
                    notificationId,
                    recipient.recipientType,
                    recipient.recipientKey,
                    recipient.recipientName,
                    result.success() ? "SUCCESS" : "FAILED",
                    result.errorMessage(),
                    result.success() ? LocalDateTime.now(BEIJING) : null);
        }
    }

    private void validate(ConfigSave request, boolean requireRecipients) {
        validateRecipients(request.recipients(), requireRecipients && request.enabled());
        validUnit(request.banWindowUnit());
        limitPollInterval(request.limitPollIntervalMinutes());
    }

    private void validateRecipients(List<RecipientSave> recipients, boolean required) {
        if (required && recipients.isEmpty()) {
            throw new IllegalArgumentException("至少配置一个收件目标");
        }
        Set<String> keys = new HashSet<>();
        for (RecipientSave recipient : recipients) {
            String type = recipient.recipientType().trim().toUpperCase();
            if (!Set.of("USER", "CHAT").contains(type)) {
                throw new IllegalArgumentException("收件人类型仅支持USER或CHAT");
            }
            if (!keys.add(type + ":" + recipient.recipientKey().trim())) {
                throw new DataIntegrityViolationException("收件人不能重复");
            }
        }
    }

    private RecipientSave normalizedRecipient(RecipientSave value) {
        return new RecipientSave(
                value.recipientType().trim().toUpperCase(),
                value.recipientKey().trim(),
                value.recipientName().trim());
    }

    private Recipient recipient(RecipientSave value) {
        Recipient recipient = new Recipient();
        recipient.recipientType = value.recipientType();
        recipient.recipientKey = value.recipientKey();
        recipient.recipientName = value.recipientName();
        return recipient;
    }

    private void validUnit(String unit) {
        if (!Set.of("HOURS", "DAYS").contains(unit.toUpperCase())) {
            throw new IllegalArgumentException("时间单位仅支持HOURS或DAYS");
        }
    }

    private int limitPollInterval(Integer value) {
        int interval = value == null ? DEFAULT_LIMIT_POLL_INTERVAL_MINUTES : value;
        if (!LIMIT_POLL_INTERVALS.contains(interval)) {
            throw new IllegalArgumentException("限额轮询间隔仅支持5、10、15、30或60分钟");
        }
        return interval;
    }

    private boolean isLimitChangeEnabled(Config config) {
        return config != null
                && Boolean.TRUE.equals(config.enabled)
                && Boolean.TRUE.equals(config.limitChangeEnabled);
    }

    private String amount(BigDecimal value) {
        return value == null ? "未设置" : value.stripTrailingZeros().toPlainString();
    }

    private String changeText(String type) {
        return switch (value(type, "")) {
            case "SET" -> "设置限额";
            case "INCREASE" -> "提高限额";
            case "DECREASE" -> "降低限额";
            case "CLEAR" -> "清空限额";
            default -> "限额变化";
        };
    }

    private String value(String preferred, String fallback) {
        return preferred == null || preferred.isBlank() ? fallback : preferred;
    }
}
