package com.ruoyi.system.orbit.scope;

import com.fasterxml.jackson.core.type.TypeReference;
import com.fasterxml.jackson.databind.*;
import java.text.Normalizer;
import java.util.*;
import org.springframework.stereotype.Component;

/** 范围请求只携带选择条件，成员名称、外部ID及归属必须从服务端目录读取。 */
@Component
public final class ScopeRequestGuard {
    public record Selection(
            String mode,
            List<String> accountIds,
            String q,
            String escapedQ,
            String status,
            String authStatus,
            String operator,
            String vendor,
            String canonical) {
        public Selection {
            accountIds = List.copyOf(accountIds);
        }

        @Override
        public String toString() {
            return "ScopeSelection[REDACTED]";
        }
    }

    private final ObjectMapper json;

    public ScopeRequestGuard(ObjectMapper json) {
        this.json = json.copy().enable(SerializationFeature.ORDER_MAP_ENTRIES_BY_KEYS);
    }

    public Selection prepare(JsonNode input) {
        exact(input, Set.of("mode", "account_ids", "filter"));
        String mode = text(input.get("mode"));
        if (!Set.of("IDS", "FILTER").contains(mode)) throw invalid();
        JsonNode ids = input.get("account_ids"), filter = input.get("filter");
        if (!ids.isArray() || ids.size() > 50000) throw invalid();
        TreeSet<String> normalized = new TreeSet<>();
        for (JsonNode id : ids) normalized.add(uuid(text(id)));
        String q = "", status = null, auth = null, operator = null, vendor = null;
        if (mode.equals("IDS")) {
            if (normalized.isEmpty() || !filter.isNull()) throw invalid();
        } else {
            if (!normalized.isEmpty()) throw invalid();
            exact(filter, Set.of("q", "status", "auth_status", "operator_user_id", "vendor_id"));
            q = Normalizer.normalize(text(filter.get("q")), Normalizer.Form.NFC).strip();
            if (q.codePointCount(0, q.length()) > 100
                    || q.codePoints().anyMatch(Character::isISOControl)) throw invalid();
            status = nullableText(filter.get("status"));
            auth = nullableText(filter.get("auth_status"));
            if (status != null && !Set.of("ACTIVE", "DISABLED", "UNKNOWN").contains(status))
                throw invalid();
            if (auth != null
                    && !Set.of("AUTHORIZED", "EXPIRED", "REVOKED", "UNKNOWN").contains(auth))
                throw invalid();
            operator = nullableText(filter.get("operator_user_id"));
            vendor = nullableText(filter.get("vendor_id"));
            if (operator != null) operator = uuid(operator);
            if (vendor != null) vendor = uuid(vendor);
        }
        try {
            Map<String, Object> canonical =
                    json.convertValue(input, new TypeReference<Map<String, Object>>() {});
            canonical.put("account_ids", new ArrayList<>(normalized));
            if (mode.equals("FILTER")) {
                Map<String, Object> f = new TreeMap<>();
                f.put("q", q);
                f.put("status", status);
                f.put("auth_status", auth);
                f.put("operator_user_id", operator);
                f.put("vendor_id", vendor);
                canonical.put("filter", f);
            }
            return new Selection(
                    mode,
                    new ArrayList<>(normalized),
                    q,
                    q.replace("!", "!!").replace("%", "!%").replace("_", "!_"),
                    status,
                    auth,
                    operator,
                    vendor,
                    json.writeValueAsString(canonical));
        } catch (Exception error) {
            throw invalid();
        }
    }

    public static String uuid(String value) {
        try {
            String normalized = UUID.fromString(value).toString();
            if (!normalized.equalsIgnoreCase(value)) throw invalid();
            return normalized;
        } catch (Exception error) {
            throw invalid();
        }
    }

    private String nullableText(JsonNode value) {
        if (value == null) throw invalid();
        return value.isNull() ? null : text(value);
    }

    private String text(JsonNode value) {
        if (value == null || !value.isTextual()) throw invalid();
        return value.textValue();
    }

    private void exact(JsonNode value, Set<String> fields) {
        if (value == null || !value.isObject() || value.size() != fields.size()) throw invalid();
        value.fieldNames()
                .forEachRemaining(
                        field -> {
                            if (!fields.contains(field)) throw invalid();
                        });
    }

    private static IllegalArgumentException invalid() {
        return new IllegalArgumentException("账户范围模式、字段、筛选或ID数量无效");
    }
}
