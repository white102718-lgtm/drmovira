package com.ruoyi.system.orbit.rules;

import static com.ruoyi.system.orbit.rules.RuleConditions.*;
import static org.junit.jupiter.api.Assertions.*;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.node.*;
import java.math.BigDecimal;
import java.nio.file.*;
import java.util.*;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.params.ParameterizedTest;
import org.junit.jupiter.params.provider.*;

/** 三值逻辑、合同字段、十进制精度、两层AST与逐条件缺失原因回归，不使用平台或数据库。 */
class RuleConditionsTest {
    private final ObjectMapper json = new ObjectMapper();
    private final RuleConditions engine = new RuleConditions();

    private ObjectNode leaf(String metric, String operator, String threshold) {
        return json.createObjectNode()
                .put("metric", metric)
                .put("operator", operator)
                .put("threshold", threshold);
    }

    private ObjectNode expression(String logic, ObjectNode... conditions) {
        ObjectNode root = json.createObjectNode().put("logic", logic);
        ObjectNode group = root.putArray("groups").addObject().put("logic", logic);
        ArrayNode leaves = group.putArray("conditions");
        for (ObjectNode condition : conditions) leaves.add(condition);
        return root;
    }

    private Evaluation evaluate(ObjectNode expression, Map<String, String> values) {
        return engine.evaluate(engine.parse(expression), values);
    }

    @ParameterizedTest
    @CsvSource({
        "AND,TRUE,TRUE,TRUE",
        "AND,TRUE,FALSE,FALSE",
        "AND,TRUE,UNKNOWN,UNKNOWN",
        "AND,FALSE,TRUE,FALSE",
        "AND,FALSE,FALSE,FALSE",
        "AND,FALSE,UNKNOWN,FALSE",
        "AND,UNKNOWN,TRUE,UNKNOWN",
        "AND,UNKNOWN,FALSE,FALSE",
        "AND,UNKNOWN,UNKNOWN,UNKNOWN",
        "OR,TRUE,TRUE,TRUE",
        "OR,TRUE,FALSE,TRUE",
        "OR,TRUE,UNKNOWN,TRUE",
        "OR,FALSE,TRUE,TRUE",
        "OR,FALSE,FALSE,FALSE",
        "OR,FALSE,UNKNOWN,UNKNOWN",
        "OR,UNKNOWN,TRUE,TRUE",
        "OR,UNKNOWN,FALSE,UNKNOWN",
        "OR,UNKNOWN,UNKNOWN,UNKNOWN"
    })
    void followsCompleteThreeValuedTruthTable(
            String logic, String left, String right, String expected) {
        Map<String, String> values = new HashMap<>();
        if (!left.equals("UNKNOWN")) values.put("spend", left.equals("TRUE") ? "1" : "0");
        if (!right.equals("UNKNOWN")) values.put("clicks", right.equals("TRUE") ? "1" : "0");
        var result =
                evaluate(
                        expression(logic, leaf("spend", "EQ", "1"), leaf("clicks", "EQ", "1")),
                        values);
        assertEquals(Truth.valueOf(expected), result.result());
        assertEquals(expected.equals("TRUE"), result.candidate());
        assertEquals(2, result.groups().getFirst().conditions().size());
        ObjectNode separate = expression(logic, leaf("spend", "EQ", "1"));
        ((ArrayNode) separate.path("groups"))
                .add(expression(logic, leaf("clicks", "EQ", "1")).path("groups").get(0));
        assertEquals(Truth.valueOf(expected), evaluate(separate, values).result());
    }

    @ParameterizedTest
    @CsvSource({
        "GT,0,FALSE",
        "GT,1,FALSE",
        "GT,2,TRUE",
        "GTE,0,FALSE",
        "GTE,1,TRUE",
        "GTE,2,TRUE",
        "LT,0,TRUE",
        "LT,1,FALSE",
        "LT,2,FALSE",
        "LTE,0,TRUE",
        "LTE,1,TRUE",
        "LTE,2,FALSE",
        "EQ,0,FALSE",
        "EQ,1,TRUE",
        "EQ,2,FALSE",
        "NEQ,0,TRUE",
        "NEQ,1,FALSE",
        "NEQ,2,TRUE"
    })
    void comparesEachOperatorBelowAtAndAboveThreshold(
            String operator, String observed, String expected) {
        assertEquals(
                Truth.valueOf(expected),
                evaluate(
                                expression("AND", leaf("spend", operator, "1.000000")),
                                Map.of("spend", observed))
                        .result());
    }

