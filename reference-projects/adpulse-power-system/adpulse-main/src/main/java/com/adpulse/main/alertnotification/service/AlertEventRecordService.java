package com.adpulse.main.alertnotification.service;

import com.adpulse.main.alertnotification.dto.AlertRequests.EventRecordQuery;
import com.adpulse.main.alertnotification.dto.AlertRequests.LimitChangeRecordQuery;
import com.adpulse.main.alertnotification.dto.AlertViews.BanRecord;
import com.adpulse.main.alertnotification.dto.AlertViews.LimitChangeRecord;
import com.adpulse.main.alertnotification.dto.AlertViews.Page;
import java.math.BigDecimal;
import java.time.LocalDate;
import java.time.LocalDateTime;
import java.time.ZoneId;
import java.util.ArrayList;
import java.util.Date;
import java.util.List;
import java.util.Locale;
import java.util.Set;
import java.util.regex.Pattern;
import org.bson.Document;
import org.springframework.data.domain.Sort;
import org.springframework.data.mongodb.core.MongoTemplate;
import org.springframework.data.mongodb.core.query.Criteria;
import org.springframework.data.mongodb.core.query.Query;
import org.springframework.stereotype.Service;

/** 为预警通知页面提供只读的 Facebook 封户与限额变化事件分页查询。 */
@Service
public class AlertEventRecordService {
    private static final ZoneId BEIJING = ZoneId.of("Asia/Shanghai");
    private static final int DEFAULT_PAGE_SIZE = 20;
    private static final int MAX_PAGE_SIZE = 100;
    private static final String BAN_COLLECTION = "fb_ad_account_ban_events";
    private static final String LIMIT_COLLECTION = "fb_ad_account_limit_events";
    private static final Set<String> LIMIT_CHANGE_TYPES =
            Set.of("SET", "INCREASE", "DECREASE", "CLEAR");

    private final MongoTemplate mongo;

    public AlertEventRecordService(MongoTemplate mongo) {
        this.mongo = mongo;
    }

    /** 按事件时间倒序分页查询封户事件。 */
    public Page<BanRecord> listBanRecords(EventRecordQuery request) {
        PageRequest pageRequest = pageRequest(request.page(), request.pageSize());
        Query query = eventQuery(request.keyword(), request.startDate(), request.endDate());
        long total = mongo.count(query, BAN_COLLECTION);
        applyPage(query, pageRequest);
        List<BanRecord> items =
                mongo.find(query, Document.class, BAN_COLLECTION).stream()
                        .map(this::banRecord)
                        .toList();
        return new Page<>(items, total, pageRequest.page(), pageRequest.pageSize());
    }

    /** 按事件时间倒序分页查询账户日限额变化事件。 */
    public Page<LimitChangeRecord> listLimitChangeRecords(LimitChangeRecordQuery request) {
        PageRequest pageRequest = pageRequest(request.page(), request.pageSize());
        Query query = eventQuery(request.keyword(), request.startDate(), request.endDate());
        String changeType = normalizedChangeType(request.changeType());
        if (changeType != null) query.addCriteria(Criteria.where("change_type").is(changeType));
        long total = mongo.count(query, LIMIT_COLLECTION);
        applyPage(query, pageRequest);
        List<LimitChangeRecord> items =
                mongo.find(query, Document.class, LIMIT_COLLECTION).stream()
                        .map(this::limitChangeRecord)
                        .toList();
        return new Page<>(items, total, pageRequest.page(), pageRequest.pageSize());
    }

