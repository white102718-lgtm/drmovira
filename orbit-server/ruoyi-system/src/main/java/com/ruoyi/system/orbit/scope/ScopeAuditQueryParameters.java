package com.ruoyi.system.orbit.scope;

import java.text.Normalizer;
import java.time.*;
import java.util.*;

/** 审计合同查询参数边界；仅解析请求，不授予身份、目标租户或数据权限。 */
public final class ScopeAuditQueryParameters {
    private ScopeAuditQueryParameters() {}

    private static final Set<String> KNOWN =
            Set.of(
                    "q",
                    "cursor",
                    "page_size",
                    "status",
                    "date_from",
                    "date_to",
                    "operator_user_id",
                    "channel_id",
                    "metric_profile_id",
                    "entity_type");
    private static final Set<String> UNSUPPORTED =
            Set.of("status", "channel_id", "metric_profile_id", "entity_type");

    public record Input(ScopeFreezeAuditQuery.Filter filter, int size, String cursor) {
        @Override
        public String toString() {
            return "AuditQueryInput[REDACTED]";
        }
    }

    /** Servlet MultiValueMap可直接按此只读Map接口传入；重复参数不能采用first-value悄悄丢弃。 */
    public static Input parse(Map<String, List<String>> query) {
        if (query == null) throw malformed();
        for (var field : query.entrySet()) {
            if (field.getKey() == null) throw malformed();
            if (!KNOWN.contains(field.getKey()))
                throw new AccountScopeService.Failure(400, "UNKNOWN_FIELD", "审计查询包含未知参数");
            if (field.getValue() == null
                    || field.getValue().size() != 1
                    || field.getValue().getFirst() == null) throw malformed();
        }
        for (String field : UNSUPPORTED)
            if (query.containsKey(field))
                throw new AccountScopeService.Failure(422, "UNSUPPORTED_FILTER", "当前审计查询不支持该筛选");
        int size = 50;
        String rawSize = value(query, "page_size"), cursor = value(query, "cursor");
        if (rawSize != null) {
            if (!Set.of("20", "50", "100", "200").contains(rawSize)) throw invalid();
            size = Integer.parseInt(rawSize);
        }
        if (cursor != null && (cursor.isEmpty() || cursor.length() > 2048)) throw invalid();
        var filter =
                normalize(
                        new ScopeFreezeAuditQuery.Filter(
                                value(query, "q"),
                                value(query, "operator_user_id"),
                                value(query, "date_from"),
                                value(query, "date_to")));
        return new Input(filter, size, cursor);
    }

    /** 公开参数与内部扫描复用同一字段规则；拒绝控制符、无效日期和伪造UUID后才查询数据库。 */
    static ScopeFreezeAuditQuery.Filter normalize(ScopeFreezeAuditQuery.Filter filter) {
        if (filter == null) filter = new ScopeFreezeAuditQuery.Filter(null, null, null, null);
        String raw = filter.q() == null ? "" : filter.q();
        if (raw.codePoints().anyMatch(Character::isISOControl)) throw invalid();
        String q = Normalizer.normalize(raw, Normalizer.Form.NFC).strip();
        if (q.codePointCount(0, q.length()) > 100) throw invalid();
        try {
            String operator =
                    filter.operator() == null ? null : ScopeRequestGuard.uuid(filter.operator());
            LocalDate from = date(filter.dateFrom()), to = date(filter.dateTo());
            if (from != null && to != null && from.isAfter(to)) throw invalid();
            return new ScopeFreezeAuditQuery.Filter(
                    q,
                    operator,
                    from == null ? null : from.toString(),
                    to == null ? null : to.toString());
        } catch (Exception error) {
            throw invalid();
        }
    }

    private static LocalDate date(String value) {
        if (value == null) return null;
        LocalDate parsed = LocalDate.parse(value);
        if (parsed.getYear() < 1000
                || !parsed.toString().equals(value)
                || parsed.isAfter(LocalDate.now(ZoneOffset.UTC))) throw invalid();
        return parsed;
    }

    private static String value(Map<String, List<String>> query, String field) {
        return query.containsKey(field) ? query.get(field).getFirst() : null;
    }

    private static AccountScopeService.Failure malformed() {
        return new AccountScopeService.Failure(400, "INVALID_REQUEST", "审计查询参数值缺失或重复");
    }

    private static AccountScopeService.Failure invalid() {
        return new AccountScopeService.Failure(
                422, "BUSINESS_VALIDATION_FAILED", "审计查询字段、UTC日期、页大小或游标长度无效");
    }
}