    @Test
    void nullNotEqualZeroIsUnknownAndMissingReasonsRemainDistinct() {
        ObjectNode rule = expression("AND", leaf("clicks", "NEQ", "0"));
        Map<String, String> values = new HashMap<>();
        values.put("clicks", null);
        var result = evaluate(rule, values);
        assertFalse(result.candidate());
        assertEquals(Truth.UNKNOWN, result.result());
        assertEquals(
                MissingReason.NULL_VALUE,
                result.groups().getFirst().conditions().getFirst().reason());
        assertEquals(
                MissingReason.MISSING,
                evaluate(rule, Map.of()).groups().getFirst().conditions().getFirst().reason());
        assertEquals(Truth.FALSE, evaluate(rule, Map.of("clicks", "0")).result());
    }

    @Test
    void rootAndGroupLogicAreIndependentAndAllLeavesRemainVisible() {
        ObjectNode root = expression("OR", leaf("spend", "EQ", "1"), leaf("clicks", "EQ", "1"));
        ((ObjectNode) root.path("groups").get(0)).put("logic", "AND");
        ((ArrayNode) root.path("groups"))
                .add(
                        json.createObjectNode()
                                .put("logic", "OR")
                                .set(
                                        "conditions",
                                        json.createArrayNode()
                                                .add(leaf("purchases", "EQ", "1"))
                                                .add(leaf("roas", "EQ", "1"))));
        var result = evaluate(root, Map.of("spend", "0", "purchases", "1"));
        assertEquals(Truth.TRUE, result.result());
        assertEquals(Truth.FALSE, result.groups().get(0).result());
        assertEquals(Truth.TRUE, result.groups().get(1).result());
        assertEquals(MissingReason.MISSING, result.groups().get(1).conditions().get(1).reason());
    }

    @ParameterizedTest
    @ValueSource(
            strings = {
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
                "cpa"
            })
    void acceptsEveryContractMetric(String metric) {
        assertTrue(
                evaluate(expression("AND", leaf(metric, "GTE", "0")), Map.of(metric, "0"))
                        .candidate());
    }

    @ParameterizedTest
    @ValueSource(strings = {"spend", "purchase_value", "cpm", "cpc", "cpa"})
    void enforcesMoneyUpperBoundaryWithoutRounding(String metric) {
        assertNotNull(engine.parse(expression("AND", leaf(metric, "EQ", "1000000000.000000"))));
        assertThrows(
                IllegalArgumentException.class,
                () -> engine.parse(expression("AND", leaf(metric, "EQ", "1000000000.000001"))));
    }

    @Test
    void ctrUsesPercentAndRoasHasIndependentRatioBoundary() {
        assertNotNull(
                engine.parse(
                        expression(
                                "AND", leaf("ctr", "EQ", "100"), leaf("roas", "EQ", "1000000"))));
        assertThrows(
                IllegalArgumentException.class,
                () -> engine.parse(expression("AND", leaf("ctr", "EQ", "100.000001"))));
        assertThrows(
                IllegalArgumentException.class,
                () -> engine.parse(expression("AND", leaf("roas", "EQ", "1000000.000001"))));
        assertTrue(
                evaluate(expression("AND", leaf("ctr", "EQ", "1")), Map.of("ctr", "1.000000"))
                        .candidate());
    }

    @ParameterizedTest
    @ValueSource(strings = {"impressions", "clicks", "registrations", "purchases"})
    void countsRequireIntegralValuesWithoutInventingZero(String metric) {
        assertNotNull(engine.parse(expression("AND", leaf(metric, "EQ", "1.000000"))));
        assertThrows(
                IllegalArgumentException.class,
                () -> engine.parse(expression("AND", leaf(metric, "EQ", "1.000001"))));
        var result = evaluate(expression("AND", leaf(metric, "EQ", "0")), Map.of(metric, "0.1"));
        assertEquals(Truth.UNKNOWN, result.result());
        assertEquals(
                MissingReason.INVALID_VALUE,
                result.groups().getFirst().conditions().getFirst().reason());
    }

