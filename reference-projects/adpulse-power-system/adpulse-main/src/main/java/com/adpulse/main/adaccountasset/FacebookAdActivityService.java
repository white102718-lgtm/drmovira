package com.adpulse.main.adaccountasset;

import static com.adpulse.main.adaccountasset.AdAccountAssetViews.FacebookActivityPage;

import com.adpulse.main.adaccountasset.AdAccountAssetModels.AdAccountAsset;
import com.adpulse.main.adaccountasset.AdAccountAssetService.AdAccountAssetException;
import com.adpulse.main.adaccountasset.FacebookAdActivityClient.FacebookActivityProviderException;
import java.time.DateTimeException;
import java.time.Instant;
import java.time.LocalDateTime;
import java.time.ZoneId;
import java.util.List;
import org.bson.Document;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.data.mongodb.core.MongoTemplate;
import org.springframework.data.mongodb.core.query.Criteria;
import org.springframework.data.mongodb.core.query.Query;
import org.springframework.stereotype.Service;

/** 广告账户 Facebook 操作记录查询服务。 */
@Service
public class FacebookAdActivityService {
    private static final int DEFAULT_PAGE_SIZE = 50;
    private static final int MAX_PAGE_SIZE = 100;
    private final MongoTemplate mongoTemplate;
    private final AdAccountAssetMapper assetMapper;
    private final FacebookAdActivityClient client;
    private final String personalAccountCollection;

    public FacebookAdActivityService(
            MongoTemplate mongoTemplate,
            AdAccountAssetMapper assetMapper,
            FacebookAdActivityClient client,
            @Value("${adpulse.mongo.personal-account.collection:personal_accounts}")
                    String personalAccountCollection) {
        this.mongoTemplate = mongoTemplate;
        this.assetMapper = assetMapper;
        this.client = client;
        this.personalAccountCollection = personalAccountCollection;
    }

    /** 查询一页 Facebook 操作记录。个号凭证只取 {@code status=true} 的第一条匹配数据，不做失效 Token 回退，确保选择规则与资源库一致。 */
    public FacebookActivityPage list(
            String accountId, String after, Long requestedUntil, int requestedPageSize) {
        String normalizedId = normalizeAccountId(accountId);
        AdAccountAsset asset = assetMapper.findByAccountId(normalizedId);
        if (asset == null) throw new AdAccountAssetException("广告账户资产不存在");
        if (asset.getCreatedAt() == null) throw new AdAccountAssetException("广告账户缺少入库时间");

        Document personalAccount = firstActivePersonalAccount(normalizedId);
        String accessToken =
                text(personalAccount == null ? null : personalAccount.get("access_token"));
        if (accessToken == null) {
            throw new AdAccountAssetException("未找到可访问该广告账户的有效个号 Token");
        }

        long since = epochSecond(asset.getCreatedAt(), asset.getTimezone());
        long until = requestedUntil == null ? Instant.now().getEpochSecond() : requestedUntil;
        if (until < since) throw new AdAccountAssetException("Facebook 操作记录时间范围不合法");
        int pageSize =
                requestedPageSize <= 0
                        ? DEFAULT_PAGE_SIZE
                        : Math.min(requestedPageSize, MAX_PAGE_SIZE);
        try {
            return client.list(accessToken, normalizedId, since, until, after, pageSize);
        } catch (FacebookActivityProviderException exception) {
            throw new AdAccountAssetException(exception.getMessage());
        }
    }

    private Document firstActivePersonalAccount(String accountId) {
        Query query =
                Query.query(
                        new Criteria()
                                .andOperator(
                                        Criteria.where("status").is(true),
                                        Criteria.where("access_token").regex("\\S"),
                                        Criteria.where("accounts.id")
                                                .in(List.of(accountId, "act_" + accountId))));
        return mongoTemplate.findOne(query, Document.class, personalAccountCollection);
    }

    private long epochSecond(LocalDateTime time, String timezone) {
        ZoneId zone = ZoneId.systemDefault();
        if (timezone != null && !timezone.isBlank()) {
            try {
                zone = ZoneId.of(timezone.trim());
            } catch (DateTimeException ignored) {
                // 历史台账可能保存非 IANA 时区，无法识别时沿用服务运行时区。
            }
        }
        return time.atZone(zone).toEpochSecond();
    }

    private String normalizeAccountId(String accountId) {
        String normalized = text(accountId);
        if (normalized == null) throw new AdAccountAssetException("广告账户 ID 不能为空");
        return normalized.replaceFirst("(?i)^act_", "");
    }

    private String text(Object value) {
        if (value == null) return null;
        String normalized = String.valueOf(value).trim();
        return normalized.isEmpty() ? null : normalized;
    }
}
