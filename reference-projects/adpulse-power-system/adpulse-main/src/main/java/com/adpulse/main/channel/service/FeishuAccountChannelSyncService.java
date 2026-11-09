package com.adpulse.main.channel.service;

import com.adpulse.main.adaccountasset.AdAccountAssetMapper;
import com.adpulse.main.adaccountasset.AdAccountAssetModels.AdAccountAsset;
import com.adpulse.main.adaccountasset.AdAccountAssetService;
import com.adpulse.main.channel.mapper.ChannelMapper;
import com.adpulse.main.channel.model.ChannelModels.Channel;
import java.time.LocalDate;
import java.time.LocalDateTime;
import java.time.ZoneOffset;
import java.time.format.DateTimeFormatter;
import java.time.format.ResolverStyle;
import java.util.Date;
import java.util.List;
import org.bson.Document;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.data.mongodb.core.MongoTemplate;
import org.springframework.scheduling.annotation.Scheduled;
import org.springframework.stereotype.Service;

/**
 * 将 MongoDB 广告账户和飞书使用记录同步到统一广告账户资产表。
 *
 * <p>MongoDB 永远负责账户名称和平台状态；飞书每小时只维护业务资料，且不能覆盖人工锁定记录。
 */
@Service
public class FeishuAccountChannelSyncService {
    private static final Logger log =
            LoggerFactory.getLogger(FeishuAccountChannelSyncService.class);
    private static final String FEISHU_SYNC_SWITCH_DICT_CODE = "AD_ACCOUNT_ASSET_FEISHU_SYNC";
    private static final String DISABLED_SWITCH_VALUE = "0";
    private static final DateTimeFormatter DELIVERY_DATE_TIME_FORMATTER =
            DateTimeFormatter.ofPattern("uuuu-MM-dd HH:mm:ss.SSS")
                    .withResolverStyle(ResolverStyle.STRICT);
    private static final ZoneOffset SHANGHAI_OFFSET = ZoneOffset.ofHours(8);
    private final MongoTemplate mongoTemplate;
    private final AdAccountAssetMapper assetMapper;
    private final AdAccountAssetService assetService;
    private final ChannelMapper channelMapper;
    private final String accountCollection;
    private final String feishuCollection;

    public FeishuAccountChannelSyncService(
            MongoTemplate mongoTemplate,
            AdAccountAssetMapper assetMapper,
            AdAccountAssetService assetService,
            ChannelMapper channelMapper,
            @Value("${adpulse.mongo.account.collection:fb_ad_accounts}") String accountCollection,
            @Value(
                            "${adpulse.mongo.feishu-account-used-record.collection:feishu_account_used_record}")
                    String feishuCollection) {
        this.mongoTemplate = mongoTemplate;
        this.assetMapper = assetMapper;
        this.assetService = assetService;
        this.channelMapper = channelMapper;
        this.accountCollection = accountCollection;
        this.feishuCollection = feishuCollection;
    }

    /** 启动后延迟一个同步周期再执行，避免全量同步与首屏查询争抢数据库；单条异常不会阻断其他账户。 */
    @Scheduled(
            fixedDelayString = "${adpulse.feishu-account-asset-sync-delay-ms:3600000}",
            initialDelayString = "${adpulse.feishu-account-asset-sync-initial-delay-ms:3600000}")
    public void synchronize() {
        synchronizePlatformAccounts();
        if (isFeishuSyncDisabled()) {
            log.info("广告账户飞书资料同步已由系统字典暂停");
            return;
        }
        synchronizeFeishuRecords();
    }

    /** 字典未配置、已禁用或已删除时保持默认同步，仅启用值 0 明确暂停。 */
    private boolean isFeishuSyncDisabled() {
        return assetMapper.countEnabledDictionaryValue(
                        FEISHU_SYNC_SWITCH_DICT_CODE, DISABLED_SWITCH_VALUE)
                > 0;
    }

    private void synchronizePlatformAccounts() {
        for (Document document : mongoTemplate.findAll(Document.class, accountCollection)) {
            try {
                String accountId = normalizeAccountId(string(document, "_id", "account_id"));
                if (accountId == null) continue;
                AdAccountAsset snapshot = new AdAccountAsset();
                snapshot.setAccountId(accountId);
                snapshot.setAccountName(firstText(document, "name", "account_name"));
                if (snapshot.getAccountName() == null) snapshot.setAccountName("");
                snapshot.setAccountStatus(integer(document, "account_status", "status"));
                assetService.syncPlatformAsset(snapshot);
            } catch (RuntimeException exception) {
                log.warn("MongoDB广告账户快照同步失败，accountId={}", string(document, "_id"), exception);
            }
        }
    }

