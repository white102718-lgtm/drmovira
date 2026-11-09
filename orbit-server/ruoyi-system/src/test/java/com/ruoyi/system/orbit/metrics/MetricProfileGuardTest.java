package com.ruoyi.system.orbit.metrics;

import static org.junit.jupiter.api.Assertions.*;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.node.ObjectNode;
import java.nio.file.*;
import java.util.*;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.params.ParameterizedTest;
import org.junit.jupiter.params.provider.ValueSource;

/** 指标口径完整字段和不可变定义校验；fixture事件不代表真实Meta验证。 */
public class MetricProfileGuardTest {
    private final ObjectMapper json = new ObjectMapper();
    private final MetricProfileGuard guard = new MetricProfileGuard(json);

    public static ObjectNode definition(ObjectMapper json) {
        ObjectNode body =
                json.createObjectNode()
                        .put("version", "v1")
                        .put("source", "META")
                        .putNull("register_action_type")
                        .putNull("purchase_action_type")
                        .putNull("value_action_type")
                        .put("action_report_time", "conversion")
                        .put("timezone_policy", "ACCOUNT_LOCAL")
                        .put("breakdown", "TOTAL")
                        .put("maturity_days", 28);
        body.putArray("attribution_windows").add("7d_click").add("1d_view");
        return body;
    }

    @ParameterizedTest
    @ValueSource(
            strings = {
                "version",
                "source",
                "register_action_type",
                "purchase_action_type",
                "value_action_type",
                "attribution_windows",
                "action_report_time",
                "timezone_policy",
                "breakdown",
                "maturity_days"
            })
    void requiresEveryDefinitionField(String field) {
        ObjectNode body = definition(json);
        body.remove(field);
        assertThrows(IllegalArgumentException.class, () -> guard.prepare(body));
    }

    @ParameterizedTest
    @ValueSource(strings = {"verified", "id", "tenant_id", "actor_id"})
    void cannotInjectReadOnlyOrServerFields(String field) {
        assertThrows(
                IllegalArgumentException.class,
                () -> guard.prepare(definition(json).put(field, true)));
    }

    @ParameterizedTest
    @ValueSource(ints = {0, 91, -1})
    void rejectsMaturityOutsideContract(int days) {
        assertThrows(
                IllegalArgumentException.class,
                () -> guard.prepare(definition(json).put("maturity_days", days)));
    }

    @Test
    void maturityBoundariesAndTypesAreStrict() {
        assertNotNull(guard.prepare(definition(json).put("maturity_days", 1)));
        assertNotNull(guard.prepare(definition(json).put("maturity_days", 90)));
        for (ObjectNode bad :
                List.of(
                        definition(json).put("maturity_days", "28"),
                        definition(json).put("maturity_days", 28.0),
                        definition(json).putNull("maturity_days")))
            assertThrows(IllegalArgumentException.class, () -> guard.prepare(bad));
    }

    @ParameterizedTest
    @ValueSource(strings = {"register_action_type", "purchase_action_type", "value_action_type"})
    void mappingCanBeUnknownButNotEmptyOrCoerced(String field) throws Exception {
        assertTrue(json.readTree(guard.prepare(definition(json)).json()).get(field).isNull());
        assertEquals(
                "fixture_event",
                json.readTree(guard.prepare(definition(json).put(field, "fixture_event")).json())
                        .get(field)
                        .asText());
        for (ObjectNode bad :
                List.of(
                        definition(json).put(field, " "),
                        definition(json).put(field, "a".repeat(65)),
                        definition(json).put(field, 1)))
            assertThrows(IllegalArgumentException.class, () -> guard.prepare(bad));
    }

    @Test
    void windowsAreBoundedDistinctAndCanonicalizedAsSet() throws Exception {
        ObjectNode first = definition(json), second = definition(json);
        second.putArray("attribution_windows").add("1d_view").add("7d_click");
        assertEquals(guard.prepare(first), guard.prepare(second));
        for (int count : List.of(0, 11)) {
            ObjectNode bad = definition(json);
            var windows = bad.putArray("attribution_windows");
            for (int i = 0; i < count; i++) windows.add("fixture_" + i);
            assertThrows(IllegalArgumentException.class, () -> guard.prepare(bad));
        }
        ObjectNode duplicate = definition(json);
        duplicate.putArray("attribution_windows").add("7d_click").add(" 7d_click ");
        assertThrows(IllegalArgumentException.class, () -> guard.prepare(duplicate));
        ObjectNode bad = definition(json);
        bad.putArray("attribution_windows").add(7);
        assertThrows(IllegalArgumentException.class, () -> guard.prepare(bad));
        ObjectNode maximum = definition(json);
        var windows = maximum.putArray("attribution_windows");
        for (int i = 0; i < 10; i++) windows.add("fixture_" + i);
        assertNotNull(guard.prepare(maximum));
    }

    @Test
    void validatesEnumsVersionReportTimeAndControlCharacters() {
        assertNotNull(guard.prepare(definition(json).put("source", "FIXTURE")));
        for (ObjectNode bad :
                List.of(
                        definition(json).put("source", "UNKNOWN"),
                        definition(json).put("timezone_policy", "UTC"),
                        definition(json).put("breakdown", "AGE"),
                        definition(json).put("version", ""),
                        definition(json).put("version", "a".repeat(65)),
                        definition(json).put("action_report_time", "x\ny"),
                        definition(json).putNull("action_report_time")))
            assertThrows(IllegalArgumentException.class, () -> guard.prepare(bad));
        assertNotNull(guard.prepare(definition(json).put("version", "a".repeat(64))));
    }

    @Test
    void frozenHashAndJsonRemainStableAfterSourceMutation() {
        ObjectNode source = definition(json);
        var frozen = guard.prepare(source);
        source.put("maturity_days", 90);
        assertNotEquals(frozen.sha256(), guard.prepare(source).sha256());
        assertEquals("MetricProfile[REDACTED]", frozen.toString());
        ObjectNode reordered = json.createObjectNode();
        List<String> fields = new ArrayList<>();
        definition(json).fieldNames().forEachRemaining(fields::add);
        Collections.reverse(fields);
        for (String field : fields) reordered.set(field, definition(json).get(field));
        assertEquals(frozen, guard.prepare(reordered));
    }

    @Test
    void definitionCoversProductProfileExceptServerIdAndVerified() throws Exception {
        var schema =
                json.readTree(
                                Files.readString(
                                        Path.of(
                                                "../docs/orbit/baseline/contracts/openapi-current.json")))
                        .path("components")
                        .path("schemas")
                        .path("MetricProfile");
        Set<String> expected = new HashSet<>(), actual = new HashSet<>();
        schema.path("properties").fieldNames().forEachRemaining(expected::add);
        expected.removeAll(Set.of("id", "verified"));
        definition(json).fieldNames().forEachRemaining(actual::add);
        assertEquals(expected, actual);
    }

    @Test
    void normalizedPolicyFieldsAreStoredAsCanonicalContractEnums() throws Exception {
        var body =
                json.readTree(
                        guard.prepare(
                                        definition(json)
                                                .put("timezone_policy", " ACCOUNT_LOCAL ")
                                                .put("breakdown", " TOTAL "))
                                .json());
        assertEquals("ACCOUNT_LOCAL", body.path("timezone_policy").asText());
        assertEquals("TOTAL", body.path("breakdown").asText());
    }
}
