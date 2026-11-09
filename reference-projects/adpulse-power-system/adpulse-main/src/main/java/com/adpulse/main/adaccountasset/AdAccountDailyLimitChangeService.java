package com.adpulse.main.adaccountasset;

import com.adpulse.main.adaccountasset.AdAccountAssetService.AdAccountAssetException;
import com.adpulse.main.adaccountasset.AdAccountAssetViews.DailyLimitChange;
import com.adpulse.main.adaccountasset.AdAccountAssetViews.DailyLimitChangePage;
import java.math.BigDecimal;
import java.time.LocalDateTime;
import java.time.ZoneId;
import java.util.ArrayList;
import java.util.Date;
import java.util.List;
import java.util.Locale;
import org.bson.Document;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.data.domain.Sort;
import org.springframework.data.mongodb.core.MongoTemplate;
import org.springframework.data.mongodb.core.query.Criteria;
import org.springframework.data.mongodb.core.query.Query;
import org.springframework.stereotype.Service;

/** 广告账户日限额变化记录查询服务。 */
@Service
public class AdAccountDailyLimitChangeService {
    private static final ZoneId BEIJING = ZoneId.of("Asia/Shanghai");
    private static final int DEFAULT_PAGE_SIZE = 20;
    private static final int MAX_PAGE_SIZE = 100;
    private static final String EVENT_COLLECTION = "fb_ad_account_limit_events";

    private final MongoTemplate mongoTemplate;
    private final String accountCollection;

    public AdAccountDailyLimitChangeService(
            MongoTemplate mongoTemplate,
            @Value("${adpulse.mongo.account.collection:fb_ad_accounts}") String accountCollection) {
        this.mongoTemplate = mongoTemplate;
        this.accountCollection = accountCollection;
    }

    /** 查询一个广告账户的日限额变化记录，按变化时间倒序分页。 */
    public DailyLimitChangePage list(String accountId, int requestedPage, int requestedPageSize) {
        String normalizedId = normalizeAccountId(accountId);
        int page = Math.max(requestedPage, 1);
        int pageSize =
                requestedPageSize <= 0
                        ? DEFAULT_PAGE_SIZE
                        : Math.min(requestedPageSize, MAX_PAGE_SIZE);

        Document account =
                mongoTemplate.findOne(
                        accountQuery(normalizedId), Document.class, accountCollection);
        Query eventQuery = Query.query(Criteria.where("account_id").is(normalizedId));
        long total = mongoTemplate.count(eventQuery, EVENT_COLLECTION);
        eventQuery
                .with(Sort.by(Sort.Order.desc("detected_at"), Sort.Order.desc("_id")))
                .skip((long) (page - 1) * pageSize)
                .limit(pageSize);
        List<Document> eventDocuments =
                mongoTemplate.find(eventQuery, Document.class, EVENT_COLLECTION);
        List<DailyLimitChange> items = eventDocuments.stream().map(this::event).toList();
        Document newestEvent = eventDocuments.isEmpty() ? null : eventDocuments.getFirst();

        return new DailyLimitChangePage(
                normalizedId,
                text(account, "name", "account_name", "accountName", newestEvent),
                text(account, "currency", newestEvent),
                decimal(account, "account_dsl"),
                localDateTime(account, "updated_at"),
                items,
                total,
                page,
                pageSize);
    }

    private DailyLimitChange event(Document value) {
        BigDecimal previousLimit = decimal(value, "previous_limit");
        BigDecimal currentLimit = decimal(value, "current_limit");
        return new DailyLimitChange(
                String.valueOf(value.get("_id")),
                previousLimit,
                currentLimit,
                changeType(value.getString("change_type"), previousLimit, currentLimit),
                localDateTime(value, "detected_at"),
                "FACEBOOK");
    }

    private String changeType(String value, BigDecimal previousLimit, BigDecimal currentLimit) {
        if (value != null) {
            String normalized = value.trim().toUpperCase(Locale.ROOT);
            if (List.of("SET", "INCREASE", "DECREASE", "CLEAR").contains(normalized)) {
                return normalized;
            }
        }
        if (currentLimit == null) return "CLEAR";
        if (previousLimit == null) return "SET";
        return currentLimit.compareTo(previousLimit) > 0 ? "INCREASE" : "DECREASE";
    }

    private Query accountQuery(String accountId) {
        List<Object> variants = new ArrayList<>();
        variants.add(accountId);
        try {
            variants.add(Long.parseLong(accountId));
        } catch (NumberFormatException ignored) {
            // MongoDB 历史账户主键同时存在字符串和 Long，非数字 ID 只按字符串查询。
        }
        return Query.query(Criteria.where("_id").in(variants));
    }

    private BigDecimal decimal(Document value, String name) {
        if (value == null || value.get(name) == null) return null;
        return new BigDecimal(value.get(name).toString());
    }

    private LocalDateTime localDateTime(Document value, String name) {
        if (value == null || !(value.get(name) instanceof Date date)) return null;
        return LocalDateTime.ofInstant(date.toInstant(), BEIJING);
    }

    private String text(Document primary, String name, Document fallback) {
        String value = text(primary == null ? null : primary.get(name));
        return value == null ? text(fallback == null ? null : fallback.get(name)) : value;
    }

    private String text(
            Document primary,
            String firstName,
            String secondName,
            String thirdName,
            Document fallback) {
        if (primary != null) {
            for (String name : List.of(firstName, secondName, thirdName)) {
                String value = text(primary.get(name));
                if (value != null) return value;
            }
        }
        return text(fallback == null ? null : fallback.get("account_name"));
    }

    private String text(Object value) {
        if (value == null) return null;
        String normalized = String.valueOf(value).trim();
        return normalized.isEmpty() ? null : normalized;
    }

    private String normalizeAccountId(String accountId) {
        String normalized = text(accountId);
        if (normalized == null) throw new AdAccountAssetException("账户ID不能为空");
        normalized = normalized.replaceFirst("(?i)^act_", "").trim();
        if (normalized.isEmpty()) throw new AdAccountAssetException("账户ID不能为空");
        return normalized;
    }
}