    private void synchronizeFeishuRecords() {
        List<Document> records = mongoTemplate.findAll(Document.class, feishuCollection);
        for (Document record : records) {
            try {
                synchronizeFeishuRecord(record);
            } catch (RuntimeException exception) {
                log.warn("飞书广告账户业务资料同步失败，accountId={}", string(record, "account_id"), exception);
            }
        }
    }

    /** 单条飞书记录使用 upsert；不存在时创建，人工锁定时仅刷新同步时间。 */
    void synchronizeFeishuRecord(Document record) {
        String accountId = normalizeAccountId(string(record, "account_id"));
        if (accountId == null) return;

        AdAccountAsset existing = assetMapper.findByAccountId(accountId);
        AdAccountAsset asset = new AdAccountAsset();
        asset.setAccountId(accountId);
        // 飞书不得成为账户名称来源；资产不存在时使用空快照等待 MongoDB 补齐。
        asset.setAccountName(existing == null ? "" : existing.getAccountName());
        asset.setAccountType(firstText(record, "account_type"));
        asset.setAccountAttribute(firstText(record, "account_attribute"));
        asset.setManagedBm(firstText(record, "management_bm_name", "manage_bm"));
        asset.setManagedBmId(firstText(record, "management_bm_id", "bm_id"));
        asset.setBackupManagedBm(
                firstText(record, "backup_management_bm_name", "backup_manage_bm"));
        asset.setBackupManagedBmId(
                firstText(record, "backup_management_bm_id", "backup_manage_bm_id"));
        asset.setTimezone(firstText(record, "timezone_name", "timezone"));
        asset.setCardStation(firstText(record, "card_platform", "card_station"));
        asset.setCardNumber(firstText(record, "card_number"));
        asset.setDeliveryDate(deliveryDate(record));
        applyChannel(asset, firstText(record, "channel", "channel_name"));
        assetService.syncFeishuAsset(asset);
    }

    private void applyChannel(AdAccountAsset asset, String channelName) {
        if (channelName == null) return;
        Channel channel = channelMapper.findChannelByName(channelName);
        if (channel == null || !Integer.valueOf(1).equals(channel.getStatus())) return;
        asset.setChannelId(channel.getId());
        asset.setChannelName(channel.getChannelName());
    }

    private String normalizeAccountId(String accountId) {
        String normalized = trimToNull(accountId);
        return normalized == null ? null : normalized.replaceFirst("^act_", "");
    }

    private String firstText(Document document, String... keys) {
        for (String key : keys) {
            String value = trimToNull(string(document, key));
            if (value != null) return value;
        }
        return null;
    }

    private Integer integer(Document document, String... keys) {
        for (String key : keys) {
            Object value = document.get(key);
            if (value instanceof Number number) return number.intValue();
            if (value != null) {
                try {
                    return Integer.valueOf(value.toString());
                } catch (NumberFormatException ignored) {
                    return null;
                }
            }
        }
        return null;
    }

    /** 同步表 Mongo Date 或固定毫秒时间戳按 UTC 解析，转换为东八区后仅保存下户日期。 */
    private LocalDate deliveryDate(Document record) {
        Object raw = record == null ? null : record.get("delivery_date");
        if (raw instanceof Date date)
            return date.toInstant().atOffset(SHANGHAI_OFFSET).toLocalDate();
        String value = firstText(record, "delivery_date");
        return value == null
                ? null
                : LocalDateTime.parse(value, DELIVERY_DATE_TIME_FORMATTER)
                        .atOffset(ZoneOffset.UTC)
                        .withOffsetSameInstant(SHANGHAI_OFFSET)
                        .toLocalDate();
    }

    private String string(Document document, String... keys) {
        if (document == null) return null;
        for (String key : keys) {
            Object value = document.get(key);
            if (value != null) return value.toString();
        }
        return null;
    }

    private String trimToNull(String value) {
        if (value == null || value.trim().isEmpty()) return null;
        return value.trim();
    }
}
