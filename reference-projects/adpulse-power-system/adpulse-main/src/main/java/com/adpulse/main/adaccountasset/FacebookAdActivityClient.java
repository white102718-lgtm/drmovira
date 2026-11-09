package com.adpulse.main.adaccountasset;

import static com.adpulse.main.adaccountasset.AdAccountAssetViews.FacebookActivity;
import static com.adpulse.main.adaccountasset.AdAccountAssetViews.FacebookActivityPage;

import com.facebook.ads.sdk.APIContext;
import com.facebook.ads.sdk.APIException;
import com.facebook.ads.sdk.APINodeList;
import com.facebook.ads.sdk.AdAccount;
import com.facebook.ads.sdk.AdActivity;
import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.node.ObjectNode;
import java.nio.charset.StandardCharsets;
import java.util.Iterator;
import java.util.List;
import java.util.Locale;
import java.util.Map;
import java.util.UUID;
import org.springframework.stereotype.Component;

/** 对 Meta Java Business SDK 的最小封装，隔离第三方异常与敏感响应。 */
@Component
public class FacebookAdActivityClient {
    private static final String REDACTED = "***";
    private final ObjectMapper objectMapper;
    private final FacebookActivitySummaryParser summaryParser;

    public FacebookAdActivityClient(ObjectMapper objectMapper) {
        this.objectMapper = objectMapper;
        this.summaryParser = new FacebookActivitySummaryParser(objectMapper);
    }

    /** 使用服务端个号 Token 查询一页广告账户活动，Token 不参与返回值和异常信息。 */
    public FacebookActivityPage list(
            String accessToken,
            String accountId,
            long since,
            long until,
            String after,
            int pageSize) {
        try {
            APIContext context = new APIContext(accessToken);
            AdAccount.APIRequestGetActivities request =
                    new AdAccount(accountId, context)
                            .getActivities()
                            .setSince(String.valueOf(since))
                            .setUntil(String.valueOf(until))
                            .setLimit((long) pageSize)
                            .requestAllFields();
            if (after != null && !after.isBlank()) request.setAfter(after.trim());

            APINodeList<AdActivity> response = request.execute();
            String nextAfter = nextAfter(response);
            List<FacebookActivity> items = response.stream().map(this::view).toList();
            return new FacebookActivityPage(items, nextAfter, nextAfter != null, since, until);
        } catch (APIException exception) {
            throw new FacebookActivityProviderException("Facebook 操作记录暂时无法获取，请稍后重试", exception);
        }
    }

    private FacebookActivity view(AdActivity activity) {
        String eventType = text(activity.getFieldEventType());
        String objectType = text(activity.getFieldObjectType());
        String occurredAt =
                firstText(activity.getFieldEventTime(), activity.getFieldDateTimeInTimezone());
        String sanitizedExtraData = sanitizedExtraData(activity.getFieldExtraData());
        String category = summaryParser.category(eventType, objectType);
        String stableSource =
                String.join(
                        "|",
                        text(activity.getFieldActorId()),
                        text(activity.getFieldObjectId()),
                        eventType,
                        text(occurredAt),
                        text(activity.getFieldExtraData()));
        String id =
                "facebook-" + UUID.nameUUIDFromBytes(stableSource.getBytes(StandardCharsets.UTF_8));
        return new FacebookActivity(
                id,
                activity.getFieldActorId(),
                activity.getFieldActorName(),
                activity.getFieldApplicationId(),
                activity.getFieldApplicationName(),
                occurredAt,
                activity.getFieldDateTimeInTimezone(),
                eventType,
                activity.getFieldTranslatedEventType(),
                activity.getFieldObjectId(),
                activity.getFieldObjectName(),
                objectType,
                activity.getFieldTool(),
                category,
                summaryParser.parse(sanitizedExtraData, category),
                sanitizedExtraData);
    }

    private String nextAfter(APINodeList<AdActivity> response) {
        try {
            JsonNode paging = objectMapper.readTree(response.getRawResponse()).path("paging");
            if (!paging.path("next").isTextual()) return null;
            JsonNode after = paging.path("cursors").path("after");
            return after.isTextual() && !after.asText().isBlank() ? after.asText() : null;
        } catch (JsonProcessingException ignored) {
            return null;
        }
    }

    String sanitizedExtraData(String raw) {
        if (raw == null || raw.isBlank()) return null;
        try {
            JsonNode root = objectMapper.readTree(raw);
            redact(root);
            return objectMapper.writeValueAsString(root);
        } catch (JsonProcessingException ignored) {
            return raw.replaceAll(
                    "(?i)(access_token|token|password|secret)(\\s*[=:]\\s*)[^,\\s}]+",
                    "$1$2" + REDACTED);
        }
    }

    private void redact(JsonNode node) {
        if (node instanceof ObjectNode object) {
            Iterator<Map.Entry<String, JsonNode>> fields = object.fields();
            while (fields.hasNext()) {
                Map.Entry<String, JsonNode> field = fields.next();
                if (isSensitive(field.getKey())) object.put(field.getKey(), REDACTED);
                else redact(field.getValue());
            }
            return;
        }
        if (node.isArray()) node.forEach(this::redact);
    }

    private boolean isSensitive(String key) {
        String normalized = key.toLowerCase(Locale.ROOT);
        return normalized.contains("token")
                || normalized.contains("password")
                || normalized.contains("secret");
    }

    private String text(Object value) {
        return value == null ? "" : String.valueOf(value);
    }

    private String firstText(Object... values) {
        for (Object value : values) {
            String candidate = text(value).trim();
            if (!candidate.isEmpty()) return candidate;
        }
        return "";
    }

    /** Meta 提供方异常；对外只保留固定、无敏感信息的业务提示。 */
    public static final class FacebookActivityProviderException extends RuntimeException {
        public FacebookActivityProviderException(String message, Throwable cause) {
            super(message, cause);
        }
    }
}
