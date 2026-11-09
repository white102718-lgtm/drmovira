package com.adpulse.main.alertnotification.service;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.eq;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

import com.adpulse.main.alertnotification.dto.AlertRequests.EventRecordQuery;
import com.adpulse.main.alertnotification.dto.AlertRequests.LimitChangeRecordQuery;
import java.math.BigDecimal;
import java.time.Instant;
import java.time.LocalDate;
import java.time.LocalDateTime;
import java.util.Date;
import java.util.List;
import org.bson.Document;
import org.bson.types.Decimal128;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.ArgumentCaptor;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;
import org.springframework.data.mongodb.core.MongoTemplate;
import org.springframework.data.mongodb.core.query.Query;

/** 预警页面原始事件分页查询测试。 */
@ExtendWith(MockitoExtension.class)
class AlertEventRecordServiceTest {
    @Mock private MongoTemplate mongo;

    private AlertEventRecordService service;

    @BeforeEach
    void setUp() {
        service = new AlertEventRecordService(mongo);
    }

    @Test
    void shouldPageBanRecordsByBeijingDateAndEscapedKeyword() {
        Document event =
                new Document("_id", "ban-1")
                        .append("account_id", "100")
                        .append("account_name", "账户A")
                        .append("previous_status", 1)
                        .append("current_status", 2)
                        .append("disable_reason", "风险停用")
                        .append("currency", "USD")
                        .append("detected_at", Date.from(Instant.parse("2026-09-17T02:30:00Z")));
        when(mongo.count(any(Query.class), eq("fb_ad_account_ban_events"))).thenReturn(21L);
        when(mongo.find(any(Query.class), eq(Document.class), eq("fb_ad_account_ban_events")))
                .thenReturn(List.of(event));

        var result =
                service.listBanRecords(
                        new EventRecordQuery(
                                "账户.*",
                                LocalDate.of(2026, 9, 17),
                                LocalDate.of(2026, 9, 18),
                                2,
                                20));

        assertThat(result.total()).isEqualTo(21);
        assertThat(result.page()).isEqualTo(2);
        assertThat(result.pageSize()).isEqualTo(20);
        assertThat(result.items())
                .singleElement()
                .satisfies(
                        item -> {
                            assertThat(item.id()).isEqualTo("ban-1");
                            assertThat(item.accountId()).isEqualTo("100");
                            assertThat(item.previousStatus()).isEqualTo(1);
                            assertThat(item.currentStatus()).isEqualTo(2);
                            assertThat(item.disableReason()).isEqualTo("风险停用");
                            assertThat(item.occurredAt())
                                    .isEqualTo(LocalDateTime.of(2026, 9, 17, 10, 30));
                            assertThat(item.source()).isEqualTo("FACEBOOK");
                        });

        ArgumentCaptor<Query> queryCaptor = ArgumentCaptor.forClass(Query.class);
        verify(mongo)
                .find(queryCaptor.capture(), eq(Document.class), eq("fb_ad_account_ban_events"));
        Query query = queryCaptor.getValue();
        assertThat(query.getQueryObject().toJson())
                .contains(
                        "detected_at",
                        "$gte",
                        "$lt",
                        "account_id",
                        "account_name",
                        "\\\\Q账户.*\\\\E");
        assertThat(query.getSortObject().toJson()).contains("detected_at", "_id", "-1");
        assertThat(query.getSkip()).isEqualTo(20);
        assertThat(query.getLimit()).isEqualTo(20);
    }

    @Test
    void shouldFilterAndMapLimitChangesWithBoundedPageSize() {
        Document event =
                new Document("_id", "limit-1")
                        .append("account_id", "200")
                        .append("account_name", "账户B")
                        .append("currency", "EUR")
                        .append("previous_limit", new Decimal128(new BigDecimal("500.00")))
                        .append("current_limit", new Decimal128(new BigDecimal("800.00")))
                        .append("change_type", "INCREASE")
                        .append("detected_at", Date.from(Instant.parse("2026-09-18T03:00:00Z")));
        when(mongo.count(any(Query.class), eq("fb_ad_account_limit_events"))).thenReturn(1L);
        when(mongo.find(any(Query.class), eq(Document.class), eq("fb_ad_account_limit_events")))
                .thenReturn(List.of(event));

        var result =
                service.listLimitChangeRecords(
                        new LimitChangeRecordQuery(null, null, null, "increase", 0, 500));

        assertThat(result.page()).isEqualTo(1);
        assertThat(result.pageSize()).isEqualTo(100);
        assertThat(result.items())
                .singleElement()
                .satisfies(
                        item -> {
                            assertThat(item.previousLimit()).isEqualByComparingTo("500.00");
                            assertThat(item.currentLimit()).isEqualByComparingTo("800.00");
                            assertThat(item.changeType()).isEqualTo("INCREASE");
                            assertThat(item.currency()).isEqualTo("EUR");
                            assertThat(item.occurredAt())
                                    .isEqualTo(LocalDateTime.of(2026, 9, 18, 11, 0));
                        });

        ArgumentCaptor<Query> queryCaptor = ArgumentCaptor.forClass(Query.class);
        verify(mongo)
                .find(queryCaptor.capture(), eq(Document.class), eq("fb_ad_account_limit_events"));
        assertThat(queryCaptor.getValue().getQueryObject().toJson())
                .contains("change_type", "INCREASE");
        assertThat(queryCaptor.getValue().getLimit()).isEqualTo(100);
    }

    @Test
    void shouldReturnEmptyPageAndDefaultPagination() {
        when(mongo.count(any(Query.class), eq("fb_ad_account_ban_events"))).thenReturn(0L);
        when(mongo.find(any(Query.class), eq(Document.class), eq("fb_ad_account_ban_events")))
                .thenReturn(List.of());

        var result = service.listBanRecords(new EventRecordQuery(null, null, null, null, null));

        assertThat(result.items()).isEmpty();
        assertThat(result.total()).isZero();
        assertThat(result.page()).isEqualTo(1);
        assertThat(result.pageSize()).isEqualTo(20);
    }

    @Test
    void shouldRejectInvalidDateRangeAndLimitChangeType() {
        assertThatThrownBy(
                        () ->
                                service.listBanRecords(
                                        new EventRecordQuery(
                                                null,
                                                LocalDate.of(2026, 9, 19),
                                                LocalDate.of(2026, 9, 18),
                                                1,
                                                20)))
                .isInstanceOf(IllegalArgumentException.class)
                .hasMessage("开始日期不能晚于结束日期");

        assertThatThrownBy(
                        () ->
                                service.listLimitChangeRecords(
                                        new LimitChangeRecordQuery(
                                                null, null, null, "UNKNOWN", 1, 20)))
                .isInstanceOf(IllegalArgumentException.class)
                .hasMessage("限额变化类型不受支持");
    }
}
