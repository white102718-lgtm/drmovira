package com.adpulse.main.alertnotification.service;

import com.adpulse.main.alertnotification.mapper.AlertNotificationMapper;
import com.adpulse.main.alertnotification.model.AlertModels.Recipient;
import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.databind.ObjectMapper;
import java.util.List;
import java.util.Map;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.http.MediaType;
import org.springframework.stereotype.Component;
import org.springframework.util.StringUtils;
import org.springframework.web.client.RestClient;

/** 使用 Mpower 应用向系统用户或飞书群投递预警文本。 */
@Component
public class AlertFeishuSender {
    private final AlertNotificationMapper mapper;
    private final ObjectMapper json;
    private final String appId;
    private final String appSecret;
    private final String testRecipientPhone;
    private final String contentPrefix;
    private final RestClient client =
            RestClient.builder().baseUrl("https://open.feishu.cn/open-apis").build();

    public AlertFeishuSender(
            AlertNotificationMapper mapper,
            ObjectMapper json,
            @Value("${mpower.feishu.app-id:}") String appId,
            @Value("${mpower.feishu.app-secret:}") String appSecret,
            @Value("${adpulse.feishu.notification.test-recipient-phone:}")
                    String testRecipientPhone,
            @Value("${adpulse.feishu.notification.content-prefix:}") String contentPrefix) {
        this.mapper = mapper;
        this.json = json;
        this.appId = environmentValue("MPOWER_FEISHU_APP_ID", appId);
        this.appSecret = environmentValue("MPOWER_FEISHU_APP_SECRET", appSecret);
        this.testRecipientPhone = testRecipientPhone;
        this.contentPrefix = contentPrefix;
    }

    public DeliveryResult send(Recipient recipient, String content) {
        if (!StringUtils.hasText(appId) || !StringUtils.hasText(appSecret)) {
            return new DeliveryResult(false, "Mpower飞书凭据未配置");
        }
        try {
            String token = tenantAccessToken();
            if (StringUtils.hasText(testRecipientPhone)) {
                sendText(
                        token,
                        "open_id",
                        findOpenId(token, testRecipientPhone),
                        contentPrefix + content);
            } else if ("CHAT".equals(recipient.recipientType)) {
                sendText(token, "chat_id", recipient.recipientKey, contentPrefix + content);
            } else if ("USER".equals(recipient.recipientType)) {
                String phone = mapper.findActiveUserPhone(Long.valueOf(recipient.recipientKey));
                if (!StringUtils.hasText(phone)) return new DeliveryResult(false, "用户不存在或未配置手机号");
                String openId = findOpenId(token, phone);
                sendText(token, "open_id", openId, contentPrefix + content);
            } else {
                return new DeliveryResult(false, "不支持的收件人类型");
            }
            return new DeliveryResult(true, null);
        } catch (RuntimeException exception) {
            return new DeliveryResult(false, exception.getMessage());
        }
    }

    private String findOpenId(String token, String phone) {
        Map<?, ?> response =
                client.post()
                        .uri("/contact/v3/users/batch_get_id?user_id_type=open_id")
                        .header("Authorization", "Bearer " + token)
                        .contentType(MediaType.APPLICATION_JSON)
                        .body(Map.of("mobiles", List.of(phone)))
                        .retrieve()
                        .body(Map.class);
        if (response == null || !"0".equals(String.valueOf(response.get("code")))) {
            throw new IllegalStateException("飞书收件人解析失败");
        }
        Object dataValue = response.get("data");
        if (!(dataValue instanceof Map<?, ?> data)
                || !(data.get("user_list") instanceof List<?> users)
                || users.isEmpty()
                || !(users.getFirst() instanceof Map<?, ?> user)) {
            throw new IllegalStateException("手机号未匹配到飞书用户");
        }
        String openId = String.valueOf(user.get("user_id"));
        if (!StringUtils.hasText(openId) || "null".equals(openId)) {
            throw new IllegalStateException("飞书用户缺少open_id");
        }
        return openId;
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
            throw new IllegalStateException("Mpower飞书认证失败");
        }
        return String.valueOf(response.get("tenant_access_token"));
    }

    private void sendText(String token, String receiveType, String receiveId, String content) {
        Map<?, ?> response =
                client.post()
                        .uri("/im/v1/messages?receive_id_type=" + receiveType)
                        .header("Authorization", "Bearer " + token)
                        .contentType(MediaType.APPLICATION_JSON)
                        .body(
                                Map.of(
                                        "receive_id",
                                        receiveId,
                                        "msg_type",
                                        "text",
                                        "content",
                                        textContent(content)))
                        .retrieve()
                        .body(Map.class);
        if (response == null || !"0".equals(String.valueOf(response.get("code")))) {
            throw new IllegalStateException("飞书消息投递失败");
        }
    }

    private String textContent(String content) {
        try {
            return json.writeValueAsString(Map.of("text", content));
        } catch (JsonProcessingException exception) {
            throw new IllegalStateException("飞书消息编码失败", exception);
        }
    }

    private String environmentValue(String name, String fallback) {
        String value = System.getenv(name);
        return StringUtils.hasText(value) ? value : fallback;
    }

    public record DeliveryResult(boolean success, String errorMessage) {}
}
