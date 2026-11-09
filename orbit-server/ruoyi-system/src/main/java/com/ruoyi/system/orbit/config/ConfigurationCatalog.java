package com.ruoyi.system.orbit.config;

import java.math.BigDecimal;
import java.net.URI;
import java.text.Normalizer;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Set;

/** 系统配置字段白名单；前后端共享字段元数据，密钥字段绝不进入普通settings。 */
public final class ConfigurationCatalog {
    /** 对外字段描述只含公开规则和默认值，不含任何密钥。 */
    public record Field(
            String key,
            String label,
            String type,
            boolean required,
            Object defaultValue,
            Integer minimum,
            Integer maximum,
            List<String> options) {}

    /** 同一类型可建多个配置，例如不同BM与不同模型配置。 */
    public record Section(String key, String label, List<Field> fields) {}

    private static Field text(String key, String label, boolean required, String value) {
        return new Field(key, label, "text", required, value, null, 500, List.of());
    }

    private static Field secret(String key, String label) {
        return new Field(key, label, "secret", true, null, 1, 8192, List.of());
    }

    private static Field number(String key, String label, int value, int min, int max) {
        return new Field(key, label, "integer", true, value, min, max, List.of());
    }

    private static Field choice(String key, String label, String value, String... options) {
        return new Field(key, label, "select", true, value, null, null, List.of(options));
    }

