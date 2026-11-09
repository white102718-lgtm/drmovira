package com.adpulse.main.adaccountasset;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.anyLong;
import static org.mockito.ArgumentMatchers.eq;
import static org.mockito.ArgumentMatchers.isNull;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

import com.adpulse.main.adaccountasset.AdAccountAssetModels.AdAccountAsset;
import com.adpulse.main.adaccountasset.AdAccountAssetService.AdAccountAssetException;
import com.adpulse.main.adaccountasset.AdAccountAssetViews.FacebookActivityPage;
import java.time.LocalDateTime;
import java.time.ZoneId;
import java.util.List;
import org.bson.Document;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.ArgumentCaptor;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;
import org.springframework.data.mongodb.core.MongoTemplate;
import org.springframework.data.mongodb.core.query.Query;

/** Facebook 操作记录的个号 Token 选择与查询边界测试。 */
@ExtendWith(MockitoExtension.class)
class FacebookAdActivityServiceTest {
    @Mock private MongoTemplate mongoTemplate;
    @Mock private AdAccountAssetMapper assetMapper;
    @Mock private FacebookAdActivityClient client;

    private FacebookAdActivityService service;

    @BeforeEach
    void setUp() {
        service =
                new FacebookAdActivityService(
                        mongoTemplate, assetMapper, client, "personal_accounts");
    }

    @Test
    void shouldUseFirstActivePersonalAccountToken() {
        AdAccountAsset asset = asset("123");
        FacebookActivityPage expected =
                new FacebookActivityPage(List.of(), null, false, 1L, 2_000_000_000L);
        when(assetMapper.findByAccountId("123")).thenReturn(asset);
        when(mongoTemplate.findOne(any(Query.class), eq(Document.class), eq("personal_accounts")))
                .thenReturn(new Document("access_token", "first-token"));
        when(client.list(
                        eq("first-token"),
                        eq("123"),
                        anyLong(),
                        eq(2_000_000_000L),
                        isNull(),
                        eq(100)))
                .thenReturn(expected);

        FacebookActivityPage result = service.list("act_123", null, 2_000_000_000L, 200);

        assertThat(result).isSameAs(expected);
        ArgumentCaptor<Query> queryCaptor = ArgumentCaptor.forClass(Query.class);
        verify(mongoTemplate)
                .findOne(queryCaptor.capture(), eq(Document.class), eq("personal_accounts"));
        String query = queryCaptor.getValue().getQueryObject().toJson();
        assertThat(query)
                .contains("\"status\": true")
                .contains("\"accounts.id\"")
                .contains("\"123\"")
                .contains("\"act_123\"");
    }

    @Test
    void shouldRejectWhenNoActiveTokenMatches() {
        when(assetMapper.findByAccountId("123")).thenReturn(asset("123"));
        when(mongoTemplate.findOne(any(Query.class), eq(Document.class), eq("personal_accounts")))
                .thenReturn(null);

        assertThatThrownBy(() -> service.list("123", null, null, 50))
                .isInstanceOf(AdAccountAssetException.class)
                .hasMessage("未找到可访问该广告账户的有效个号 Token");
    }

    private AdAccountAsset asset(String accountId) {
        AdAccountAsset asset = new AdAccountAsset();
        asset.setAccountId(accountId);
        asset.setTimezone("Asia/Shanghai");
        asset.setCreatedAt(LocalDateTime.of(2026, 9, 1, 0, 0));
        long since = asset.getCreatedAt().atZone(ZoneId.of("Asia/Shanghai")).toEpochSecond();
        assertThat(since).isPositive();
        return asset;
    }
}
