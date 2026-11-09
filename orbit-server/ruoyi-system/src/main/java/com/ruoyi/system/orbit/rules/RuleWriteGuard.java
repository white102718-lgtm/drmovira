package com.ruoyi.system.orbit.rules;

import com.fasterxml.jackson.core.type.TypeReference;
import com.fasterxml.jackson.databind.*;
import com.fasterxml.jackson.databind.node.ObjectNode;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.text.Normalizer;
import java.util.*;
import org.springframework.stereotype.Component;

/** 完整RuleWrite结构校验及不可变版本正文；UUID格式通过不代表引用已存在或已获授权。 */
@Component
public final class RuleWriteGuard {
    private static final Set<String> FIELDS =
            Set.of(
                    "name",
                    "ownership",
                    "target_level",
                    "scope_snapshot_id",
                    "logic",
                    "groups",
                    "window",
                    "metric_profile_id",
                    "schedule",
                    "cooldown_minutes",
                    "max_daily");
    private final ObjectMapper json;
    private final RuleSchedule schedules;
    private final RuleConditions conditions;

    public RuleWriteGuard(ObjectMapper json, RuleSchedule schedules, RuleConditions conditions) {
        this.json = json.copy().enable(SerializationFeature.ORDER_MAP_ENTRIES_BY_KEYS);
        this.schedules = schedules;
        this.conditions = conditions;
    }

    public record Frozen(String body, String hash) {
        @Override
        public String toString() {
            return "RuleWrite[REDACTED]";
        }
    }

    public Frozen prepare(JsonNode input) {
        exact(input, FIELDS);
        ObjectNode copy = input.deepCopy();
        copy.put("name", normalize(text(copy.get("name")), 80));
        exact(copy.get("ownership"), Set.of("owner_user_id", "owner_team_id"));
        for (String field : List.of("owner_user_id", "owner_team_id"))
            ((ObjectNode) copy.get("ownership"))
                    .put(field, uuid(text(copy.get("ownership").get(field))));
        for (String field : List.of("scope_snapshot_id", "metric_profile_id"))
            copy.put(field, uuid(text(copy.get(field))));
        if (!Set.of("CAMPAIGN", "ADSET", "AD").contains(text(copy.get("target_level")))
                || !Set.of("TODAY", "YESTERDAY", "LAST_3D", "LAST_7D")
                        .contains(text(copy.get("window")))) throw invalid();
        integer(copy.get("cooldown_minutes"), 0, 10080);
        integer(copy.get("max_daily"), 1, 1000);
        ObjectNode expression = json.createObjectNode();
        expression.set("logic", copy.get("logic"));
        expression.set("groups", copy.get("groups"));
        conditions.parse(expression);
        schedules.parse(copy.get("schedule"));
        try {
            Map<String, Object> tree =
                    json.convertValue(copy, new TypeReference<Map<String, Object>>() {});
            String body = json.writeValueAsString(tree);
            return new Frozen(
                    body,
                    HexFormat.of()
                            .formatHex(
                                    MessageDigest.getInstance("SHA-256")
                                            .digest(body.getBytes(StandardCharsets.UTF_8))));
        } catch (Exception error) {
            throw invalid();
        }
    }

    static String uuid(String value) {
        try {
            String normalized = UUID.fromString(value).toString();
            if (!normalized.equalsIgnoreCase(value)) throw invalid();
            return normalized;
        } catch (Exception error) {
            throw invalid();
        }
    }

    static String normalize(String value, int maximum) {
        if (value == null) throw invalid();
        String normalized = Normalizer.normalize(value, Normalizer.Form.NFC).strip();
        if (normalized.isEmpty()
                || normalized.codePointCount(0, normalized.length()) > maximum
                || normalized.codePoints().anyMatch(Character::isISOControl)) throw invalid();
        return normalized;
    }

    private void integer(JsonNode value, int minimum, int maximum) {
        if (value == null
                || !value.isIntegralNumber()
                || !value.canConvertToInt()
                || value.intValue() < minimum
                || value.intValue() > maximum) throw invalid();
    }

    private static String text(JsonNode value) {
        if (value == null || !value.isTextual()) throw invalid();
        return value.textValue();
    }

    private static void exact(JsonNode value, Set<String> fields) {
        if (value == null || !value.isObject() || value.size() != fields.size()) throw invalid();
        value.fieldNames()
                .forEachRemaining(
                        field -> {
                            if (!fields.contains(field)) throw invalid();
                        });
    }

    private static IllegalArgumentException invalid() {
        return new IllegalArgumentException("规则字段、所有权格式或引用格式无效");
    }
}
