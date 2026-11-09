package com.adpulse.main.adaccountasset;

import static com.adpulse.main.adaccountasset.AdAccountAssetViews.FacebookActivitySummaryItem;

import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import java.math.BigDecimal;
import java.util.ArrayList;
import java.util.List;
import java.util.Locale;
import java.util.Map;
import java.util.Set;

/** 将 Meta 活动中的动态 extra_data 转为稳定、可直接展示的业务摘要。 */
final class FacebookActivitySummaryParser {
    private static final int MAX_COMPLEX_VALUE_LENGTH = 240;
    private static final Set<String> IGNORED_DETAIL_KEYS =
            Set.of("old_value", "new_value", "type");
    private static final Set<String> MONEY_KEYS =
            Set.of(
                    "payment_amount",
                    "daily_budget",
                    "lifetime_budget",
                    "budget",
                    "spend_cap",
                    "spending_limit",
                    "account_spending_limit",
                    "campaign_spending_limit");
    private static final Map<String, String> FIELD_LABELS =
            Map.ofEntries(
                    Map.entry("name", "名称"),
                    Map.entry("status", "状态"),
                    Map.entry("run_status", "投放状态"),
                    Map.entry("account_status", "账户状态"),
                    Map.entry("payment_amount", "金额"),
                    Map.entry("daily_budget", "日预算"),
                    Map.entry("lifetime_budget", "总预算"),
                    Map.entry("budget", "预算"),
                    Map.entry("spend_cap", "消耗上限"),
                    Map.entry("spending_limit", "账户消耗上限"),
                    Map.entry("account_spending_limit", "账户消耗上限"),
                    Map.entry("campaign_spending_limit", "广告系列消耗上限"),
                    Map.entry("currency", "币种"),
                    Map.entry("additional_value", "说明"),
                    Map.entry("bid_amount", "出价"),
                    Map.entry("bid_strategy", "出价策略"),
                    Map.entry("optimization_goal", "优化目标"),
                    Map.entry("start_time", "开始时间"),
                    Map.entry("end_time", "结束时间"));

    private final ObjectMapper objectMapper;

    FacebookActivitySummaryParser(ObjectMapper objectMapper) {
        this.objectMapper = objectMapper;
    }

    /** 按事件类型和对象层级归类，未知事件保留为 OTHER，避免前端自行猜测。 */
    String category(String eventType, String objectType) {
        String event = normalize(eventType);
        if (event.contains("billing") || event.contains("funding")) return "BILLING";
        if (event.contains("spend_limit") || event.contains("spending_limit")) {
            return "BILLING";
        }
        if (event.startsWith("ad_account_add_user")
                || event.startsWith("ad_account_remove_user")) {
            return "ACCESS";
        }
        if (event.startsWith("ad_account") || event.startsWith("adaccount")) return "ACCOUNT";
        if (event.contains("audience")) return "AUDIENCE";
        if (event.contains("image") || event.contains("creative")) return "CREATIVE";
        if (event.contains("ad_set") || event.contains("adset")) return "AD_SET";
        if (event.contains("campaign")) return "CAMPAIGN";
        if (event.startsWith("create_ad")
                || event.startsWith("update_ad")
                || event.startsWith("ad_review")
                || event.startsWith("update_adgroup")) {
            return "AD";
        }
        if (event.contains("delivery")
                || event.contains("learning_stage")
                || event.contains("lifetime_budget_spent")) {
            return "DELIVERY";
        }

        return switch (normalize(objectType).toUpperCase(Locale.ROOT)) {
            case "ACCOUNT", "AD_ACCOUNT" -> "ACCOUNT";
            case "CAMPAIGN", "CAMPAIGN_GROUP" -> "CAMPAIGN";
            case "ADSET", "AD_SET" -> "AD_SET";
            case "AD", "ADGROUP" -> "AD";
            case "AUDIENCE", "CUSTOM_AUDIENCE" -> "AUDIENCE";
            case "CREATIVE", "IMAGE" -> "CREATIVE";
            default -> "OTHER";
        };
    }

    /**
     * 解析 Meta 动态 JSON。无法识别或格式损坏时返回空列表，原始数据仍由兼容字段提供。
     */
    List<FacebookActivitySummaryItem> parse(String raw, String category) {
        if (raw == null || raw.isBlank()) return List.of();
        try {
            JsonNode root = objectMapper.readTree(raw);
            if (!root.isObject()) return List.of();

            List<FacebookActivitySummaryItem> items = new ArrayList<>();
            appendChange(items, root, category);
            appendDetails(items, root);
            return List.copyOf(items);
        } catch (JsonProcessingException ignored) {
            return List.of();
        }
    }

    private void appendChange(
            List<FacebookActivitySummaryItem> items, JsonNode root, String category) {
        JsonNode beforeNode = root.get("old_value");
        JsonNode afterNode = root.get("new_value");
        if (isMissing(beforeNode) && isMissing(afterNode)) return;

        if ((beforeNode != null && beforeNode.isObject())
                || (afterNode != null && afterNode.isObject())) {
            appendNestedChange(items, root, beforeNode, afterNode, category);
            return;
        }

        String fieldKey = text(root.get("type"));
        items.add(
                new FacebookActivitySummaryItem(
                        fieldLabel(fieldKey, category),
                        formatValue(beforeNode, fieldKey, root),
                        formatValue(afterNode, fieldKey, root),
                        null));
    }

