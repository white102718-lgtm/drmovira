package com.ruoyi.system.orbit.metrics;

import com.fasterxml.jackson.core.type.TypeReference;
import com.fasterxml.jackson.databind.*;
import com.fasterxml.jackson.databind.node.ObjectNode;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.text.Normalizer;
import java.util.*;
import org.springframework.stereotype.Component;

/** 指标口径定义校验；不接受调用方声明verified，格式合法不代表真实平台事件映射已验证。 */
@Component
public final class MetricProfileGuard {
    private static final Set<String> FIELDS =
            Set.of(
                    "version",
                    "source",
                    "register_action_type",
                    "purchase_action_type",
                    "value_action_type",
                    "attribution_windows",
                    "action_report_time",
                    "timezone_policy",
                    "breakdown",
                    "maturity_days");
    private final ObjectMapper json;

    public MetricProfileGuard(ObjectMapper json) {
        this.json = json.copy().enable(SerializationFeature.ORDER_MAP_ENTRIES_BY_KEYS);
    }

    public record Frozen(String json, String sha256, String version, String source) {
        @Override
        public String toString() {
            return "MetricProfile[REDACTED]";
        }
    }

    public Frozen prepare(JsonNode input) {
        if (input == null || !input.isObject() || input.size() != FIELDS.size()) throw invalid();
        input.fieldNames()
                .forEachRemaining(
                        field -> {
                            if (!FIELDS.contains(field)) throw invalid();
                        });
        ObjectNode copy = input.deepCopy();
        String version = text(copy.get("version"), 64), source = text(copy.get("source"), 64);
        if (!Set.of("META", "FIXTURE").contains(source)) throw invalid();
        copy.put("version", version);
        copy.put("source", source);
        for (String field :
                List.of("register_action_type", "purchase_action_type", "value_action_type")) {
            JsonNode value = copy.get(field);
            if (value == null) throw invalid();
            if (!value.isNull()) copy.put(field, text(value, 64));
        }
        JsonNode windows = copy.get("attribution_windows");
        if (windows == null || !windows.isArray() || windows.isEmpty() || windows.size() > 10)
            throw invalid();
        TreeSet<String> normalized = new TreeSet<>();
        for (JsonNode window : windows) if (!normalized.add(text(window, 64))) throw invalid();
        var list = copy.putArray("attribution_windows");
        normalized.forEach(list::add);
        copy.put("action_report_time", text(copy.get("action_report_time"), 64));
        if (!"ACCOUNT_LOCAL".equals(text(copy.get("timezone_policy"), 64))
                || !"TOTAL".equals(text(copy.get("breakdown"), 64))) throw invalid();
        copy.put("timezone_policy", "ACCOUNT_LOCAL");
        copy.put("breakdown", "TOTAL");
        JsonNode days = copy.get("maturity_days");
        if (days == null
                || !days.isIntegralNumber()
                || !days.canConvertToInt()
                || days.intValue() < 1
                || days.intValue() > 90) throw invalid();
        try {
            String frozen =
                    json.writeValueAsString(
                            json.convertValue(copy, new TypeReference<Map<String, Object>>() {}));
            return new Frozen(
                    frozen,
                    HexFormat.of()
                            .formatHex(
                                    MessageDigest.getInstance("SHA-256")
                                            .digest(frozen.getBytes(StandardCharsets.UTF_8))),
                    version,
                    source);
        } catch (Exception error) {
            throw invalid();
        }
    }

    private String text(JsonNode value, int maximum) {
        if (value == null || !value.isTextual()) throw invalid();
        String normalized = Normalizer.normalize(value.textValue(), Normalizer.Form.NFC).strip();
        if (normalized.isEmpty()
                || normalized.codePointCount(0, normalized.length()) > maximum
                || normalized.codePoints().anyMatch(Character::isISOControl)) throw invalid();
        return normalized;
    }

    private IllegalArgumentException invalid() {
        return new IllegalArgumentException("指标口径字段、映射、归因窗口或成熟期无效");
    }
}
