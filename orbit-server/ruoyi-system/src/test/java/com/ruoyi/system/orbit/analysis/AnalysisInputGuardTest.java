package com.ruoyi.system.orbit.analysis;

import static org.junit.jupiter.api.Assertions.*;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.node.*;
import com.ruoyi.system.orbit.config.ConfigurationException;
import java.nio.file.*;
import java.util.*;
import org.junit.jupiter.api.Test;

/** 产品事实包Schema、严格限制合并与不可变输入回归；不调用任何外部平台。 */
class AnalysisInputGuardTest {
    private final ObjectMapper mapper = new ObjectMapper();
    private final AnalysisInputGuard guard = new AnalysisInputGuard(mapper);
    private static final String TENANT = "00000000-0000-0000-0000-000000000001";

    private ObjectNode input() {
        ObjectNode facts = mapper.createObjectNode();
        facts.put("schema_version", 1);
        for (String field : List.of("tenant_id", "snapshot_id", "entity_id", "metric_profile_id"))
            facts.put(field, TENANT);
        facts.put("entity_type", "AD");
        facts.put("policy_version", "policy-v1");
        facts.put("currency", "USD");
        ObjectNode metrics = mapper.createObjectNode();
        for (String field :
                List.of(
                        "spend",
                        "impressions",
                        "clicks",
                        "registrations",
                        "purchases",
                        "purchase_value",
                        "roas",
                        "cpm",
                        "ctr",
                        "cpc",
                        "cpa",
                        "usage")) metrics.put(field, "12.345600");
        facts.set("current", metrics);
        facts.set("previous", metrics.deepCopy());
        facts.putArray("daily_points");
        ObjectNode evidence = mapper.createObjectNode();
        evidence.put("id", "a".repeat(64));
        evidence.put("entity_id", TENANT);
        evidence.put("metric", "spend");
        evidence.put("date_from", "2026-11-01");
        evidence.put("date_to", "2026-11-02");
        evidence.put("value", "12.345600");
        evidence.put("unit", "USD");
        evidence.put("calculation_version", "metric-v1");
        facts.putArray("evidence").add(evidence);
        facts.put("budget_owner_id", TENANT);
        facts.put("budget_before", "100.500000");
        facts.put("coverage", "0.999999");
        facts.put("observed_at", "2026-11-07T00:00:00Z");
        facts.put("entity_age_hours", "24");
        facts.put("paused_hours", "72");
        facts.put("maturity_days", 28);
        facts.put("quality", "SUFFICIENT");
        return facts;
    }

    private AnalysisInputGuard.FrozenInput prepare(ObjectNode facts, Map<String, Object> policy) {
        return guard.prepare(facts, TENANT, policy, 2048, 120, 3);
    }

    @Test
    void freezesExactDecimalStringsAndUsesStricterLimits() throws Exception {
        ObjectNode facts = input();
        var frozen = prepare(facts, Map.of("maxOutputTokens", 4096));
        assertEquals(2048, frozen.maxOutputTokens());
        assertEquals(120, frozen.cooldownMinutes());
        assertEquals(3, frozen.maximumDailyAnalysesPerObject());
        assertEquals(64, frozen.sha256().length());
        assertEquals(
                "12.345600", mapper.readTree(frozen.json()).path("current").path("spend").asText());
        facts.put("policy_version", "changed-after-freeze");
        assertFalse(frozen.json().contains("changed-after-freeze"));
        assertEquals("FrozenInput[REDACTED]", frozen.toString());
        var tight =
                guard.prepare(
                        input(),
                        TENANT,
                        Map.of(
                                "minimumCooldownMinutes",
                                180,
                                "maximumDailyAnalysesPerObject",
                                2,
                                "maxOutputTokens",
                                1024),
                        4096,
                        60,
                        5);
        assertEquals(180, tight.cooldownMinutes());
        assertEquals(2, tight.maximumDailyAnalysesPerObject());
        assertEquals(1024, tight.maxOutputTokens());
    }