    private void appendNestedChange(
            List<FacebookActivitySummaryItem> items,
            JsonNode root,
            JsonNode beforeNode,
            JsonNode afterNode,
            String category) {
        JsonNode beforeObject = beforeNode != null && beforeNode.isObject() ? beforeNode : null;
        JsonNode afterObject = afterNode != null && afterNode.isObject() ? afterNode : null;
        String fieldKey =
                firstNonBlank(
                        text(node(afterObject, "type")),
                        firstNonBlank(
                                text(node(beforeObject, "type")), text(node(root, "type"))));
        JsonNode beforeValue = nestedValue(beforeObject, "old_value");
        JsonNode afterValue = nestedValue(afterObject, "new_value");

        items.add(
                new FacebookActivitySummaryItem(
                        fieldLabel(fieldKey, category),
                        formatValue(beforeValue, fieldKey, beforeObject),
                        formatValue(afterValue, fieldKey, afterObject),
                        null));

        String description =
                firstNonBlank(
                        text(node(afterObject, "additional_value")),
                        text(node(beforeObject, "additional_value")));
        if (!description.isBlank()) {
            items.add(new FacebookActivitySummaryItem("说明", null, null, description));
        }
    }

    private void appendDetails(List<FacebookActivitySummaryItem> items, JsonNode root) {
        root.fields()
                .forEachRemaining(
                        field -> {
                            if (IGNORED_DETAIL_KEYS.contains(field.getKey())
                                    || isSensitiveKey(field.getKey())
                                    || isMissing(field.getValue())) {
                                return;
                            }
                            items.add(
                                    new FacebookActivitySummaryItem(
                                            fieldLabel(field.getKey(), "OTHER"),
                                            null,
                                            null,
                                            formatValue(field.getValue(), field.getKey(), root)));
                });
    }

    private boolean isSensitiveKey(String key) {
        String normalized = normalize(key);
        return normalized.contains("token")
                || normalized.contains("password")
                || normalized.contains("secret");
    }

    private String fieldLabel(String fieldKey, String category) {
        String normalized = normalize(fieldKey);
        if ("status".equals(normalized)) {
            return switch (category) {
                case "ACCOUNT" -> "账户状态";
                case "CAMPAIGN" -> "广告系列状态";
                case "AD_SET" -> "广告组状态";
                case "AD" -> "广告状态";
                default -> "状态";
            };
        }
        if (normalized.isBlank()) return "变更内容";
        return FIELD_LABELS.getOrDefault(normalized, humanize(normalized));
    }

    private String humanize(String key) {
        String normalized = key.replace('-', '_').trim();
        if (normalized.isBlank()) return "详情";
        String[] parts = normalized.split("_+");
        StringBuilder label = new StringBuilder();
        for (String part : parts) {
            if (part.isBlank()) continue;
            if (!label.isEmpty()) label.append(' ');
            label.append(Character.toUpperCase(part.charAt(0))).append(part.substring(1));
        }
        return label.toString();
    }

    private String formatValue(JsonNode value, String fieldKey, JsonNode context) {
        if (isMissing(value)) return null;
        if (value.isValueNode()) {
            String raw = value.asText();
            if (MONEY_KEYS.contains(normalize(fieldKey))) {
                return formatMoney(raw, text(node(context, "currency")));
            }
            return raw;
        }
        String serialized = value.toString();
        if (serialized.length() <= MAX_COMPLEX_VALUE_LENGTH) return serialized;
        return serialized.substring(0, MAX_COMPLEX_VALUE_LENGTH) + "…";
    }

    private String formatMoney(String raw, String currency) {
        try {
            BigDecimal amount = new BigDecimal(raw).movePointLeft(2).stripTrailingZeros();
            String display = amount.scale() < 2 ? amount.setScale(2).toPlainString() : amount.toPlainString();
            return currency == null || currency.isBlank() ? display : currency + " " + display;
        } catch (NumberFormatException ignored) {
            return raw;
        }
    }

    private JsonNode node(JsonNode parent, String key) {
        return parent == null ? null : parent.get(key);
    }

    private JsonNode firstPresent(JsonNode first, JsonNode second) {
        return !isMissing(first) ? first : second;
    }

    private JsonNode nestedValue(JsonNode object, String changeKey) {
        if (object == null) return null;
        JsonNode value = firstPresent(node(object, changeKey), node(object, "value"));
        value = firstPresent(value, node(object, "amount"));
        return isMissing(value) ? object : value;
    }

    private boolean isMissing(JsonNode value) {
        return value == null || value.isNull() || (value.isTextual() && value.asText().isBlank());
    }

    private String text(JsonNode value) {
        return isMissing(value) ? "" : value.asText();
    }

    private String firstNonBlank(String first, String second) {
        return first != null && !first.isBlank() ? first : second == null ? "" : second;
    }

    private String normalize(String value) {
        return value == null ? "" : value.trim().toLowerCase(Locale.ROOT);
    }
}