    @ParameterizedTest
    @ValueSource(
            strings = {
                "",
                " ",
                "-1",
                "+1",
                "01",
                ".1",
                "1.",
                "1e2",
                "NaN",
                "1,000",
                "0.0000001",
                "10000000000000000000000000000"
            })
    void rejectsNonContractThresholdLiterals(String threshold) {
        var error =
                assertThrows(
                        IllegalArgumentException.class,
                        () -> engine.parse(expression("AND", leaf("spend", "EQ", threshold))));
        assertEquals("规则条件结构、指标、比较符或阈值无效", error.getMessage());
    }

    @ParameterizedTest
    @ValueSource(strings = {"", "private-token-value", "-1", "NaN", "1e2", "0.0000001"})
    void invalidObservedValuesAreUnknownAndNeverEchoed(String raw) {
        var result = evaluate(expression("AND", leaf("spend", "NEQ", "0")), Map.of("spend", raw));
        var condition = result.groups().getFirst().conditions().getFirst();
        assertEquals(Truth.UNKNOWN, result.result());
        assertNull(condition.observed());
        assertEquals(MissingReason.INVALID_VALUE, condition.reason());
        assertFalse(result.toString().contains("private-token-value"));
        assertFalse(json.valueToTree(result).toString().contains("private-token-value"));
    }

    @Test
    void decimalComparisonRetainsSixPlacesAndCountsAboveJavascriptSafeInteger() {
        assertTrue(
                evaluate(
                                expression("AND", leaf("spend", "GT", "0.123455")),
                                Map.of("spend", "0.123456"))
                        .candidate());
        assertTrue(
                evaluate(
                                expression("AND", leaf("clicks", "GT", "9007199254740992")),
                                Map.of("clicks", "9007199254740993"))
                        .candidate());
        assertFalse(
                evaluate(
                                expression("AND", leaf("clicks", "EQ", "9007199254740992")),
                                Map.of("clicks", "9007199254740993"))
                        .candidate());
        assertNotNull(
                engine.parse(
                        expression("AND", leaf("clicks", "EQ", "9999999999999999999999999999"))));
    }

    @Test
    void rejectsUnknownMetricOperatorExtraFieldsAndThirdAstLevel() {
        assertThrows(
                IllegalArgumentException.class,
                () -> engine.parse(expression("AND", leaf("unknown_metric", "EQ", "0"))));
        assertThrows(
                IllegalArgumentException.class,
                () -> engine.parse(expression("AND", leaf("spend", "eval(script)", "0"))));
        assertThrows(
                IllegalArgumentException.class,
                () ->
                        engine.parse(
                                expression(
                                        "AND",
                                        leaf("spend", "EQ", "0").put("script", "ignored?"))));
        ObjectNode extraRoot =
                expression("AND", leaf("spend", "EQ", "0")).put("script", "ignored?");
        assertThrows(IllegalArgumentException.class, () -> engine.parse(extraRoot));
        ObjectNode extraGroup = expression("AND", leaf("spend", "EQ", "0"));
        ((ObjectNode) extraGroup.path("groups").get(0)).putArray("groups");
        assertThrows(IllegalArgumentException.class, () -> engine.parse(extraGroup));
        ObjectNode nested = expression("AND", leaf("spend", "EQ", "0"));
        ((ArrayNode) nested.path("groups").get(0).path("conditions")).set(0, extraRoot);
        assertThrows(IllegalArgumentException.class, () -> engine.parse(nested));
        assertThrows(
                IllegalArgumentException.class,
                () -> engine.parse(expression("and", leaf("spend", "EQ", "0"))));
    }

    @Test
    void rejectsMissingNullNumericAndWrongContainerTypes() {
        for (ObjectNode bad :
                List.of(
                        expression("AND", leaf("spend", "EQ", "0").putNull("threshold")),
                        expression("AND", leaf("spend", "EQ", "0").put("threshold", 0)),
                        expression("AND", leaf("spend", "EQ", "0").putNull("metric")),
                        expression("AND", leaf("spend", "EQ", "0")).putNull("groups"),
                        expression("AND", leaf("spend", "EQ", "0")).put("groups", "array?"))) {
            assertThrows(IllegalArgumentException.class, () -> engine.parse(bad));
        }
        ObjectNode missing = expression("AND", leaf("spend", "EQ", "0"));
        missing.remove("logic");
        assertThrows(IllegalArgumentException.class, () -> engine.parse(missing));
        assertThrows(IllegalArgumentException.class, () -> engine.parse(null));
    }