    @Test
    void rejectsUnknownOrMissingFieldsWithoutEchoingInput() {
        ObjectNode facts = input();
        facts.put("api_token", "fixture-private-not-to-echo");
        var error = assertThrows(ConfigurationException.class, () -> prepare(facts, Map.of()));
        assertEquals("ANALYSIS_INPUT_INVALID", error.code());
        assertFalse(error.getMessage().contains("fixture-private"));
        ObjectNode missing = input();
        missing.remove("snapshot_id");
        assertThrows(ConfigurationException.class, () -> prepare(missing, Map.of()));
    }

    @Test
    void rejectsMalformedFormatsAndDecimals() {
        for (String field : List.of("tenant_id", "observed_at")) {
            ObjectNode facts = input();
            facts.put(field, "not-a-valid-format");
            assertThrows(ConfigurationException.class, () -> prepare(facts, Map.of()));
        }
        ObjectNode facts = input();
        ((ObjectNode) facts.path("current")).put("spend", "12.1234567");
        assertThrows(ConfigurationException.class, () -> prepare(facts, Map.of()));
        ObjectNode day = mapper.createObjectNode().put("business_date", "2026-02-30");
        day.set("values", input().path("current"));
        ObjectNode invalidDate = input();
        ((ArrayNode) invalidDate.path("daily_points")).add(day);
        assertThrows(ConfigurationException.class, () -> prepare(invalidDate, Map.of()));
    }

    @Test
    void enforcesSchemaAndConfiguredArrayLimitsAndEvidenceUniqueness() {
        ObjectNode facts = input();
        ((ArrayNode) facts.path("evidence")).add(facts.path("evidence").get(0).deepCopy());
        assertThrows(ConfigurationException.class, () -> prepare(facts, Map.of()));
        ObjectNode points = input();
        for (int n = 0; n < 3; n++) {
            ObjectNode day =
                    mapper.createObjectNode()
                            .put(
                                    "business_date",
                                    java.time.LocalDate.of(2026, 11, 1).plusDays(n).toString());
            day.set("values", input().path("current"));
            ((ArrayNode) points.path("daily_points")).add(day);
        }
        assertThrows(
                ConfigurationException.class, () -> prepare(points, Map.of("maxDailyPoints", 2)));
        assertDoesNotThrow(() -> prepare(points, Map.of("maxDailyPoints", 3)));
        ((ArrayNode) points.path("daily_points"))
                .add(points.path("daily_points").get(0).deepCopy());
        assertThrows(ConfigurationException.class, () -> prepare(points, Map.of()));
    }

    @Test
    void rejectsForeignTenantAndInvalidRuleOrProviderLimits() {
        var error =
                assertThrows(
                        ConfigurationException.class,
                        () ->
                                guard.prepare(
                                        input(),
                                        "00000000-0000-0000-0000-000000000002",
                                        Map.of(),
                                        2048,
                                        60,
                                        5));
        assertEquals(403, error.status());
        assertThrows(
                ConfigurationException.class,
                () -> guard.prepare(input(), TENANT, Map.of(), 2048, -1, 5));
        assertThrows(
                ConfigurationException.class,
                () -> guard.prepare(input(), TENANT, Map.of(), 2048, 60, 0));
        assertThrows(
                ConfigurationException.class,
                () -> guard.prepare(input(), TENANT, Map.of(), 1, 60, 5));
    }

    @Test
    void runtimeSchemaOnlyRepairsOverescapedDecimalPattern() throws Exception {
        var original =
                mapper.readTree(
                        Path.of("../docs/orbit/baseline/contracts/analysis-input.schema.json")
                                .toFile());
        repair(original);
        try (var stream = getClass().getResourceAsStream("/orbit/analysis-input.schema.json")) {
            assertEquals(original, mapper.readTree(stream));
        }
    }

    private void repair(com.fasterxml.jackson.databind.JsonNode node) {
        if (node.isObject()) {
            if (node.has("pattern"))
                ((ObjectNode) node)
                        .put("pattern", node.path("pattern").asText().replace("\\\\.", "\\."));
            node.elements().forEachRemaining(this::repair);
        } else if (node.isArray()) node.elements().forEachRemaining(this::repair);
    }
}
