package com.adpulse.main.adaccountasset;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.eq;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

import java.math.BigDecimal;
import java.time.Instant;
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

/** 广告账户日限额变化记录查询与数据映射测试。 */
@ExtendWith(MockitoExtension.class)
class AdAccountDailyLimitChangeServiceTest {
    @Mock private MongoTemplate mongoTemplate;

    private AdAccountDailyLimitChangeService service;

    @BeforeEach
    void setUp() {
        service = new AdAccountDailyLimitChangeService(mongoTemplate, "fb_ad_accounts");
    }

    @Test
    void shouldQueryAccountEventsInDescendingPagesAndMapBeijingTime() {
        Instant changedAt = Instant.parse("2026-09-18T02:32:07Z");
        Instant syncedAt = Instant.parse("2026-09-18T02:36:12Z");
        Document account =
                new Document("_id", "100")
                        .append("name", "账户A")
                        .append("currency", "USD")
                        .append("account_dsl", new Decimal128(new BigDecimal("1000.00")))
                        .append("updated_at", Date.from(syncedAt));
        Document event =
                new Document("_id", "event-1")
                        .append("account_id", "100")
                        .append("previous_limit", new Decimal128(new BigDecimal("800.00")))
                        .append("current_limit", new Decimal128(new BigDecimal("1000.00")))
                        .append("change_type", "INCREASE")
                        .append("detected_at", Date.from(changedAt));
        when(mongoTemplate.findOne(any(Query.class), eq(Document.class), eq("fb_ad_accounts")))
                .thenReturn(account);
        when(mongoTemplate.count(any(Query.class), eq("fb_ad_account_limit_events")))
                .thenReturn(21L);
        when(mongoTemplate.find(
                        any(Query.class), eq(Document.class), eq("fb_ad_account_limit_events")))
                .thenReturn(List.of(event));

        var result = service.list("act_100", 2, 20);

        assertThat(result.accountId()).isEqualTo("100");
        assertThat(result.accountName()).isEqualTo("账户A");
        assertThat(result.currentLimit()).isEqualByComparingTo("1000.00");
        assertThat(result.lastSyncedAt()).isEqualTo(LocalDateTime.of(2026, 9, 18, 10, 36, 12));
        assertThat(result.items())
                .singleElement()
                .satisfies(
                        item -> {
                            assertThat(item.previousLimit()).isEqualByComparingTo("800.00");
                            assertThat(item.currentLimit()).isEqualByComparingTo("1000.00");
                            assertThat(item.changeType()).isEqualTo("INCREASE");
                            assertThat(item.source()).isEqualTo("FACEBOOK");
                            assertThat(item.changedAt())
                                    .isEqualTo(LocalDateTime.of(2026, 9, 18, 10, 32, 7));
                        });

        ArgumentCaptor<Query> eventQuery = ArgumentCaptor.forClass(Query.class);
        verify(mongoTemplate)
                .find(eventQuery.capture(), eq(Document.class), eq("fb_ad_account_limit_events"));
        assertThat(eventQuery.getValue().getQueryObject().toJson()).contains("account_id", "100");
        assertThat(eventQuery.getValue().getSortObject().toJson())
                .contains("detected_at", "_id", "-1");
        assertThat(eventQuery.getValue().getSkip()).isEqualTo(20);
        assertThat(eventQuery.getValue().getLimit()).isEqualTo(20);
    }

    @Test
    void shouldReturnSetEventAndFallbackSummaryWhenSnapshotIsMissing() {
        Document event =
                new Document("_id", "event-2")
                        .append("account_id", "abc")
                        .append("account_name", "历史账户")
                        .append("currency", "EUR")
                        .append("previous_limit", null)
                        .append("current_limit", new Decimal128(new BigDecimal("500.00")))
                        .append("change_type", "SET")
                        .append("detected_at", Date.from(Instant.parse("2026-09-18T03:00:00Z")));
        when(mongoTemplate.findOne(any(Query.class), eq(Document.class), eq("fb_ad_accounts")))
                .thenReturn(null);
        when(mongoTemplate.count(any(Query.class), eq("fb_ad_account_limit_events")))
                .thenReturn(1L);
        when(mongoTemplate.find(
                        any(Query.class), eq(Document.class), eq("fb_ad_account_limit_events")))
                .thenReturn(List.of(event));

        var result = service.list("abc", 0, 0);

        assertThat(result.accountName()).isEqualTo("历史账户");
        assertThat(result.currency()).isEqualTo("EUR");
        assertThat(result.currentLimit()).isNull();
        assertThat(result.lastSyncedAt()).isNull();
        assertThat(result.page()).isEqualTo(1);
        assertThat(result.pageSize()).isEqualTo(20);
        assertThat(result.items()).singleElement().extracting("changeType").isEqualTo("SET");
    }
}
