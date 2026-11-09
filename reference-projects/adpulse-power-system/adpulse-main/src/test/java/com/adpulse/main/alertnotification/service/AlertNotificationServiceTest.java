package com.adpulse.main.alertnotification.service;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.anyInt;
import static org.mockito.ArgumentMatchers.eq;
import static org.mockito.ArgumentMatchers.isNull;
import static org.mockito.Mockito.never;
import static org.mockito.Mockito.times;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

import com.adpulse.main.alertnotification.dto.AlertRequests.ConfigSave;
import com.adpulse.main.alertnotification.dto.AlertRequests.RecipientSave;
import com.adpulse.main.alertnotification.dto.AlertRequests.TestDelivery;
import com.adpulse.main.alertnotification.mapper.AlertNotificationMapper;
import com.adpulse.main.alertnotification.model.AlertModels.Config;
import com.adpulse.main.alertnotification.model.AlertModels.Recipient;
import com.adpulse.main.alertnotification.mongo.AlertMongoEventProvider;
import com.adpulse.main.alertnotification.mongo.AlertMongoEventProvider.BanEvent;
import com.adpulse.main.alertnotification.mongo.AlertMongoEventProvider.ChangeEvent;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.ArgumentCaptor;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;

import java.math.BigDecimal;
import java.time.Instant;
import java.time.LocalDateTime;
import java.time.ZoneId;
import java.util.List;

/** 预警通知业务规则测试。 */
@ExtendWith(MockitoExtension.class)
class AlertNotificationServiceTest {
    private static final ZoneId BEIJING = ZoneId.of("Asia/Shanghai");

    @Mock private AlertNotificationMapper mapper;
    @Mock private AlertMongoEventProvider mongoEvents;
    @Mock private AlertFeishuSender feishuSender;

    @Test
    void shouldSendOnlyPreviousHourAccountsInHourlyBanNotification() {
        LocalDateTime windowEnd = LocalDateTime.of(2026, 9, 17, 11, 0);
        BanEvent recentOne = event("ban-2", "200", "账户B", 10, 15);
        BanEvent recentTwo = event("ban-3", "300", "账户C", 10, 45);
        when(mapper.findConfig()).thenReturn(enabledConfig());
        when(mapper.findRecipients()).thenReturn(List.of());
        when(mongoEvents.banEventsBetween(any(Instant.class), any(Instant.class)))
                .thenReturn(List.of(recentOne, recentTwo));
        when(mapper.insertNotification(
                        any(), any(), any(), any(), any(), any(), any(), any(), any(), any(),
                        any()))
                .thenReturn(1);

        service().evaluateHourlyBan(windowEnd.plusMinutes(7));

        verify(mongoEvents)
                .banEventsBetween(instant(2026, 9, 17, 10, 0), instant(2026, 9, 17, 11, 0));
        ArgumentCaptor<String> content = ArgumentCaptor.forClass(String.class);
        verify(mapper)
                .insertNotification(
                        eq("BAN_THRESHOLD"),
                        eq("BAN_HOURLY:2026091711"),
                        eq("广告户封户小时提醒"),
                        content.capture(),
                        isNull(),
                        isNull(),
                        eq(BigDecimal.valueOf(2)),
                        eq(BigDecimal.ONE),
                        isNull(),
                        eq("ban-3"),
                        eq(windowEnd));
        assertThat(content.getValue())
                .contains("最近一小时封户：2 户", "账户B（200，封户时间：2026-09-17 10:15）")
                .contains("账户C（300，封户时间：2026-09-17 10:45）")
                .doesNotContain("今日封户", "今日封户账户");
    }

    @Test
    void shouldNotCreateNotificationWhenPreviousHourHasNoBanEvents() {
        when(mapper.findConfig()).thenReturn(enabledConfig());
        when(mongoEvents.banEventsBetween(any(Instant.class), any(Instant.class)))
                .thenReturn(List.of());

        service().evaluateHourlyBan(LocalDateTime.of(2026, 9, 17, 11, 0));

        verify(mapper, never())
                .insertNotification(
                        any(), any(), any(), any(), any(), any(), any(), any(), any(), any(),
                        any());
        verify(mapper, never()).findRecipients();
    }

