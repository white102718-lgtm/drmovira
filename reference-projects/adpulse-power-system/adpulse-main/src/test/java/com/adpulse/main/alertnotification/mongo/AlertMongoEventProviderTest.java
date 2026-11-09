package com.adpulse.main.alertnotification.mongo;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.eq;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

import java.time.Instant;
import java.time.LocalDateTime;
import java.util.Date;
import java.util.List;
import org.bson.Document;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.ArgumentCaptor;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;
import org.springframework.data.mongodb.core.MongoTemplate;
import org.springframework.data.mongodb.core.query.Query;

/** 预警 Mongo 事件时间窗口查询测试。 */
@ExtendWith(MockitoExtension.class)
class AlertMongoEventProviderTest {
    @Mock private MongoTemplate mongoTemplate;

    @Test
    void shouldQueryBanEventsInHalfOpenTimeWindow() {
        Instant start = Instant.parse("2026-09-17T02:00:00Z");
        Instant end = Instant.parse("2026-09-17T03:00:00Z");
        when(mongoTemplate.find(
                        any(Query.class), eq(Document.class), eq("fb_ad_account_ban_events")))
                .thenReturn(
                        List.of(
                                new Document("_id", "ban-1")
                                        .append("account_id", "100")
                                        .append("account_name", "账户A")
                                        .append("detected_at", Date.from(start.plusSeconds(60)))));

        var events = new AlertMongoEventProvider(mongoTemplate).banEventsBetween(start, end);

        assertThat(events)
                .singleElement()
                .satisfies(
                        event -> {
                            assertThat(event.id()).isEqualTo("ban-1");
                            assertThat(event.accountId()).isEqualTo("100");
                            assertThat(event.accountName()).isEqualTo("账户A");
                        });
        ArgumentCaptor<Query> queryCaptor = ArgumentCaptor.forClass(Query.class);
        verify(mongoTemplate)
                .find(queryCaptor.capture(), eq(Document.class), eq("fb_ad_account_ban_events"));
        assertThat(queryCaptor.getValue().getQueryObject().toJson())
                .contains("$gte", "$lt", "detected_at");
    }

    @Test
    void shouldQueryOneLimitEventPageInsideHalfOpenWindow() {
        LocalDateTime start = LocalDateTime.of(2026, 9, 18, 10, 0);
        LocalDateTime end = LocalDateTime.of(2026, 9, 18, 10, 15);
        LocalDateTime pageTime = LocalDateTime.of(2026, 9, 18, 10, 8);
        when(mongoTemplate.find(
                        any(Query.class), eq(Document.class), eq("fb_ad_account_limit_events")))
                .thenReturn(List.of());

        new AlertMongoEventProvider(mongoTemplate)
                .limitEventsBetween(start, end, pageTime, "event-1", 100);

        ArgumentCaptor<Query> queryCaptor = ArgumentCaptor.forClass(Query.class);
        verify(mongoTemplate)
                .find(queryCaptor.capture(), eq(Document.class), eq("fb_ad_account_limit_events"));
        Query query = queryCaptor.getValue();
        assertThat(query.getQueryObject().toJson())
                .contains("$gte", "$lt", "$gt", "event-1", "detected_at");
        assertThat(query.getLimit()).isEqualTo(100);
        assertThat(query.getSortObject().toJson()).contains("detected_at", "_id");
    }
}
