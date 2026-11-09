package com.adpulse.main.channel.mongo;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.eq;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

import java.time.LocalDateTime;
import java.util.List;
import org.bson.Document;
import org.junit.jupiter.api.Test;
import org.mockito.ArgumentCaptor;
import org.mockito.Mockito;
import org.springframework.data.mongodb.core.MongoTemplate;
import org.springframework.data.mongodb.core.query.Query;

class MongoAccountSnapshotProviderTest {

    @Test
    void shouldReadActualMongoAccountFields() {
        MongoTemplate mongoTemplate = Mockito.mock(MongoTemplate.class);
        Document account =
                new Document("_id", "act-123")
                        .append("name", "测试账户")
                        .append("account_status", 1)
                        .append("updated_at", "2026-08-24T10:15:30")
                        .append("timezone_name", "Asia/Shanghai")
                        .append("owner", new Document("id", "bm-123"))
                        .append("balance", "800.25")
                        .append("amount_spent", "199.75")
                        .append("spend_cap", "1000.00")
                        .append("end_advertiser", "主体公司");
        when(mongoTemplate.find(any(Query.class), eq(Document.class), eq("fb_ad_account")))
                .thenReturn(List.of(account));
        MongoAccountSnapshotProvider provider =
                new MongoAccountSnapshotProvider(mongoTemplate, true, "fb_ad_account");

        var snapshots = provider.findByAccountIds(List.of("act-123"));

        assertThat(snapshots.get("act-123"))
                .satisfies(
                        snapshot -> {
                            assertThat(snapshot.accountName()).isEqualTo("测试账户");
                            assertThat(snapshot.status()).isEqualTo(1);
                            assertThat(snapshot.takeTime())
                                    .isEqualTo(LocalDateTime.of(2026, 8, 24, 10, 15, 30));
                            assertThat(snapshot.timezone()).isEqualTo(8);
                            assertThat(snapshot.bmId()).isEqualTo("bm-123");
                            assertThat(snapshot.balance()).isEqualByComparingTo("800.25");
                            assertThat(snapshot.amountSpent()).isEqualByComparingTo("199.75");
                            assertThat(snapshot.remainingSpendCap()).isEqualByComparingTo("800.25");
                            assertThat(snapshot.subjectName()).isEqualTo("主体公司");
                        });
        ArgumentCaptor<Query> queryCaptor = ArgumentCaptor.forClass(Query.class);
        verify(mongoTemplate).find(queryCaptor.capture(), eq(Document.class), eq("fb_ad_account"));
        assertThat(queryCaptor.getValue().getQueryObject())
                .isEqualTo(new Document("_id", new Document("$in", List.of("act-123"))));
    }
}