    @Test
    void shouldQueryTodayToFixedMorningBoundaryEvenWhenTaskStartsLate() {
        when(mapper.findConfig()).thenReturn(enabledConfig());
        when(mongoEvents.banEventsBetween(any(Instant.class), any(Instant.class)))
                .thenReturn(List.of());

        service().evaluateMorningBanSummary(LocalDateTime.of(2026, 9, 17, 10, 7));

        verify(mongoEvents)
                .banEventsBetween(instant(2026, 9, 17, 0, 0), instant(2026, 9, 17, 10, 0));
        verify(mapper, never())
                .insertNotification(
                        any(), any(), any(), any(), any(), any(), any(), any(), any(), any(),
                        any());
    }

    @Test
    void shouldQueryTodayToFixedEveningBoundary() {
        when(mapper.findConfig()).thenReturn(enabledConfig());
        when(mongoEvents.banEventsBetween(any(Instant.class), any(Instant.class)))
                .thenReturn(List.of());

        service().evaluateEveningBanSummary(LocalDateTime.of(2026, 9, 17, 18, 32));

        verify(mongoEvents)
                .banEventsBetween(instant(2026, 9, 17, 0, 0), instant(2026, 9, 17, 18, 30));
    }

    @Test
    void shouldQueryOnlyPreviousCalendarDayForMidnightSummaryWhenTaskStartsLate() {
        when(mapper.findConfig()).thenReturn(enabledConfig());
        when(mongoEvents.banEventsBetween(any(Instant.class), any(Instant.class)))
                .thenReturn(List.of());

        service().evaluatePreviousDayBanSummary(LocalDateTime.of(2026, 9, 18, 0, 1));

        verify(mongoEvents)
                .banEventsBetween(instant(2026, 9, 17, 0, 0), instant(2026, 9, 18, 0, 0));
    }

    @Test
    void shouldDeduplicateSummaryByAccountAndKeepMissingAccountIdsSeparate() {
        BanEvent firstAccountEvent = event("ban-1", "100", "账户A", 8, 30);
        BanEvent latestAccountEvent = event("ban-2", "100", "账户A", 9, 0);
        BanEvent missingAccountOne = event("ban-3", null, "未知账户一", 9, 10);
        BanEvent missingAccountTwo = event("ban-4", null, "未知账户二", 9, 20);
        when(mapper.findConfig()).thenReturn(enabledConfig());
        when(mapper.findRecipients()).thenReturn(List.of());
        when(mongoEvents.banEventsBetween(any(Instant.class), any(Instant.class)))
                .thenReturn(
                        List.of(
                                firstAccountEvent,
                                latestAccountEvent,
                                missingAccountOne,
                                missingAccountTwo));
        when(mapper.insertNotification(
                        any(), any(), any(), any(), any(), any(), any(), any(), any(), any(),
                        any()))
                .thenReturn(1);

        service().evaluateMorningBanSummary(LocalDateTime.of(2026, 9, 17, 10, 0));

        ArgumentCaptor<String> content = ArgumentCaptor.forClass(String.class);
        verify(mapper)
                .insertNotification(
                        eq("BAN_THRESHOLD"),
                        eq("BAN_SUMMARY:20260917:1000"),
                        eq("广告户封户汇总提醒（10:00）"),
                        content.capture(),
                        isNull(),
                        isNull(),
                        eq(BigDecimal.valueOf(3)),
                        eq(BigDecimal.ONE),
                        isNull(),
                        eq("ban-4"),
                        eq(LocalDateTime.of(2026, 9, 17, 10, 0)));
        assertThat(content.getValue())
                .contains("累计封户：3 户", "账户A（100，封户时间：2026-09-17 09:00）")
                .contains("未知账户一（未知ID", "未知账户二（未知ID")
                .doesNotContain("2026-09-17 08:30");
    }

    @Test
    void shouldCreateEndOfDaySummaryWithPreviousDateAndMidnightBoundary() {
        BanEvent event = event("ban-1", "100", "账户A", 23, 45);
        when(mapper.findConfig()).thenReturn(enabledConfig());
        when(mapper.findRecipients()).thenReturn(List.of());
        when(mongoEvents.banEventsBetween(any(Instant.class), any(Instant.class)))
                .thenReturn(List.of(event));
        when(mapper.insertNotification(
                        any(), any(), any(), any(), any(), any(), any(), any(), any(), any(),
                        any()))
                .thenReturn(1);

        service().evaluatePreviousDayBanSummary(LocalDateTime.of(2026, 9, 18, 0, 1));

        ArgumentCaptor<String> content = ArgumentCaptor.forClass(String.class);
        verify(mapper)
                .insertNotification(
                        eq("BAN_THRESHOLD"),
                        eq("BAN_SUMMARY:20260917:2400"),
                        eq("广告户封户当日汇总提醒（24:00）"),
                        content.capture(),
                        isNull(),
                        isNull(),
                        eq(BigDecimal.ONE),
                        eq(BigDecimal.ONE),
                        isNull(),
                        eq("ban-1"),
                        eq(LocalDateTime.of(2026, 9, 18, 0, 0)));
        assertThat(content.getValue())
                .contains(
                        "汇总日期：2026-09-17", "汇总时段：2026-09-17 00:00 - 2026-09-18 00:00", "全天封户：1 户");
    }