    @Test
    void boundsGroupSizeAndTotalConditionCountIndependently() {
        ObjectNode root = expression("AND", leaf("spend", "EQ", "0"));
        ArrayNode groups = (ArrayNode) root.path("groups");
        ObjectNode group = (ObjectNode) groups.get(0);
        ArrayNode conditions = (ArrayNode) group.path("conditions");
        conditions.removeAll();
        assertThrows(IllegalArgumentException.class, () -> engine.parse(root));
        for (int i = 0; i < 10; i++) conditions.add(leaf("spend", "EQ", "0"));
        groups.add(group.deepCopy());
        assertNotNull(engine.parse(root));
        groups.add(expression("AND", leaf("clicks", "EQ", "0")).path("groups").get(0));
        assertThrows(IllegalArgumentException.class, () -> engine.parse(root));
        groups.removeAll();
        groups.add(group);
        conditions.add(leaf("spend", "EQ", "0"));
        assertThrows(IllegalArgumentException.class, () -> engine.parse(root));
        groups.removeAll();
        assertThrows(IllegalArgumentException.class, () -> engine.parse(root));
        for (int i = 0; i < 6; i++)
            groups.add(expression("AND", leaf("clicks", "EQ", "0")).path("groups").get(0));
        assertThrows(IllegalArgumentException.class, () -> engine.parse(root));
        groups.remove(5);
        assertNotNull(engine.parse(root));
    }

    @Test
    void parsedDefinitionAndEvaluationAreImmutableAndDirectConstructionCannotBypassLimits() {
        ObjectNode source = expression("AND", leaf("spend", "EQ", "1"));
        Definition frozen = engine.parse(source);
        ((ObjectNode) source.path("groups").get(0).path("conditions").get(0)).put("threshold", "2");
        assertTrue(engine.evaluate(frozen, Map.of("spend", "1")).candidate());
        assertThrows(UnsupportedOperationException.class, () -> frozen.groups().clear());
        assertThrows(
                UnsupportedOperationException.class,
                () -> frozen.groups().getFirst().conditions().clear());
        assertThrows(
                UnsupportedOperationException.class,
                () -> engine.evaluate(frozen, Map.of()).groups().clear());
        assertThrows(
                IllegalArgumentException.class,
                () -> new Condition("unknown", Operator.EQ, BigDecimal.ZERO));
        assertThrows(
                IllegalArgumentException.class,
                () -> new Condition("ctr", Operator.EQ, new BigDecimal("101")));
        assertThrows(
                IllegalArgumentException.class,
                () -> new Condition("spend", Operator.EQ, new BigDecimal("1E+100000")));
        assertThrows(IllegalArgumentException.class, () -> new Group(Logic.AND, List.of()));
        assertThrows(IllegalArgumentException.class, () -> new Definition(Logic.AND, List.of()));
    }

    @Test
    void productWhitelistAndStructuralLimitsRemainUnchanged() throws Exception {
        var schemas =
                json.readTree(
                                Files.readString(
                                        Path.of(
                                                "../docs/orbit/baseline/contracts/openapi-current.json")))
                        .path("components")
                        .path("schemas");
        Set<String> metrics = new HashSet<>();
        schemas.path("Condition")
                .path("properties")
                .path("metric")
                .path("enum")
                .forEach(value -> metrics.add(value.asText()));
        assertEquals(
                Set.of(
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
                        "cpa"),
                metrics);
        assertEquals(
                6,
                schemas.path("Condition").path("properties").path("operator").path("enum").size());
        assertEquals(
                10,
                schemas.path("ConditionGroup")
                        .path("properties")
                        .path("conditions")
                        .path("maxItems")
                        .asInt());
        assertEquals(
                5,
                schemas.path("RuleWrite")
                        .path("properties")
                        .path("groups")
                        .path("maxItems")
                        .asInt());
    }
}
