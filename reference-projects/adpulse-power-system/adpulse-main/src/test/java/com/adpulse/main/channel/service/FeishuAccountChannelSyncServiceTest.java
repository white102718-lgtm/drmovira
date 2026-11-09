package com.adpulse.main.channel.service;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.Mockito.never;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

import com.adpulse.main.adaccountasset.AdAccountAssetMapper;
import com.adpulse.main.adaccountasset.AdAccountAssetModels.AdAccountAsset;
import com.adpulse.main.adaccountasset.AdAccountAssetService;
import com.adpulse.main.channel.mapper.ChannelMapper;
import com.adpulse.main.channel.model.ChannelModels.Channel;
import java.time.Instant;
import java.time.LocalDate;
import java.util.Date;
import org.bson.Document;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.ArgumentCaptor;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;
import org.springframework.data.mongodb.core.MongoTemplate;

/** 飞书业务资料同步到统一广告账户资产表的测试。 */
@ExtendWith(MockitoExtension.class)
class FeishuAccountChannelSyncServiceTest {
    @Mock private MongoTemplate mongoTemplate;
    @Mock private AdAccountAssetMapper assetMapper;
    @Mock private AdAccountAssetService assetService;
    @Mock private ChannelMapper channelMapper;

    @Test
    void shouldSynchronizePlatformAndFeishuWhenDisabledValueIsMissing() {
        Document platformAccount =
                new Document("_id", "act_123").append("name", "平台账户").append("account_status", 1);
        Document feishuRecord = new Document("account_id", "act_123");
        when(mongoTemplate.findAll(Document.class, "fb_ad_accounts"))
                .thenReturn(java.util.List.of(platformAccount));
        when(mongoTemplate.findAll(Document.class, "feishu_account_used_record"))
                .thenReturn(java.util.List.of(feishuRecord));

        service().synchronize();

        verify(assetMapper).countEnabledDictionaryValue("AD_ACCOUNT_ASSET_FEISHU_SYNC", "0");
        verify(assetService).syncPlatformAsset(any());
        verify(assetService).syncFeishuAsset(any());
    }

    @Test
    void shouldOnlySynchronizePlatformWhenFeishuSyncIsDisabled() {
        Document platformAccount =
                new Document("_id", "act_123").append("name", "平台账户").append("account_status", 1);
        when(mongoTemplate.findAll(Document.class, "fb_ad_accounts"))
                .thenReturn(java.util.List.of(platformAccount));
        when(assetMapper.countEnabledDictionaryValue("AD_ACCOUNT_ASSET_FEISHU_SYNC", "0"))
                .thenReturn(1);

        service().synchronize();

        verify(assetService).syncPlatformAsset(any());
        verify(mongoTemplate, never()).findAll(Document.class, "feishu_account_used_record");
        verify(assetService, never()).syncFeishuAsset(any());
    }

    @Test
    void shouldUpsertAssetAndResolveExactChannelName() {
        Channel channel = new Channel();
        channel.setId(8L);
        channel.setChannelName("渠道A");
        channel.setStatus(1);
        when(channelMapper.findChannelByName("渠道A")).thenReturn(channel);

        service()
                .synchronizeFeishuRecord(
                        new Document("account_id", "act_123")
                                .append("channel", "渠道A")
                                .append("account_type", "企业户"));

        ArgumentCaptor<AdAccountAsset> captor = ArgumentCaptor.forClass(AdAccountAsset.class);
        verify(assetService).syncFeishuAsset(captor.capture());
        assertThat(captor.getValue().getAccountId()).isEqualTo("123");
        assertThat(captor.getValue().getChannelId()).isEqualTo(8L);
        assertThat(captor.getValue().getAccountName()).isEmpty();
    }

    @Test
    void shouldExtractDateFromFeishuDeliveryTimestamp() {
        service()
                .synchronizeFeishuRecord(
                        new Document("account_id", "act_123")
                                .append("delivery_date", "2026-03-31 16:00:00.000"));

        ArgumentCaptor<AdAccountAsset> captor = ArgumentCaptor.forClass(AdAccountAsset.class);
        verify(assetService).syncFeishuAsset(captor.capture());
        assertThat(captor.getValue().getDeliveryDate()).isEqualTo(LocalDate.of(2026, 4, 1));
    }

    @Test
    void shouldExtractDateFromMongoDeliveryDate() {
        service()
                .synchronizeFeishuRecord(
                        new Document("account_id", "act_123")
                                .append(
                                        "delivery_date",
                                        Date.from(Instant.parse("2026-03-31T16:00:00Z"))));

        ArgumentCaptor<AdAccountAsset> captor = ArgumentCaptor.forClass(AdAccountAsset.class);
        verify(assetService).syncFeishuAsset(captor.capture());
        assertThat(captor.getValue().getDeliveryDate()).isEqualTo(LocalDate.of(2026, 4, 1));
    }

    @Test
    void shouldPassEmptyDeliveryDateToMapperForUnlockedAssetToClear() {
        service().synchronizeFeishuRecord(new Document("account_id", "act_123"));

        ArgumentCaptor<AdAccountAsset> captor = ArgumentCaptor.forClass(AdAccountAsset.class);
        verify(assetService).syncFeishuAsset(captor.capture());
        assertThat(captor.getValue().getDeliveryDate()).isNull();
    }

    @Test
    void shouldRejectMalformedDeliveryDateBeforeUpsertingAsset() {
        assertThatThrownBy(
                        () ->
                                service()
                                        .synchronizeFeishuRecord(
                                                new Document("account_id", "act_123")
                                                        .append("delivery_date", "2026/09/11")))
                .isInstanceOf(java.time.format.DateTimeParseException.class);

        verify(assetService, never()).syncFeishuAsset(any());
    }

    @Test
    void shouldRejectDeliveryDateWithoutZeroPaddedMonthAndDay() {
        assertThatThrownBy(
                        () ->
                                service()
                                        .synchronizeFeishuRecord(
                                                new Document("account_id", "act_123")
                                                        .append(
                                                                "delivery_date",
                                                                "2026-3-1 16:00:00.000")))
                .isInstanceOf(java.time.format.DateTimeParseException.class);

        verify(assetService, never()).syncFeishuAsset(any());
    }

    private FeishuAccountChannelSyncService service() {
        return new FeishuAccountChannelSyncService(
                mongoTemplate,
                assetMapper,
                assetService,
                channelMapper,
                "fb_ad_accounts",
                "feishu_account_used_record");
    }
}