    @Test
    void shouldNotDeliverSameBanSummaryTwiceWhenTriggeredAgain() {
        BanEvent event = event("ban-1", "100", "账户A", 9, 30);
        Recipient recipient = new Recipient();
        recipient.recipientType = "CHAT";
        recipient.recipientKey = "oc_test";
        recipient.recipientName = "测试群";
        when(mapper.findConfig()).thenReturn(enabledConfig());
        when(mapper.findRecipients()).thenReturn(List.of(recipient));
        when(mongoEvents.banEventsBetween(any(Instant.class), any(Instant.class)))
                .thenReturn(List.of(event));
        when(mapper.insertNotification(
                        any(), any(), any(), any(), any(), any(), any(), any(), any(), any(),
                        any()))
                .thenReturn(1, 0);
        when(mapper.findNotificationIdByDedupeKey("BAN_SUMMARY:20260917:1000")).thenReturn(1L);
        when(feishuSender.send(any(), any()))
                .thenReturn(new AlertFeishuSender.DeliveryResult(true, null));

        LocalDateTime now = LocalDateTime.of(2026, 9, 17, 10, 0);
        service().evaluateMorningBanSummary(now);
        service().evaluateMorningBanSummary(now);

        verify(feishuSender, times(1)).send(eq(recipient), any());
        verify(mapper, times(1)).insertDelivery(any(), any(), any(), any(), any(), any(), any());
    }

    @Test
    void shouldQueryConfiguredLimitWindowAtNaturalBoundary() {
        Config config = enabledLimitConfig();
        when(mapper.findConfig()).thenReturn(config);
        when(mapper.findRecipients()).thenReturn(List.of());
        when(mongoEvents.limitEventsBetween(any(), any(), any(), any(), eq(500)))
                .thenReturn(List.of());

        service().evaluateLimitChanges(LocalDateTime.of(2026, 9, 18, 10, 15, 42));

        verify(mongoEvents)
                .limitEventsBetween(
                        LocalDateTime.of(2026, 9, 18, 10, 0),
                        LocalDateTime.of(2026, 9, 18, 10, 15),
                        null,
                        null,
                        500);
    }

    @Test
    void shouldSkipLimitWindowOutsideNaturalBoundary() {
        when(mapper.findConfig()).thenReturn(enabledLimitConfig());

        service().evaluateLimitChanges(LocalDateTime.of(2026, 9, 18, 10, 16));

        verify(mongoEvents, never()).limitEventsBetween(any(), any(), any(), any(), anyInt());
        verify(mapper, never()).findRecipients();
    }

    @Test
    void shouldExcludeLimitEventsCreatedBeforeNotificationWasEnabled() {
        Config config = enabledLimitConfig();
        config.limitChangeEnabledAt = LocalDateTime.of(2026, 9, 18, 10, 7, 30);
        when(mapper.findConfig()).thenReturn(config);
        when(mapper.findRecipients()).thenReturn(List.of());
        when(mongoEvents.limitEventsBetween(any(), any(), any(), any(), eq(500)))
                .thenReturn(List.of());

        service().evaluateLimitChanges(LocalDateTime.of(2026, 9, 18, 10, 15));

        verify(mongoEvents)
                .limitEventsBetween(
                        config.limitChangeEnabledAt,
                        LocalDateTime.of(2026, 9, 18, 10, 15),
                        null,
                        null,
                        500);
    }

