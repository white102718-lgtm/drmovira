package com.ruoyi.system.orbit.rules;

import static org.junit.jupiter.api.Assertions.*;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.node.ObjectNode;
import java.nio.file.*;
import java.util.*;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.params.ParameterizedTest;
import org.junit.jupiter.params.provider.ValueSource;

/** 完整RuleWrite结构测试；不把UUID格式校验当作引用授权或存在校验。 */
public class RuleWriteGuardTest {
    private final ObjectMapper json = new ObjectMapper();
    private final RuleWriteGuard guard =
            new RuleWriteGuard(json, new RuleSchedule(), new RuleConditions());

    public static ObjectNode request(ObjectMapper json) {
        String id = "00000000-0000-0000-0000-000000000001";
        ObjectNode root =
                json.createObjectNode()
                        .put("name", "测试规则")
                        .put("target_level", "AD")
                        .put("scope_snapshot_id", id)
                        .put("logic", "AND")
                        .put("window", "TODAY")
                        .put("metric_profile_id", id)
                        .put("cooldown_minutes", 60)
                        .put("max_daily", 5);
        root.putObject("ownership").put("owner_user_id", id).put("owner_team_id", id);
        root.putArray("groups")
                .addObject()
                .put("logic", "AND")
                .putArray("conditions")
                .addObject()
                .put("metric", "spend")
                .put("operator", "GT")
                .put("threshold", "1");
        root.putObject("schedule")
                .put("frequency", "DAILY")
                .putNull("interval_minutes")
                .put("time_of_day", "09:00")
                .putNull("weekday")
                .put("timezone", "Asia/Shanghai")
                .put("start_date", "2026-11-01")
                .put("end_date", "2026-11-30");
        return root;
    }

    @ParameterizedTest
    @ValueSource(
            strings = {
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
                "max_daily"
            })
    void allContractFieldsAreRequired(String field) {
        ObjectNode body = request(json);
        body.remove(field);
        assertThrows(IllegalArgumentException.class, () -> guard.prepare(body));
    }

    @ParameterizedTest
    @ValueSource(
            strings = {
                "tenant_id",
                "actor_id",
                "state",
                "revision",
                "action",
                "current_simulation_id"
            })
    void cannotInjectServerFields(String field) {
        assertThrows(
                IllegalArgumentException.class,
                () -> guard.prepare(request(json).put(field, "injected")));
    }

    @Test
    void namesUseCodePointsNfcAndRejectEmptyControlsOrOverflow() throws Exception {
        ObjectNode source = request(json).put("name", "  e\u0301 ");
        var frozen = guard.prepare(source);
        assertEquals("é", json.readTree(frozen.body()).path("name").asText());
        assertNotNull(guard.prepare(request(json).put("name", "😀".repeat(80))));
        for (String name : List.of(" ", "a\nb", "😀".repeat(81)))
            assertThrows(
                    IllegalArgumentException.class,
                    () -> guard.prepare(request(json).put("name", name)));
        source.put("name", "changed");
        assertEquals("é", json.readTree(frozen.body()).path("name").asText());
        assertEquals("RuleWrite[REDACTED]", frozen.toString());
    }

    @Test
    void canonicalBodyAndHashAreIndependentOfPropertyOrder() throws Exception {
        ObjectNode first = request(json), reverse = json.createObjectNode();
        List<String> fields = new ArrayList<>();
        first.fieldNames().forEachRemaining(fields::add);
        Collections.reverse(fields);
        for (String field : fields) reverse.set(field, first.get(field));
        assertEquals(guard.prepare(first), guard.prepare(reverse));
        assertNotEquals(
                guard.prepare(first).hash(), guard.prepare(first.put("max_daily", 6)).hash());
    }

    @Test
    void ownershipRequiresTwoStrictUuidsAndNoExtraFields() {
        for (String field : List.of("owner_user_id", "owner_team_id")) {
            ObjectNode bad = request(json);
            ((ObjectNode) bad.get("ownership")).put(field, "1-1-1-1-1");
            assertThrows(IllegalArgumentException.class, () -> guard.prepare(bad));
        }
        ObjectNode bad = request(json);
        ((ObjectNode) bad.get("ownership")).put("data_role", "SUPER_ADMIN");
        assertThrows(IllegalArgumentException.class, () -> guard.prepare(bad));
        assertThrows(
                IllegalArgumentException.class,
                () -> guard.prepare(request(json).put("scope_snapshot_id", "not-a-scope")));
        assertThrows(
                IllegalArgumentException.class,
                () -> guard.prepare(request(json).putNull("metric_profile_id")));
    }

    @Test
    void numericBoundariesAndTypesDoNotCoerce() {
        assertNotNull(guard.prepare(request(json).put("cooldown_minutes", 0).put("max_daily", 1)));
        assertNotNull(
                guard.prepare(request(json).put("cooldown_minutes", 10080).put("max_daily", 1000)));
        for (ObjectNode bad :
                List.of(
                        request(json).put("cooldown_minutes", -1),
                        request(json).put("cooldown_minutes", 10081),
                        request(json).put("cooldown_minutes", "60"),
                        request(json).put("cooldown_minutes", 60.0),
                        request(json).put("max_daily", 0),
                        request(json).put("max_daily", 1001),
                        request(json).put("max_daily", Long.MAX_VALUE),
                        request(json).putNull("max_daily")))
            assertThrows(IllegalArgumentException.class, () -> guard.prepare(bad));
    }

    @Test
    void acceptsAllTargetAndWindowEnumsButRejectsUnknown() {
        for (String target : List.of("CAMPAIGN", "ADSET", "AD"))
            for (String window : List.of("TODAY", "YESTERDAY", "LAST_3D", "LAST_7D"))
                assertNotNull(
                        guard.prepare(
                                request(json).put("target_level", target).put("window", window)));
        assertThrows(
                IllegalArgumentException.class,
                () -> guard.prepare(request(json).put("target_level", "ACCOUNT")));
        assertThrows(
                IllegalArgumentException.class,
                () -> guard.prepare(request(json).put("window", "LAST_30D")));
    }

    @Test
    void fullRequestCannotBypassSharedConditionsOrSchedule() {
        ObjectNode bad = request(json);
        ((ObjectNode) bad.get("groups").get(0).get("conditions").get(0)).put("metric", "script");
        assertThrows(IllegalArgumentException.class, () -> guard.prepare(bad));
        ObjectNode incompatible = request(json);
        ((ObjectNode) incompatible.get("schedule")).put("interval_minutes", 60);
        assertThrows(IllegalArgumentException.class, () -> guard.prepare(incompatible));
    }

    @Test
    void fieldsMatchOriginalRuleWriteContract() throws Exception {
        var schema =
                json.readTree(
                                Files.readString(
                                        Path.of(
                                                "../docs/orbit/baseline/contracts/openapi-current.json")))
                        .path("components")
                        .path("schemas")
                        .path("RuleWrite");
        Set<String> expected = new HashSet<>(), actual = new HashSet<>();
        schema.path("properties").fieldNames().forEachRemaining(expected::add);
        request(json).fieldNames().forEachRemaining(actual::add);
        assertEquals(expected, actual);
    }
}
