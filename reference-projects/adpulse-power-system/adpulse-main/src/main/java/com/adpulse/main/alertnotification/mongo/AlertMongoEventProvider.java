package com.adpulse.main.alertnotification.mongo;

import java.math.BigDecimal;
import java.time.Instant;
import java.time.LocalDateTime;
import java.time.ZoneId;
import java.util.Date;
import java.util.List;
import org.bson.Document;
import org.springframework.data.domain.Sort;
import org.springframework.data.mongodb.core.MongoTemplate;
import org.springframework.data.mongodb.core.query.Criteria;
import org.springframework.data.mongodb.core.query.Query;
import org.springframework.stereotype.Component;

/** 查询 Python 同步任务写入的不可变广告户变化事件。 */
@Component
public class AlertMongoEventProvider {
    private static final ZoneId BEIJING = ZoneId.of("Asia/Shanghai");
    private final MongoTemplate mongo;

    public AlertMongoEventProvider(MongoTemplate mongo) {
        this.mongo = mongo;
    }

    /** 查询指定时间段内的封户事件，开始时间包含、结束时间不包含。 */
    public List<BanEvent> banEventsBetween(Instant startInclusive, Instant endExclusive) {
        Query query =
                Query.query(
                                Criteria.where("detected_at")
                                        .gte(Date.from(startInclusive))
                                        .lt(Date.from(endExclusive)))
                        .with(Sort.by(Sort.Direction.ASC, "detected_at", "_id"));
        return mongo.find(query, Document.class, "fb_ad_account_ban_events").stream()
                .map(this::banEvent)
                .toList();
    }

    /** 查询限额变化窗口的一页事件；页内游标只用于本次扫描，不保存跨轮询进度。 */
    public List<ChangeEvent> limitEventsBetween(
            LocalDateTime startInclusive,
            LocalDateTime endExclusive,
            LocalDateTime pageDetectedAt,
            String pageEventId,
            int limit) {
        Criteria window =
                Criteria.where("detected_at")
                        .gte(Date.from(startInclusive.atZone(BEIJING).toInstant()))
                        .lt(Date.from(endExclusive.atZone(BEIJING).toInstant()));
        Criteria criteria = window;
        if (pageDetectedAt != null) {
            Date detectedAt = Date.from(pageDetectedAt.atZone(BEIJING).toInstant());
            Criteria nextPage =
                    new Criteria()
                            .orOperator(
                                    Criteria.where("detected_at").gt(detectedAt),
                                    new Criteria()
                                            .andOperator(
                                                    Criteria.where("detected_at").is(detectedAt),
                                                    Criteria.where("_id")
                                                            .gt(
                                                                    pageEventId == null
                                                                            ? ""
                                                                            : pageEventId)));
            criteria = new Criteria().andOperator(window, nextPage);
        }
        Query query = new Query(criteria).with(Sort.by(Sort.Direction.ASC, "detected_at", "_id"));
        query.limit(limit);
        return mongo.find(query, Document.class, "fb_ad_account_limit_events").stream()
                .map(this::limitEvent)
                .toList();
    }

    private ChangeEvent limitEvent(Document value) {
        return new ChangeEvent(
                String.valueOf(value.get("_id")),
                value.getString("account_id"),
                value.getString("account_name"),
                value.getString("currency"),
                decimal(value.get("previous_limit")),
                decimal(value.get("current_limit")),
                value.getString("change_type"),
                local(value.getDate("detected_at")));
    }

    private BanEvent banEvent(Document value) {
        return new BanEvent(
                String.valueOf(value.get("_id")),
                value.getString("account_id"),
                value.getString("account_name"),
                local(value.getDate("detected_at")));
    }

    private BigDecimal decimal(Object value) {
        return value == null ? null : new BigDecimal(value.toString());
    }

    private LocalDateTime local(Date value) {
        return LocalDateTime.ofInstant(value.toInstant(), BEIJING);
    }

    public record ChangeEvent(
            String id,
            String accountId,
            String accountName,
            String currency,
            BigDecimal previousValue,
            BigDecimal currentValue,
            String changeType,
            LocalDateTime detectedAt) {}

    public record BanEvent(
            String id, String accountId, String accountName, LocalDateTime detectedAt) {}
}
