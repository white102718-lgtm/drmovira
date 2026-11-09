package com.ruoyi.system.orbit.rules;

import com.fasterxml.jackson.databind.JsonNode;
import java.math.BigDecimal;
import java.util.*;
import org.springframework.stereotype.Component;

/** 模拟和调度共用的两层条件核心；只比较可信快照值，不执行脚本、不拼接SQL或调用模型。 */
@Component
public final class RuleConditions {
    public enum Truth {
        TRUE,
        FALSE,
        UNKNOWN
    }

    public enum Logic {
        AND,
        OR
    }

    public enum Operator {
        GT,
        GTE,
        LT,
        LTE,
        EQ,
        NEQ
    }

    public enum MissingReason {
        NONE,
        MISSING,
        NULL_VALUE,
        INVALID_VALUE
    }

    private static final Set<String> COUNTS =
            Set.of("impressions", "clicks", "registrations", "purchases");
    private static final Set<String> MONEY = Set.of("spend", "purchase_value", "cpm", "cpc", "cpa");
    private static final Set<String> METRICS =
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
                    "cpa");
    private static final String DECIMAL = "(0|[1-9][0-9]*)(\\.[0-9]{1,6})?";

    /** 阈值一直使用BigDecimal，EQ比较数值而不是scale，避免double精度或字符串比较。 */
    public record Condition(String metric, Operator operator, BigDecimal threshold) {
        public Condition {
            if (metric == null
                    || !METRICS.contains(metric)
                    || operator == null
                    || !validDecimal(threshold)) throw invalid();
            if (COUNTS.contains(metric) && threshold.stripTrailingZeros().scale() > 0)
                throw invalid();
            BigDecimal maximum =
                    MONEY.contains(metric)
                            ? new BigDecimal("1000000000")
                            : metric.equals("ctr")
                                    ? new BigDecimal("100")
                                    : metric.equals("roas") ? new BigDecimal("1000000") : null;
            if (maximum != null && threshold.compareTo(maximum) > 0) throw invalid();
        }

        @Override
        public String toString() {
            return "Condition[REDACTED]";
        }
    }

    public record Group(Logic logic, List<Condition> conditions) {
        public Group {
            if (logic == null
                    || conditions == null
                    || conditions.isEmpty()
                    || conditions.size() > 10
                    || conditions.stream().anyMatch(Objects::isNull)) throw invalid();
            conditions = List.copyOf(conditions);
        }
    }

    public record Definition(Logic logic, List<Group> groups) {
        public Definition {
            if (logic == null
                    || groups == null
                    || groups.isEmpty()
                    || groups.size() > 5
                    || groups.stream().anyMatch(Objects::isNull)) throw invalid();
            if (groups.stream().mapToInt(group -> group.conditions().size()).sum() > 20)
                throw invalid();
            groups = List.copyOf(groups);
        }
    }

    /** 无效原始值不进入结果或日志；只有通过十进制校验的观察值才能进入逐条件明细。 */
    public record ConditionResult(
            String metric,
            Operator operator,
            BigDecimal threshold,
            BigDecimal observed,
            Truth result,
            MissingReason reason) {
        @Override
        public String toString() {
            return "ConditionResult[REDACTED]";
        }
    }

    public record GroupResult(Logic logic, Truth result, List<ConditionResult> conditions) {
        public GroupResult {
            conditions = List.copyOf(conditions);
        }
    }

    public record Evaluation(Truth result, List<GroupResult> groups) {
        public Evaluation {
            groups = List.copyOf(groups);
        }

        /** 仅候选，不代表授权、完整coverage、观察期或新鲜度已经通过。 */
        public boolean candidate() {
            return result == Truth.TRUE;
        }
    }

    /** 接收从RuleWrite投影出的logic/groups子对象，严格拒绝额外AST层和属性。 */
    public Definition parse(JsonNode input) {
        exactFields(input, Set.of("logic", "groups"));
        Logic logic = logic(input.get("logic"));
        JsonNode groups = input.get("groups");
        if (!groups.isArray() || groups.isEmpty() || groups.size() > 5) throw invalid();
        List<Group> parsed = new ArrayList<>();
        for (JsonNode group : groups) {
            exactFields(group, Set.of("logic", "conditions"));
            Logic groupLogic = logic(group.get("logic"));
            JsonNode conditions = group.get("conditions");
            if (!conditions.isArray() || conditions.isEmpty() || conditions.size() > 10)
                throw invalid();
            List<Condition> leaves = new ArrayList<>();
            for (JsonNode condition : conditions) {
                exactFields(condition, Set.of("metric", "operator", "threshold"));
                String metric = text(condition.get("metric")),
                        operator = text(condition.get("operator")),
                        threshold = text(condition.get("threshold"));
                if (threshold.length() > 28 || !threshold.matches(DECIMAL)) throw invalid();
                try {
                    leaves.add(
                            new Condition(
                                    metric, Operator.valueOf(operator), new BigDecimal(threshold)));
                } catch (IllegalArgumentException error) {
                    throw invalid();
                }
            }
            parsed.add(new Group(groupLogic, leaves));
        }
        return new Definition(logic, parsed);
    }

    /** 调用者必须从冻结且已鉴权的数据快照构造values；这里只做数值比较，不验证快照来源。 */
    public Evaluation evaluate(Definition definition, Map<String, String> values) {
        if (definition == null || values == null) throw invalid();
        Map<String, String> snapshot = new HashMap<>(values);
        List<GroupResult> results = new ArrayList<>();
        for (Group group : definition.groups()) {
            List<ConditionResult> leaves = new ArrayList<>();
            for (Condition condition : group.conditions())
                leaves.add(evaluate(condition, snapshot));
            results.add(
                    new GroupResult(
                            group.logic(),
                            combine(
                                    group.logic(),
                                    leaves.stream().map(ConditionResult::result).toList()),
                            leaves));
        }
        return new Evaluation(
                combine(definition.logic(), results.stream().map(GroupResult::result).toList()),
                results);
    }

    private ConditionResult evaluate(Condition condition, Map<String, String> values) {
        String raw = values.get(condition.metric());
        MissingReason reason =
                !values.containsKey(condition.metric())
                        ? MissingReason.MISSING
                        : raw == null ? MissingReason.NULL_VALUE : MissingReason.NONE;
        BigDecimal observed = null;
        if (reason == MissingReason.NONE) {
            if (raw.length() > 28 || !raw.matches(DECIMAL)) reason = MissingReason.INVALID_VALUE;
            else {
                observed = new BigDecimal(raw);
                if (COUNTS.contains(condition.metric())
                        && observed.stripTrailingZeros().scale() > 0) {
                    observed = null;
                    reason = MissingReason.INVALID_VALUE;
                }
            }
        }
        Truth result = Truth.UNKNOWN;
        if (reason == MissingReason.NONE) {
            int comparison = observed.compareTo(condition.threshold());
            boolean hit =
                    switch (condition.operator()) {
                        case GT -> comparison > 0;
                        case GTE -> comparison >= 0;
                        case LT -> comparison < 0;
                        case LTE -> comparison <= 0;
                        case EQ -> comparison == 0;
                        case NEQ -> comparison != 0;
                    };
            result = hit ? Truth.TRUE : Truth.FALSE;
        }
        return new ConditionResult(
                condition.metric(),
                condition.operator(),
                condition.threshold(),
                observed,
                result,
                reason);
    }

    private Truth combine(Logic logic, List<Truth> results) {
        // 仍计算全部叶子以返回完整缺失原因，不以短路省略模拟明细。
        if (logic == Logic.AND && results.contains(Truth.FALSE)) return Truth.FALSE;
        if (logic == Logic.OR && results.contains(Truth.TRUE)) return Truth.TRUE;
        if (results.contains(Truth.UNKNOWN)) return Truth.UNKNOWN;
        return logic == Logic.AND ? Truth.TRUE : Truth.FALSE;
    }

    private static boolean validDecimal(BigDecimal value) {
        return value != null
                && value.signum() >= 0
                && value.precision() <= 28
                && value.scale() >= -27
                && value.scale() <= 6
                && value.toPlainString().length() <= 28;
    }

    private static Logic logic(JsonNode value) {
        try {
            return Logic.valueOf(text(value));
        } catch (IllegalArgumentException error) {
            throw invalid();
        }
    }

    private static String text(JsonNode value) {
        if (value == null || !value.isTextual()) throw invalid();
        return value.textValue();
    }

    private static void exactFields(JsonNode input, Set<String> fields) {
        if (input == null || !input.isObject() || input.size() != fields.size()) throw invalid();
        input.fieldNames()
                .forEachRemaining(
                        name -> {
                            if (!fields.contains(name)) throw invalid();
                        });
    }

    private static IllegalArgumentException invalid() {
        return new IllegalArgumentException("规则条件结构、指标、比较符或阈值无效");
    }
}
