package com.ruoyi.system.orbit.analysis;

import com.fasterxml.jackson.core.type.TypeReference;
import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.SerializationFeature;
import com.networknt.schema.*;
import com.ruoyi.system.orbit.config.ConfigurationCatalog;
import com.ruoyi.system.orbit.config.ConfigurationException;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.util.*;
import org.springframework.stereotype.Component;

/** AI调用前的事实包结构、租户、输入规模及严格策略合并；不调用模型或执行广告动作。 */
@Component
public final class AnalysisInputGuard {
    /** 输入冻结为不可变JSON字符串；toString不泄露事实包，供后续Adapter和任务持久化消费。 */
    public record FrozenInput(
            String json,
            String sha256,
            int maxOutputTokens,
            int cooldownMinutes,
            int maximumDailyAnalysesPerObject) {
        @Override
        public String toString() {
            return "FrozenInput[REDACTED]";
        }
    }

    private final ObjectMapper mapper;
    private final JsonSchema schema;

    public AnalysisInputGuard(ObjectMapper mapper) {
        this.mapper = mapper.copy().enable(SerializationFeature.ORDER_MAP_ENTRIES_BY_KEYS);
        try (var stream =
                AnalysisInputGuard.class.getResourceAsStream("/orbit/analysis-input.schema.json")) {
            if (stream == null) throw new IllegalStateException();
            var config = new SchemaValidatorsConfig();
            config.setFormatAssertionsEnabled(true);
            this.schema =
                    JsonSchemaFactory.getInstance(SpecVersion.VersionFlag.V202012)
                            .getSchema(this.mapper.readTree(stream), config);
        } catch (Exception error) {
            throw new IllegalStateException("分析输入Schema无法加载");
        }
    }

    /** 可信租户必须由服务端任务上下文提供；本方法不替代上游对象权限/规则范围检查。 */
    public FrozenInput prepare(
            JsonNode input,
            String expectedTenant,
            Map<String, Object> policy,
            int providerMaxOutputTokens,
            int ruleCooldownMinutes,
            int ruleMaximumDaily) {
        if (input == null || !schema.validate(input).isEmpty()) throw invalid();
        if (!input.path("tenant_id").asText().equals(expectedTenant)) {
            throw new ConfigurationException(403, "ANALYSIS_TENANT_MISMATCH", "分析事实包不属于当前租户");
        }
        Map<String, Object> settings =
                ConfigurationCatalog.validate("AI_SUGGESTIONS", policy, false);
        if (ruleCooldownMinutes < 0
                || ruleCooldownMinutes > 10080
                || ruleMaximumDaily < 1
                || ruleMaximumDaily > 1000
                || providerMaxOutputTokens < 256
                || providerMaxOutputTokens > 32768) throw invalid();
        if (input.path("daily_points").size() > (Integer) settings.get("maxDailyPoints")
                || input.path("evidence").size() > (Integer) settings.get("maxEvidenceItems"))
            throw invalid();
        // 结构验证之外，覆盖率不得超出0至1，证据不能重号，逐日点不能同日重复。
        if (new java.math.BigDecimal(input.path("coverage").asText())
                        .compareTo(java.math.BigDecimal.ONE)
                > 0) throw invalid();
        Set<String> ids = new HashSet<>();
        for (JsonNode evidence : input.path("evidence")) {
            String id = evidence.path("id").asText();
            if (!id.matches("[a-f0-9]{64}") || !ids.add(id)) throw invalid();
        }
        Set<String> days = new HashSet<>();
        for (JsonNode point : input.path("daily_points")) {
            if (!days.add(point.path("business_date").asText())) throw invalid();
        }
        try {
            // 转成Map后递归按键排序，保留数组顺序与十进制字符串，不转换金额精度。
            Map<String, Object> facts =
                    mapper.convertValue(input, new TypeReference<Map<String, Object>>() {});
            String frozen = mapper.writeValueAsString(facts);
            String hash =
                    HexFormat.of()
                            .formatHex(
                                    MessageDigest.getInstance("SHA-256")
                                            .digest(frozen.getBytes(StandardCharsets.UTF_8)));
            return new FrozenInput(
                    frozen,
                    hash,
                    Math.min((Integer) settings.get("maxOutputTokens"), providerMaxOutputTokens),
                    Math.max((Integer) settings.get("minimumCooldownMinutes"), ruleCooldownMinutes),
                    Math.min(
                            (Integer) settings.get("maximumDailyAnalysesPerObject"),
                            ruleMaximumDaily));
        } catch (Exception error) {
            throw invalid();
        }
    }

    private static ConfigurationException invalid() {
        // 禁止拼接Schema错误、被拒绝值或原始事实包，避免凭据/联系人随失败日志传播。
        return new ConfigurationException(422, "ANALYSIS_INPUT_INVALID", "分析输入结构、证据或限制不符合要求");
    }
}
