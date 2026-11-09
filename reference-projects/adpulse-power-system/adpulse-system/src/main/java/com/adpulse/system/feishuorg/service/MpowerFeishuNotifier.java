package com.adpulse.system.feishuorg.service;

import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.databind.ObjectMapper;
import java.util.List;
import java.util.Map;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.http.MediaType;
import org.springframework.stereotype.Component;
import org.springframework.util.StringUtils;
import org.springframework.web.client.RestClient;

/** 使用 Mpower 机器人向 AdPulse 用户发送飞书私聊消息。 */
@Component
public class MpowerFeishuNotifier {
    private static final Logger log = LoggerFactory.getLogger(MpowerFeishuNotifier.class);

    private final FeishuNotificationRecipientResolver recipientResolver;
    private final ObjectMapper json;
    private final String appId;
    private final String appSecret;
    private final RestClient client;

    public MpowerFeishuNotifier(
            FeishuNotificationRecipientResolver recipientResolver,
            ObjectMapper json,
            @Value("${mpower.feishu.app-id:}") String appId,
            @Value("${mpower.feishu.app-secret:}") String appSecret) {
        this.recipientResolver = recipientResolver;
        this.json = json;
        this.appId = environmentValue("MPOWER_FEISHU_APP_ID", appId);
        this.appSecret = environmentValue("MPOWER_FEISHU_APP_SECRET", appSecret);
        this.client = RestClient.builder().baseUrl("https://open.feishu.cn/open-apis").build();
    }

    /** 向指定系统用户发送 Mpower 飞书文本消息；投递失败只记录告警，不影响已提交的业务事务。 */
    public void notifyUsers(List<Long> userIds, String content) {
        if (userIds == null || userIds.isEmpty() || !StringUtils.hasText(content)) return;
        if (!StringUtils.hasText(appId) || !StringUtils.hasText(appSecret)) {
            log.warn("Mpower Feishu notification skipped: bot credentials are unavailable");
            return;
        }

        try {
            List<String> phones = recipientResolver.resolveRecipientPhones(userIds);
            if (phones.isEmpty()) {
                log.warn("Mpower Feishu notification skipped: no active recipient phone");
                return;
            }

            String tenantToken = tenantAccessToken();
            List<String> openIds = findOpenIdsByMobile(tenantToken, phones);
            if (openIds.isEmpty()) {
                log.warn("Mpower Feishu notification skipped: no recipient open_id was resolved");
                return;
            }
            String decoratedContent = recipientResolver.decorateContent(content);
            for (String openId : openIds) {
                sendText(tenantToken, openId, decoratedContent);
            }
            log.info("Mpower Feishu notification delivered to {} recipient(s)", openIds.size());
        } catch (RuntimeException exception) {
            log.warn("Mpower Feishu notification failed: {}", exception.getMessage());
        }
    }

    private List<String> findOpenIdsByMobile(String tenantToken, List<String> phones) {
        Map<?, ?> response =
                client.post()
                        .uri("/contact/v3/users/batch_get_id?user_id_type=open_id")
                        .header("Authorization", "Bearer " + tenantToken)
                        .contentType(MediaType.APPLICATION_JSON)
                        .body(Map.of("mobiles", phones))
                        .retrieve()
                        .body(Map.class);
        if (response == null || !"0".equals(String.valueOf(response.get("code")))) {
            throw new IllegalStateException("Mpower Feishu recipient lookup was rejected");
        }
        Object dataValue = response.get("data");
        if (!(dataValue instanceof Map<?, ?> data)
                || !(data.get("user_list") instanceof List<?> users)) {
            return List.of();
        }
        return users.stream()
                .filter(Map.class::isInstance)
                .map(Map.class::cast)
                .map(
                        user -> {
                            Object userId = user.get("user_id");
                            return userId == null
                                    ? String.valueOf(user.get("open_id"))
                                    : userId.toString();
                        })
                .filter(StringUtils::hasText)
                .filter(value -> !"null".equals(value))
                .distinct()
                .toList();
    }

    private String tenantAccessToken() {
        Map<?, ?> response =
                client.post()
                        .uri("/auth/v3/tenant_access_token/internal")
                        .contentType(MediaType.APPLICATION_JSON)
                        .body(Map.of("app_id", appId, "app_secret", appSecret))
                        .retrieve()
                        .body(Map.class);
        if (response == null || !"0".equals(String.valueOf(response.get("code")))) {
            throw new IllegalStateException("Mpower Feishu tenant authentication was rejected");
        }
        String token = String.valueOf(response.get("tenant_access_token"));
        if (!StringUtils.hasText(token) || "null".equals(token)) {
            throw new IllegalStateException("Mpower Feishu did not return a tenant access token");
        }
        return token;
    }

    private void sendText(String tenantToken, String openId, String text) {
        Map<?, ?> response =
                client.post()
                        .uri("/im/v1/messages?receive_id_type=open_id")
                        .header("Authorization", "Bearer " + tenantToken)
                        .contentType(MediaType.APPLICATION_JSON)
                        .body(
                                Map.of(
                                        "receive_id",
                                        openId,
                                        "msg_type",
                                        "text",
                                        "content",
                                        textContent(text)))
                        .retrieve()
                        .body(Map.class);
        if (response == null || !"0".equals(String.valueOf(response.get("code")))) {
            throw new IllegalStateException("Mpower Feishu message delivery was rejected");
        }
    }

    private String textContent(String text) {
        try {
            return json.writeValueAsString(Map.of("text", text));
        } catch (JsonProcessingException exception) {
            throw new IllegalStateException(
                    "Failed to encode Mpower Feishu text message", exception);
        }
    }

    private String environmentValue(String name, String fallback) {
        String value = System.getenv(name);
        return StringUtils.hasText(value) ? value : fallback;
    }
}