    private static final List<Section> SECTIONS =
            List.of(
                    new Section(
                            "AI_GPT",
                            "GPT API",
                            List.of(
                                    text("model", "模型ID", true, ""),
                                    number("timeoutSeconds", "请求超时（秒）", 60, 1, 60),
                                    number("maxRetries", "最多重试次数", 2, 0, 2),
                                    number("maxOutputTokens", "最大输出Token", 4096, 256, 32768),
                                    secret("apiKey", "OpenAI API Key"))),
                    new Section(
                            "AI_CLAUDE",
                            "Claude API",
                            List.of(
                                    text("model", "模型ID", true, ""),
                                    text("apiVersion", "Anthropic API版本", true, "2026-10-21"),
                                    text("workspaceId", "工作区ID（非工作区限定Key需填写）", false, ""),
                                    number("timeoutSeconds", "请求超时（秒）", 60, 1, 60),
                                    number("maxRetries", "最多重试次数", 2, 0, 2),
                                    number("maxOutputTokens", "最大输出Token", 4096, 256, 32768),
                                    secret("apiKey", "Claude API Key"))),
                    new Section(
                            "AI_SUGGESTIONS",
                            "AI建议策略",
                            List.of(
                                    text("providerConfigId", "默认AI配置ID", true, ""),
                                    text("promptVersion", "提示词版本", true, "suggestion-v1"),
                                    number("snapshotMaxAgeMinutes", "快照最长有效分钟", 30, 1, 30),
                                    number("observationHours", "新对象观察小时", 24, 24, 720),
                                    number("minimumImpressions", "最低曝光", 1000, 1000, 1000000),
                                    number("minimumClicks", "最低点击", 20, 20, 1000000),
                                    number("minimumPurchasesForDelete", "删除最低购物数", 5, 5, 1000000),
                                    number("minimumPausedHours", "删除最低暂停小时", 72, 72, 8760),
                                    number("maturityDays", "归因成熟天数", 28, 28, 365),
                                    number("maxConcurrentAnalysis", "最大并发分析数", 2, 1, 20),
                                    number("maxDailyPoints", "输入最多逐日点", 28, 0, 28),
                                    number("maxEvidenceItems", "输入最多证据条数", 500, 1, 500),
                                    number("maxOutputTokens", "建议最大输出Token", 4096, 256, 32768),
                                    // 规则级限制与全局限制须取更严格者；运行期原子计数由规则执行器负责。
                                    number("minimumCooldownMinutes", "分析冷却下限（分钟）", 60, 0, 10080),
                                    number(
                                            "maximumDailyAnalysesPerObject",
                                            "每规则每对象每日分析上限",
                                            5,
                                            1,
                                            1000))),
                    new Section(
                            "META_APP",
                            "Meta应用",
                            List.of(
                                    text("appId", "Meta App ID", true, ""),
                                    text("graphVersion", "Graph API版本（如v25.0）", true, ""),
                                    secret("appSecret", "Meta App Secret"))),
                    new Section(
                            "META_BM",
                            "Facebook BM授权",
                            List.of(
                                    text("businessId", "Business Manager ID", true, ""),
                                    text("systemUserId", "系统用户ID", false, ""),
                                    text("graphVersion", "Graph API版本", true, ""),
                                    secret("accessToken", "BM访问Token"))),
                    new Section(
                            "ADSPOWER",
                            "AdsPower执行设置",
                            List.of(
                                    text("agentId", "执行Agent ID", true, ""),
                                    text("localSecretRef", "执行机本地密钥引用（不上传Local API Key）", true, ""),
                                    number("heartbeatSeconds", "心跳秒数", 15, 15, 15),
                                    number("leaseSeconds", "租约秒数", 120, 120, 120),
                                    number("leaseRenewSeconds", "续租秒数", 20, 20, 20),
                                    number("maxActiveProfiles", "每机器最大活动Profile", 2, 1, 20))),
                    new Section(
                            "OIDC",
                            "OIDC身份认证",
                            List.of(
                                    text("issuer", "Issuer HTTPS地址", true, ""),
                                    text("clientId", "Client ID", true, ""),
                                    text("redirectUri", "回调HTTPS地址", true, ""),
                                    secret("clientSecret", "Client Secret"))),
                    new Section(
                            "STORAGE",
                            "对象存储",
                            List.of(
                                    text("endpoint", "S3兼容HTTPS地址", true, ""),
                                    text("bucket", "Bucket", true, ""),
                                    text("region", "Region", true, ""),
                                    secret("accessKey", "Access Key"),
                                    secret("secretKey", "Secret Key"))),
                    new Section(
                            "METRICS",
                            "指标同步",
                            List.of(
                                    number("intervalMinutes", "同步间隔分钟", 15, 1, 1440),
                                    number("lookbackDays", "回补业务日", 7, 1, 93),
                                    text("profileVersion", "指标Profile版本", true, ""),
                                    text("registerActionType", "注册事件映射", true, ""),
                                    text("purchaseActionType", "购物事件映射", true, ""),
                                    text("valueActionType", "购物价值映射", true, ""))),
                    new Section(
                            "NOTIFICATIONS",
                            "通知服务",
                            List.of(
                                    choice("channel", "通知渠道", "IN_APP", "IN_APP", "WEBHOOK"),
                                    text("webhookUrl", "Webhook HTTPS地址", false, ""),
                                    new Field(
                                            "webhookToken",
                                            "Webhook签名Token",
                                            "secret",
                                            false,
                                            null,
                                            1,
                                            8192,
                                            List.of()))),
                    new Section(
                            "RISK",
                            "执行风控（只允许收紧默认上限）",
                            List.of(
                                    number("singleChangePercent", "单次预算变动上限（%）", 20, 1, 20),
                                    number("positiveRollingPercent", "24小时累计正增上限（%）", 30, 1, 30),
                                    number("lifetimeSpendMaxAgeSeconds", "消耗证据有效秒数", 300, 1, 300),
                                    number("previewTtlMinutes", "预览有效分钟", 15, 1, 15))));

    private ConfigurationCatalog() {}

    /** 配置类型和字段列表用于驱动原生Element Plus表单，不暴露部署主密钥。 */
    public static List<Section> sections() {
        return SECTIONS;
    }

    public static Section section(String key) {
        return SECTIONS.stream()
                .filter(value -> value.key().equals(key))
                .findFirst()
                .orElseThrow(
                        () -> new ConfigurationException(422, "INVALID_SECTION", "不支持的系统配置类型"));
    }