    @Test
    void shouldNotDeliverSameLimitEventTwiceWhenWindowIsScannedAgain() {
        Config config = enabledLimitConfig();
        Recipient recipient = new Recipient();
        recipient.recipientType = "CHAT";
        recipient.recipientKey = "oc_test";
        recipient.recipientName = "测试群";
        ChangeEvent event =
                new ChangeEvent(
                        "limit-1",
                        "100",
                        "账户A",
                        "USD",
                        BigDecimal.valueOf(500),
                        BigDecimal.valueOf(800),
                        "INCREASE",
                        LocalDateTime.of(2026, 9, 18, 10, 8));
        when(mapper.findConfig()).thenReturn(config);
        when(mapper.findRecipients()).thenReturn(List.of(recipient));
        when(mongoEvents.limitEventsBetween(any(), any(), any(), any(), eq(500)))
                .thenReturn(List.of(event));
        when(mapper.insertNotification(
                        any(), any(), any(), any(), any(), any(), any(), any(), any(), any(),
                        any()))
                .thenReturn(1, 0);
        when(mapper.findNotificationIdByDedupeKey("LIMIT_CHANGE:limit-1")).thenReturn(1L);
        when(feishuSender.send(any(), any()))
                .thenReturn(new AlertFeishuSender.DeliveryResult(true, null));

        LocalDateTime now = LocalDateTime.of(2026, 9, 18, 10, 15);
        service().evaluateLimitChanges(now);
        service().evaluateLimitChanges(now);

        verify(feishuSender, times(1))
                .send(recipient, "广告户限额变化通知\n广告户：账户A（100）\n变化类型：提高限额\n原限额：500\n新限额：800");
        verify(mapper, times(1)).insertDelivery(any(), any(), any(), any(), any(), any(), any());
    }

    @Test
    void shouldDefaultMissingLimitPollIntervalToFifteenMinutes() {
        ConfigSave request = new ConfigSave(false, true, 1, 1, "HOURS", true, null, List.of());
        when(mapper.findConfig()).thenReturn(new Config());
        when(mapper.findRecipients()).thenReturn(List.of());

        service().save(request, 7L);

        verify(mapper).updateConfig(request, 15, null, 7L);
    }

    @Test
    void shouldRecordNewEnableTimeWhenLimitNotificationIsReenabled() {
        Config current = new Config();
        current.enabled = false;
        current.limitChangeEnabled = false;
        RecipientSave recipient = new RecipientSave("CHAT", "oc_test", "测试群");
        ConfigSave request =
                new ConfigSave(true, true, 1, 1, "HOURS", true, 15, List.of(recipient));
        when(mapper.findConfig()).thenReturn(current);
        when(mapper.findRecipients()).thenReturn(List.of());
        ArgumentCaptor<LocalDateTime> enabledAt = ArgumentCaptor.forClass(LocalDateTime.class);

        service().save(request, 7L);

        verify(mapper).updateConfig(eq(request), eq(15), enabledAt.capture(), eq(7L));
        assertThat(enabledAt.getValue()).isNotNull();
    }

    @Test
    void shouldRejectUnsupportedLimitPollInterval() {
        ConfigSave request = new ConfigSave(false, true, 1, 1, "HOURS", true, 12, List.of());

        assertThatThrownBy(() -> service().save(request, 7L))
                .isInstanceOf(IllegalArgumentException.class)
                .hasMessage("限额轮询间隔仅支持5、10、15、30或60分钟");
    }

    @Test
    void shouldSendTestMessageWithoutCreatingNotificationRecords() {
        when(feishuSender.send(any(), any()))
                .thenReturn(
                        new AlertFeishuSender.DeliveryResult(true, null),
                        new AlertFeishuSender.DeliveryResult(false, "发送失败"));

        var result =
                service()
                        .testDelivery(
                                new TestDelivery(
                                        List.of(
                                                new RecipientSave("USER", "1", "用户A"),
                                                new RecipientSave("CHAT", "oc_test", "测试群"))));

        assertThat(result.successCount()).isEqualTo(1);
        assertThat(result.failedCount()).isEqualTo(1);
        verify(mapper, never())
                .insertNotification(
                        any(), any(), any(), any(), any(), any(), any(), any(), any(), any(),
                        any());
        verify(mapper, never()).insertDelivery(any(), any(), any(), any(), any(), any(), any());
    }

    private AlertNotificationService service() {
        return new AlertNotificationService(mapper, mongoEvents, feishuSender);
    }

    private Config enabledConfig() {
        Config config = new Config();
        config.enabled = true;
        config.banEnabled = true;
        return config;
    }

    private Config enabledLimitConfig() {
        Config config = enabledConfig();
        config.limitChangeEnabled = true;
        config.limitPollIntervalMinutes = 15;
        config.limitChangeEnabledAt = LocalDateTime.of(2026, 9, 18, 9, 0);
        return config;
    }

    private BanEvent event(String id, String accountId, String accountName, int hour, int minute) {
        return new BanEvent(
                id, accountId, accountName, LocalDateTime.of(2026, 9, 17, hour, minute));
    }

    private Instant instant(int year, int month, int day, int hour, int minute) {
        return LocalDateTime.of(year, month, day, hour, minute).atZone(BEIJING).toInstant();
    }
}