    private Query eventQuery(String keyword, LocalDate startDate, LocalDate endDate) {
        if (startDate != null && endDate != null && startDate.isAfter(endDate)) {
            throw new IllegalArgumentException("开始日期不能晚于结束日期");
        }
        List<Criteria> criteria = new ArrayList<>();
        if (startDate != null) {
            criteria.add(
                    Criteria.where("detected_at")
                            .gte(Date.from(startDate.atStartOfDay(BEIJING).toInstant())));
        }
        if (endDate != null) {
            criteria.add(
                    Criteria.where("detected_at")
                            .lt(Date.from(endDate.plusDays(1).atStartOfDay(BEIJING).toInstant())));
        }
        String normalizedKeyword = text(keyword);
        if (normalizedKeyword != null) {
            Pattern keywordPattern =
                    Pattern.compile(Pattern.quote(normalizedKeyword), Pattern.CASE_INSENSITIVE);
            criteria.add(
                    new Criteria()
                            .orOperator(
                                    Criteria.where("account_id").regex(keywordPattern),
                                    Criteria.where("account_name").regex(keywordPattern)));
        }
        return criteria.isEmpty()
                ? new Query()
                : Query.query(new Criteria().andOperator(criteria.toArray(Criteria[]::new)));
    }

    private void applyPage(Query query, PageRequest pageRequest) {
        query.with(Sort.by(Sort.Order.desc("detected_at"), Sort.Order.desc("_id")))
                .skip((long) (pageRequest.page() - 1) * pageRequest.pageSize())
                .limit(pageRequest.pageSize());
    }

    private BanRecord banRecord(Document value) {
        return new BanRecord(
                text(value.get("_id")),
                text(value.get("account_id")),
                text(value.get("account_name")),
                integer(value.get("previous_status")),
                integer(value.get("current_status")),
                text(value.get("disable_reason")),
                text(value.get("currency")),
                localDateTime(value.get("detected_at")),
                "FACEBOOK");
    }

    private LimitChangeRecord limitChangeRecord(Document value) {
        BigDecimal previousLimit = decimal(value.get("previous_limit"));
        BigDecimal currentLimit = decimal(value.get("current_limit"));
        return new LimitChangeRecord(
                text(value.get("_id")),
                text(value.get("account_id")),
                text(value.get("account_name")),
                previousLimit,
                currentLimit,
                text(value.get("currency")),
                eventChangeType(value.get("change_type"), previousLimit, currentLimit),
                localDateTime(value.get("detected_at")),
                "FACEBOOK");
    }

    private String normalizedChangeType(String value) {
        String normalized = text(value);
        if (normalized == null) return null;
        normalized = normalized.toUpperCase(Locale.ROOT);
        if (!LIMIT_CHANGE_TYPES.contains(normalized)) {
            throw new IllegalArgumentException("限额变化类型不受支持");
        }
        return normalized;
    }

    private String eventChangeType(
            Object value, BigDecimal previousLimit, BigDecimal currentLimit) {
        String normalized = text(value);
        if (normalized != null) {
            normalized = normalized.toUpperCase(Locale.ROOT);
            if (LIMIT_CHANGE_TYPES.contains(normalized)) return normalized;
        }
        if (currentLimit == null) return "CLEAR";
        if (previousLimit == null) return "SET";
        return currentLimit.compareTo(previousLimit) > 0 ? "INCREASE" : "DECREASE";
    }

    private PageRequest pageRequest(Integer requestedPage, Integer requestedPageSize) {
        int page = requestedPage == null || requestedPage < 1 ? 1 : requestedPage;
        int pageSize =
                requestedPageSize == null
                        ? DEFAULT_PAGE_SIZE
                        : Math.min(Math.max(requestedPageSize, 1), MAX_PAGE_SIZE);
        return new PageRequest(page, pageSize);
    }

    private BigDecimal decimal(Object value) {
        return value == null ? null : new BigDecimal(value.toString());
    }

    private Integer integer(Object value) {
        if (value == null) return null;
        try {
            return Integer.valueOf(value.toString());
        } catch (NumberFormatException ignored) {
            return null;
        }
    }

    private LocalDateTime localDateTime(Object value) {
        return value instanceof Date date
                ? LocalDateTime.ofInstant(date.toInstant(), BEIJING)
                : null;
    }

    private String text(Object value) {
        if (value == null) return null;
        String normalized = value.toString().trim();
        return normalized.isEmpty() ? null : normalized;
    }

    private record PageRequest(int page, int pageSize) {}
}