    /** 归一化公开字段并拒绝未知/密钥字段，启用时验证所有条件必填。 */
    public static Map<String, Object> validate(
            String sectionKey, Map<String, Object> input, boolean enabled) {
        Section section = section(sectionKey);
        Map<String, Field> allowed = new LinkedHashMap<>();
        section.fields().stream()
                .filter(field -> !field.type().equals("secret"))
                .forEach(field -> allowed.put(field.key(), field));
        if (input == null || !allowed.keySet().containsAll(input.keySet())) {
            throw new ConfigurationException(400, "UNKNOWN_FIELD", "配置包含未知字段或错误的密钥字段位置");
        }
        Map<String, Object> result = new LinkedHashMap<>();
        for (Field field : allowed.values()) {
            Object value = input.getOrDefault(field.key(), field.defaultValue());
            if (field.type().equals("integer")) {
                if (!(value instanceof Number)) {
                    throw invalid(field);
                }
                try {
                    int integer = new BigDecimal(value.toString()).intValueExact();
                    if (integer < field.minimum() || integer > field.maximum()) {
                        throw invalid(field);
                    }
                    value = integer;
                } catch (ArithmeticException | NumberFormatException exception) {
                    throw invalid(field);
                }
            } else {
                if (!(value instanceof String)) {
                    throw invalid(field);
                }
                String text = Normalizer.normalize((String) value, Normalizer.Form.NFC).trim();
                if (text.codePoints().anyMatch(Character::isISOControl)
                        || text.codePointCount(0, text.length()) > 500
                        || (enabled && field.required() && text.isEmpty())) {
                    throw invalid(field);
                }
                if (field.type().equals("select") && !field.options().contains(text)) {
                    throw invalid(field);
                }
                value = text;
            }
            result.put(field.key(), value);
        }
        if (sectionKey.startsWith("META_")) {
            requirePattern(result, "graphVersion", "v[0-9]{1,3}\\.[0-9]{1,2}", enabled);
            requirePattern(
                    result,
                    sectionKey.equals("META_APP") ? "appId" : "businessId",
                    "[0-9]{1,64}",
                    enabled);
            if (sectionKey.equals("META_BM")) {
                requirePattern(result, "systemUserId", "[0-9]{1,64}", false);
            }
        }
        if (sectionKey.equals("AI_CLAUDE")) {
            requirePattern(result, "apiVersion", "[0-9]{4}-[0-9]{2}-[0-9]{2}", true);
            requirePattern(result, "workspaceId", "wrkspc_[A-Za-z0-9]+", false);
        }
        for (String key : Set.of("issuer", "redirectUri", "endpoint", "webhookUrl")) {
            if (result.containsKey(key) && !result.get(key).toString().isBlank()) {
                try {
                    URI uri = URI.create(result.get(key).toString());
                    if (!"https".equals(uri.getScheme())
                            || uri.getHost() == null
                            || uri.getUserInfo() != null
                            || uri.getFragment() != null) {
                        throw new IllegalArgumentException();
                    }
                } catch (IllegalArgumentException exception) {
                    throw new ConfigurationException(
                            422, "INVALID_URL", "集成地址必须为不含凭据和片段的有效HTTPS地址");
                }
            }
        }
        if (sectionKey.equals("NOTIFICATIONS")
                && "WEBHOOK".equals(result.get("channel"))
                && enabled
                && result.get("webhookUrl").toString().isBlank()) {
            throw new ConfigurationException(422, "WEBHOOK_REQUIRED", "启用Webhook通知时必须提供地址");
        }
        return result;
    }

    public static String normalizeText(String text, int maxCodepoints, String label) {
        if (text == null) {
            throw new ConfigurationException(422, "FIELD_REQUIRED", label + "必填");
        }
        String normalized = Normalizer.normalize(text, Normalizer.Form.NFC).trim();
        if (normalized.isBlank()
                || normalized.codePointCount(0, normalized.length()) > maxCodepoints
                || normalized.codePoints().anyMatch(Character::isISOControl)) {
            throw new ConfigurationException(422, "FIELD_INVALID", label + "格式或长度不符合要求");
        }
        return normalized;
    }

    private static void requirePattern(
            Map<String, Object> settings, String key, String pattern, boolean required) {
        String value = settings.get(key).toString();
        if ((!value.isBlank() || required) && !value.matches(pattern)) {
            throw new ConfigurationException(422, "FIELD_INVALID", "配置字段格式不正确：" + key);
        }
    }

    private static ConfigurationException invalid(Field field) {
        return new ConfigurationException(422, "FIELD_INVALID", field.label() + "不符合必填、类型或范围限制");
    }
}
