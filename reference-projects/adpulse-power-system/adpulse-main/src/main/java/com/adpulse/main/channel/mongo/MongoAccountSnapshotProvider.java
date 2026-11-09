package com.adpulse.main.channel.mongo;

import com.adpulse.main.channel.service.AccountSnapshotProvider;
import java.math.BigDecimal;
import java.time.DateTimeException;
import java.time.Instant;
import java.time.LocalDateTime;
import java.time.ZoneId;
import java.time.ZoneOffset;
import java.time.format.DateTimeParseException;
import java.util.Date;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import org.bson.Document;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.data.mongodb.core.MongoTemplate;
import org.springframework.data.mongodb.core.query.Criteria;
import org.springframework.data.mongodb.core.query.Query;
import org.springframework.stereotype.Component;

/** 使用 MongoDB 的 fb_ad_account 集合补充账户列表展示字段。 */
@Component
public class MongoAccountSnapshotProvider implements AccountSnapshotProvider {
    private static final int QUERY_BATCH_SIZE = 500;
    private static final Logger LOGGER =
            LoggerFactory.getLogger(MongoAccountSnapshotProvider.class);

    private final MongoTemplate mongoTemplate;
    private final boolean enabled;
    private final String collection;

    public MongoAccountSnapshotProvider(
            MongoTemplate mongoTemplate,
            @Value("${adpulse.mongo.account.enabled:false}") boolean enabled,
            @Value("${adpulse.mongo.account.collection:fb_ad_accounts}") String collection) {
        this.mongoTemplate = mongoTemplate;
        this.enabled = enabled;
        this.collection = collection;
    }

    /** 批量查询当前页账户，MongoDB 异常时降级为不补充字段。 */
    @Override
    public Map<String, AccountSnapshot> findByAccountIds(List<String> accountIds) {
        if (!enabled || accountIds.isEmpty()) return Map.of();
        List<String> distinctAccountIds = accountIds.stream().distinct().toList();
        Map<String, AccountSnapshot> result = new LinkedHashMap<>();
        try {
            for (int start = 0; start < distinctAccountIds.size(); start += QUERY_BATCH_SIZE) {
                int end = Math.min(start + QUERY_BATCH_SIZE, distinctAccountIds.size());
                findBatch(distinctAccountIds.subList(start, end), result);
            }
            return result;
        } catch (RuntimeException exception) {
            LOGGER.warn("MongoDB账户信息查询失败，本次列表使用MySQL字段: {}", exception.getMessage());
            return Map.of();
        }
    }

    private void findBatch(List<String> accountIds, Map<String, AccountSnapshot> result) {
        Query query = new Query(Criteria.where("_id").in(accountIds));
        query.fields()
                .include("_id")
                .include("name")
                .include("account_status")
                .include("updated_at")
                .include("timezone_name")
                .include("owner")
                .include("balance")
                .include("amount_spent")
                .include("spend_cap")
                .include("end_advertiser");
        for (Document document : mongoTemplate.find(query, Document.class, collection)) {
            AccountSnapshot snapshot = toSnapshot(document);
            if (snapshot.accountId() != null) result.put(snapshot.accountId(), snapshot);
        }
    }

    private AccountSnapshot toSnapshot(Document value) {
        return new AccountSnapshot(
                text(value, "_id"),
                text(value, "name"),
                integer(value, "account_status"),
                dateTime(value, "updated_at"),
                timezone(value),
                identifier(value, "owner"),
                decimal(value, "balance"),
                decimal(value, "amount_spent"),
                remainingSpendCap(value),
                identifier(value, "end_advertiser"));
    }

    private Object first(Document value, String... names) {
        for (String name : names) {
            Object found = value.get(name);
            if (found != null) return found;
        }
        return null;
    }

    private String text(Document value, String... names) {
        Object found = first(value, names);
        return found == null ? null : found.toString();
    }

    private String identifier(Document value, String name) {
        Object found = value.get(name);
        if (found instanceof Document document) {
            return text(document, "id", "_id", "name");
        }
        if (found instanceof Map<?, ?> map) {
            for (String key : List.of("id", "_id", "name")) {
                Object nested = map.get(key);
                if (nested != null) return nested.toString();
            }
            return null;
        }
        return found == null ? null : found.toString();
    }

    private Integer integer(Document value, String... names) {
        Object found = first(value, names);
        if (found instanceof Number number) return number.intValue();
        try {
            return found == null ? null : Integer.valueOf(found.toString());
        } catch (NumberFormatException ignored) {
            return null;
        }
    }

    private BigDecimal decimal(Document value, String... names) {
        Object found = first(value, names);
        try {
            return found == null ? null : new BigDecimal(found.toString());
        } catch (NumberFormatException ignored) {
            return null;
        }
    }

    private LocalDateTime dateTime(Document value, String... names) {
        Object found = first(value, names);
        if (found instanceof Date date) {
            return LocalDateTime.ofInstant(date.toInstant(), ZoneId.systemDefault());
        }
        if (found instanceof Instant instant) {
            return LocalDateTime.ofInstant(instant, ZoneId.systemDefault());
        }
        if (found instanceof Number number) {
            long epoch = number.longValue();
            if (Math.abs(epoch) < 100_000_000_000L) epoch *= 1000;
            return LocalDateTime.ofInstant(Instant.ofEpochMilli(epoch), ZoneId.systemDefault());
        }
        if (found != null) {
            try {
                return LocalDateTime.ofInstant(
                        Instant.parse(found.toString()), ZoneId.systemDefault());
            } catch (DateTimeParseException ignored) {
                try {
                    return LocalDateTime.parse(found.toString());
                } catch (DateTimeParseException ignoredAgain) {
                    return null;
                }
            }
        }
        return null;
    }

    private BigDecimal remainingSpendCap(Document value) {
        BigDecimal spendCap = decimal(value, "spend_cap");
        BigDecimal amountSpent = decimal(value, "amount_spent");
        if (spendCap == null) return null;
        return amountSpent == null ? spendCap : spendCap.subtract(amountSpent).max(BigDecimal.ZERO);
    }

    private Integer timezone(Document value) {
        String timezone = text(value, "timezone_name");
        if (timezone == null) return null;
        try {
            return Integer.valueOf(timezone.replace("UTC", "").replace("+", "").trim());
        } catch (NumberFormatException ignored) {
            try {
                ZoneOffset offset = ZoneId.of(timezone).getRules().getOffset(Instant.now());
                return offset.getTotalSeconds() / 3600;
            } catch (DateTimeException ignoredAgain) {
                return null;
            }
        }
    }
}
